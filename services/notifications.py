"""Safe SMS.to and email notifications; keeps v2 database schema unchanged."""
import os
import re
import smtplib
from datetime import datetime
from zoneinfo import ZoneInfo
from email.message import EmailMessage

import requests
from sqlalchemy.exc import IntegrityError
from extensions import db
from models import Prescription, NotificationLog

ATHENS = ZoneInfo('Europe/Athens')
SMS_TEXT = 'CHRYSPHARMACY: Η συνταγή σας είναι διαθέσιμη. Επικοινωνήστε με το φαρμακείο για την παραλαβή.'


def local_today():
    """Prescription opening dates are evaluated in Greece, not UTC/server timezone."""
    return datetime.now(ATHENS).date()


def sms_settings():
    return {
        'enabled': os.getenv('SMS_ENABLED', '').strip().lower() == 'true',
        'key_ready': bool(os.getenv('SMS_TO_API_KEY', '').strip()),
        'sender': os.getenv('SMS_SENDER_ID', 'CHRYSPHARM').strip(),
    }


def e164_gr(phone):
    digits = re.sub(r'[\s\-().]', '', phone or '')
    if re.fullmatch(r'69\d{8}', digits):
        return '+30' + digits
    if re.fullmatch(r'003069\d{8}', digits):
        return '+' + digits[2:]
    if re.fullmatch(r'\+3069\d{8}', digits):
        return digits
    raise ValueError('Μη έγκυρος αριθμός κινητού. Χρησιμοποίησε 69xxxxxxxx ή +3069xxxxxxxx.')


def sms_blockers(prescription, today=None, existing_log=None):
    """Return specific reasons why the admin cannot send this prescription's SMS."""
    today = today or local_today()
    client = prescription.client
    settings = sms_settings()
    reasons = []
    if not settings['enabled']:
        reasons.append('SMS_ENABLED δεν είναι true στο .env')
    if not settings['key_ready']:
        reasons.append('Λείπει το SMS_TO_API_KEY από το .env')
    if not client.sms_consent:
        reasons.append('Δεν έχει ενεργοποιηθεί η συναίνεση SMS στην καρτέλα πελάτη')
    if not client.phone:
        reasons.append('Δεν έχει καταχωριστεί κινητό στην καρτέλα πελάτη')
    else:
        try:
            e164_gr(client.phone)
        except ValueError:
            reasons.append('Ο αριθμός κινητού δεν είναι έγκυρος')
    if not prescription.active:
        reasons.append('Η συνταγή είναι ανενεργή')
    if prescription.opens_on > today:
        reasons.append('Η συνταγή ανοίγει σε μεταγενέστερη ημερομηνία')
    if existing_log is None:
        existing_log = NotificationLog.query.filter_by(prescription_id=prescription.id, channel='sms').order_by(NotificationLog.id.desc()).first()
    if existing_log is not None:
        state = {'queued': 'δεκτό από SMS.to', 'processing': 'σε επεξεργασία', 'failed': 'προηγούμενη αποτυχία'}.get(existing_log.status, existing_log.status)
        reasons.append(f'Υπάρχει ήδη προσπάθεια SMS ({state}). Δες το ιστορικό πριν αποφασίσεις για νέα προσπάθεια')
    return reasons


def send_sms(phone, message):
    settings = sms_settings()
    key = os.getenv('SMS_TO_API_KEY', '').strip()
    if not settings['enabled'] or not key:
        raise RuntimeError('SMS.to ανενεργό ή δεν έχει καταχωριστεί API key.')
    payload = {'to': e164_gr(phone), 'message': message, 'sender_id': settings['sender']}
    try:
        response = requests.post(
            'https://api.sms.to/sms/send',
            headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'},
            json=payload,
            timeout=20,
        )
    except requests.RequestException as exc:
        raise RuntimeError('Αδυναμία επικοινωνίας με SMS.to. Έλεγξε τον λογαριασμό SMS.to πριν προσπαθήσεις ξανά.') from exc
    if not response.ok:
        raise RuntimeError(f'SMS.to επέστρεψε HTTP {response.status_code}. Έλεγξε API key, υπόλοιπο και Sender ID στον λογαριασμό SMS.to.')
    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError('Μη αναμενόμενη απάντηση από SMS.to. Έλεγξε το SMS.to πριν επαναλάβεις.') from exc
    if data.get('success') is not True:
        raise RuntimeError('Το SMS.to δεν επιβεβαίωσε αποδοχή του SMS. Έλεγξε το SMS.to dashboard.')
    return data.get('message_id')


def send_email(address, subject, body):
    host = os.getenv('SMTP_HOST')
    sender = os.getenv('SMTP_FROM')
    if not host or not sender:
        raise RuntimeError('Δεν έχουν οριστεί SMTP_HOST / SMTP_FROM.')
    msg = EmailMessage()
    msg['From'] = sender
    msg['To'] = address
    msg['Subject'] = subject
    msg.set_content(body)
    with smtplib.SMTP(host, int(os.getenv('SMTP_PORT', '587')), timeout=20) as server:
        if os.getenv('SMTP_STARTTLS', 'true').lower() == 'true':
            server.starttls()
        if os.getenv('SMTP_USER'):
            server.login(os.getenv('SMTP_USER'), os.getenv('SMTP_PASSWORD', ''))
        server.send_message(msg)


def _new_log(prescription, channel, when):
    log = NotificationLog(prescription_id=prescription.id, channel=channel, event_date=when, status='processing')
    db.session.add(log)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return None
    return log


def _dispatch(log, send_fn):
    try:
        log.provider_id = send_fn()
        log.status = 'queued'
        db.session.commit()
        return True
    except Exception as exc:
        log.status = 'failed'
        # Never store phone, bearer token, or medical data in log errors.
        log.error = str(exc)[:300]
        db.session.commit()
        return False


def send_prescription_sms(prescription):
    reasons = sms_blockers(prescription)
    if reasons:
        raise ValueError(' · '.join(reasons))
    log = _new_log(prescription, 'sms', local_today())
    if log is None:
        raise ValueError('Υπάρχει ήδη προσπάθεια SMS για τη σημερινή ημερομηνία.')
    sent = _dispatch(log, lambda: send_sms(prescription.client.phone, SMS_TEXT))
    if not sent:
        raise RuntimeError('Απέτυχε ή δεν επιβεβαιώθηκε η αποστολή. Έλεγξε το ιστορικό και το SMS.to πριν από οποιαδήποτε νέα προσπάθεια.')
    return log.provider_id


def send_due_notifications(today=None):
    """Sends notifications for exactly today's opened prescriptions, not the backlog."""
    today = today or local_today()
    items = Prescription.query.filter_by(opens_on=today, active=True).all()
    results = {'queued': 0, 'failed': 0, 'skipped': 0}
    email_enabled = os.getenv('EMAIL_ENABLED', '').strip().lower() == 'true'
    for p in items:
        channels = [
            ('sms', not sms_blockers(p, today=today)),
            ('email', email_enabled and p.client.email_consent and bool(p.client.email)),
        ]
        for channel, allowed in channels:
            if not allowed or NotificationLog.query.filter_by(prescription_id=p.id, channel=channel).first():
                results['skipped'] += 1
                continue
            log = _new_log(p, channel, today)
            if log is None:
                results['skipped'] += 1
                continue
            if channel == 'sms':
                ok = _dispatch(log, lambda: send_sms(p.client.phone, SMS_TEXT))
            else:
                ok = _dispatch(log, lambda: send_email(p.client.email, 'Ενημέρωση CHRYSPHARMACY', SMS_TEXT))
            results['queued' if ok else 'failed'] += 1
    return results
