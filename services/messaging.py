"""Direct admin-to-client channels; don't put personal/health info in push bodies."""
import json
import os
from pathlib import Path

from extensions import db
from models import MessageDelivery, PushSubscription
from services.notifications import e164_gr, send_sms, send_email, sms_settings


def push_settings():
    key_path = os.getenv('VAPID_PRIVATE_KEY', '').strip()
    if key_path and not os.path.isabs(key_path):
        key_path = str(Path(__file__).resolve().parent.parent / key_path)
    return {
        'ready': bool(os.getenv('VAPID_PUBLIC_KEY', '').strip() and
                      key_path and Path(key_path).is_file() and
                      os.getenv('VAPID_CONTACT', '').strip()),
        'public_key': os.getenv('VAPID_PUBLIC_KEY', '').strip(),
        'private_key': key_path,
        'contact': os.getenv('VAPID_CONTACT', '').strip(),
    }


def channel_blockers(client, channel):
    """No implicit opt-in based on merely having a phone or email."""
    reasons = []
    if channel == 'sms':
        config = sms_settings()
        if not config['enabled'] or not config['key_ready']:
            reasons.append('Δεν έχει ενεργοποιηθεί το SMS.to στο .env')
        if not client.sms_consent:
            reasons.append('Δεν υπάρχει συναίνεση SMS στην καρτέλα πελάτη')
        try:
            e164_gr(client.phone)
        except ValueError:
            reasons.append('Λείπει έγκυρο ελληνικό κινητό')
    elif channel == 'email':
        if os.getenv('EMAIL_ENABLED', '').lower() != 'true':
            reasons.append('EMAIL_ENABLED δεν είναι true')
        if not os.getenv('SMTP_HOST') or not os.getenv('SMTP_FROM'):
            reasons.append('Λείπουν SMTP_HOST ή SMTP_FROM')
        if not client.email_consent:
            reasons.append('Δεν υπάρχει συναίνεση email στην καρτέλα πελάτη')
        if not client.email or '@' not in client.email:
            reasons.append('Λείπει έγκυρο email στην καρτέλα πελάτη')
    elif channel == 'push':
        if not push_settings()['ready']:
            reasons.append('Δεν έχουν ρυθμιστεί VAPID keys')
        if not PushSubscription.query.filter_by(client_id=client.id).first():
            reasons.append('Ο πελάτης δεν έχει ενεργοποιήσει push σε συσκευή')
    elif channel == 'portal':
        # Messages can be stored even without an account; they become visible at login.
        pass
    else:
        reasons.append('Μη αναγνωρισμένο κανάλι')
    return reasons


def _push_one(subscription, client_id):
    from pywebpush import webpush
    settings = push_settings()
    # Deliberately generic: notifications may appear on a locked device.
    payload = json.dumps({
        'title': 'CHRYSPHARMACY',
        'body': 'Έχετε νέο προσωπικό μήνυμα στην καρτέλα σας.',
        'url': '/client#messages',
    }, ensure_ascii=False)
    return webpush(
        subscription_info={
            'endpoint': subscription.endpoint,
            'keys': {'p256dh': subscription.p256dh, 'auth': subscription.auth},
        },
        data=payload,
        vapid_private_key=settings['private_key'],
        vapid_claims={'sub': settings['contact']},
        ttl=3600,
        timeout=15,
    )


def send_push(client):
    subscriptions = PushSubscription.query.filter_by(client_id=client.id).all()
    if not subscriptions:
        raise RuntimeError('Δεν υπάρχει εγγεγραμμένη συσκευή για push.')
    successful = 0
    failures = 0
    for sub in subscriptions:
        try:
            _push_one(sub, client.id)
            successful += 1
        except Exception as exc:
            failures += 1
            # A 404/410 means subscription was revoked/expired. Other errors stay logged generically.
            response = getattr(exc, 'response', None)
            if getattr(response, 'status_code', None) in (404, 410):
                db.session.delete(sub)
    db.session.commit()
    if not successful:
        raise RuntimeError('Η αποστολή push απέτυχε σε όλες τις συσκευές. Έλεγξε VAPID, HTTPS και ενεργή συνδρομή.')
    return f'{successful} συσκευή(ές)' + (f' · {failures} αποτυχία(ες)' if failures else '')


def deliver_message(message, channels):
    """Record each channel attempt before making external network calls; no silent retry."""
    statuses = []
    client = message_client(message)
    for channel in channels:
        blockers = channel_blockers(client, channel)
        if blockers:
            statuses.append((channel, 'skipped', ' · '.join(blockers)))
            continue
        existing = MessageDelivery.query.filter_by(message_id=message.id, channel=channel).first()
        if existing:
            statuses.append((channel, 'skipped', 'Έχει καταγραφεί προηγούμενη προσπάθεια'))
            continue
        log = MessageDelivery(message_id=message.id, channel=channel, status='processing')
        db.session.add(log)
        db.session.commit()
        try:
            if channel == 'portal':
                result = 'portal'
                status = 'saved'
            elif channel == 'sms':
                result = send_sms(client.phone, message.body)
                status = 'queued'
            elif channel == 'email':
                send_email(client.email, 'Προσωπικό μήνυμα από CHRYSPHARMACY', message.body)
                result = 'smtp'
                status = 'sent'
            elif channel == 'push':
                result = send_push(client)
                status = 'queued'
            else:
                raise ValueError('Μη αναγνωρισμένο κανάλι')
            log.status = status
            log.provider_id = str(result or '')[:120]
            statuses.append((channel, status, ''))
        except Exception as exc:
            log.status = 'failed'
            # Never expose bearer tokens or health data from upstream errors.
            log.error = 'Αποτυχία από τον πάροχο ή τη ρύθμιση. Έλεγξε τα logs χωρίς να κοινοποιήσεις διαπιστευτήρια.'
            statuses.append((channel, 'failed', log.error))
        db.session.commit()
    return statuses


def message_client(message):
    from models import Client
    return db.session.get(Client, message.client_id)
