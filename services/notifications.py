import os, re, smtplib
from datetime import date
from email.message import EmailMessage
import requests
from sqlalchemy.exc import IntegrityError
from extensions import db
from models import Client, Prescription, NotificationLog

def e164_gr(phone):
    digits=re.sub(r'[^0-9+]','',phone or '')
    if re.fullmatch(r'69\d{8}',digits): return '+30'+digits
    if re.fullmatch(r'003069\d{8}',digits): return '+'+digits[2:]
    if re.fullmatch(r'\+3069\d{8}',digits): return digits
    raise ValueError('Μη έγκυρος αριθμός κινητού Ελλάδας')

def send_sms(phone,message):
    key=os.getenv('SMS_TO_API_KEY','')
    if not key: raise RuntimeError('Δεν έχει οριστεί SMS_TO_API_KEY')
    sender=os.getenv('SMS_SENDER_ID','CHRYSPHARM')
    response=requests.post('https://api.sms.to/sms/send',headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},json={'to':e164_gr(phone),'message':message,'sender_id':sender},timeout=20)
    response.raise_for_status()
    data=response.json()
    if data.get('success') is not True: raise RuntimeError('Ο πάροχος δεν δέχτηκε το SMS')
    return data.get('message_id')

def send_email(address,subject,body):
    host=os.getenv('SMTP_HOST');sender=os.getenv('SMTP_FROM')
    if not host or not sender: raise RuntimeError('Δεν έχουν οριστεί SMTP_HOST/SMTP_FROM')
    msg=EmailMessage();msg['From']=sender;msg['To']=address;msg['Subject']=subject;msg.set_content(body)
    with smtplib.SMTP(host,int(os.getenv('SMTP_PORT','587')),timeout=20) as server:
        if os.getenv('SMTP_STARTTLS','true').lower()=='true': server.starttls()
        if os.getenv('SMTP_USER'): server.login(os.getenv('SMTP_USER'),os.getenv('SMTP_PASSWORD',''))
        server.send_message(msg)

def send_due_notifications(today=None):
    today=today or date.today()
    items=Prescription.query.filter_by(opens_on=today,active=True).all()
    results={'queued':0,'failed':0,'skipped':0}
    text='CHRYSPHARMACY: Η συνταγή σας είναι διαθέσιμη. Επικοινωνήστε με το φαρμακείο για την παραλαβή.'
    for prescription in items:
        client=prescription.client
        channels=[('sms',client.sms_consent and bool(client.phone) and os.getenv('SMS_ENABLED','false').lower()=='true'),('email',client.email_consent and bool(client.email) and os.getenv('EMAIL_ENABLED','false').lower()=='true')]
        for channel,enabled in channels:
            if not enabled: results['skipped']+=1;continue
            if NotificationLog.query.filter_by(prescription_id=prescription.id,channel=channel,event_date=today).first():
                results['skipped']+=1;continue
            log=NotificationLog(prescription_id=prescription.id,channel=channel,event_date=today,status='processing')
            db.session.add(log)
            try: db.session.commit()
            except IntegrityError:
                db.session.rollback();results['skipped']+=1;continue
            try:
                if channel=='sms': log.provider_id=send_sms(client.phone,text);log.status='queued'
                else: send_email(client.email,'Ενημέρωση από CHRYSPHARMACY',text);log.status='queued'
                results['queued']+=1
            except Exception as exc:
                log.status='failed';log.error=str(exc)[:300];results['failed']+=1
            db.session.commit()
    return results


def send_prescription_sms(prescription):
    """Explicit admin action; never silently retries a provider request."""
    if not prescription.active:
        raise ValueError('Η συνταγή δεν είναι ενεργή.')
    if prescription.opens_on > date.today():
        raise ValueError('Η συνταγή δεν έχει ανοίξει ακόμη.')
    client=prescription.client
    if not client.sms_consent:
        raise ValueError('Δεν υπάρχει συναίνεση για SMS στην καρτέλα πελάτη.')
    if not client.phone:
        raise ValueError('Δεν έχει δηλωθεί κινητό.')
    if os.getenv('SMS_ENABLED','false').lower()!='true':
        raise ValueError('Η αποστολή SMS είναι απενεργοποιημένη (SMS_ENABLED=false).')
    if not os.getenv('SMS_TO_API_KEY','').strip():
        raise ValueError('Λείπει το SMS_TO_API_KEY στο .env.')
    e164_gr(client.phone)  # validate before inserting a log
    existing=NotificationLog.query.filter_by(prescription_id=prescription.id,channel='sms').first()
    if existing:
        raise ValueError('Υπάρχει ήδη προσπάθεια SMS για αυτή τη συνταγή ('+existing.status+'). Έλεγξε το ιστορικό πριν ξαναστείλεις.')
    log=NotificationLog(prescription_id=prescription.id,channel='sms',event_date=date.today(),status='processing')
    db.session.add(log)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ValueError('Υπάρχει ήδη καταχώριση SMS για τη συνταγή.')
    try:
        provider_id=send_sms(client.phone,'CHRYSPHARMACY: Η συνταγή σας είναι διαθέσιμη. Επικοινωνήστε με το φαρμακείο για την παραλαβή.')
        log.provider_id=provider_id
        log.status='queued'
        db.session.commit()
        return provider_id
    except Exception as exc:
        log.status='failed'
        log.error=str(exc)[:300]
        db.session.commit()
        raise RuntimeError('Ο πάροχος επέστρεψε σφάλμα ή δεν επιβεβαίωσε αποδοχή. Μην επαναστείλεις πριν ελέγξεις το SMS.to.') from exc
