"""Offline integration smoke tests; no real SMS, email or push are sent."""
import os
import unittest
from unittest.mock import patch

# Set these before the app/config modules are imported.
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['SECRET_KEY'] = 'testing-only-not-for-production'
os.environ['SMS_ENABLED'] = 'true'
os.environ['SMS_TO_API_KEY'] = 'dummy-testing-key'

from app import create_app
from extensions import db
from models import Client, User, Message, MessageDelivery
from werkzeug.security import generate_password_hash


class MessagingTests(unittest.TestCase):
    def setUp(self):
        self.app=create_app()
        self.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        self.ctx=self.app.app_context();self.ctx.push()
        db.create_all()
        c=Client(full_name='Δοκιμαστικός πελάτης', phone='6912345678', sms_consent=True)
        db.session.add(c);db.session.flush()
        self.cid=c.id
        db.session.add(User(username='admin',role='admin',password_hash=generate_password_hash('pass123')))
        db.session.add(User(username='client',role='client',client_id=c.id,password_hash=generate_password_hash('pass123')))
        db.session.commit()
        self.web=self.app.test_client()

    def tearDown(self):
        db.session.remove();db.drop_all();self.ctx.pop()

    def login(self, role):
        self.web.post('/login/'+role,data={'username':role,'password':'pass123'})

    def test_client_sends_and_admin_dashboard_receives(self):
        self.login('client')
        res=self.web.post('/client/messages/send',data={'body':'Καλημέρα από τον πελάτη'},follow_redirects=True)
        self.assertEqual(res.status_code,200)
        self.assertEqual(Message.query.filter_by(direction='client_to_admin').count(),1)
        self.web.post('/logout')
        self.login('admin')
        page=self.web.get('/admin')
        self.assertIn('Καλημέρα από τον πελάτη'.encode('utf8'),page.data)
        self.assertIn('1 αδιάβαστα'.encode('utf8'),page.data)
        self.web.get('/admin/clients/%s/messages' % self.cid)
        self.assertEqual(Message.query.filter_by(direction='client_to_admin',read_at=None).count(),0)

    def test_admin_portal_and_sms_log_without_network(self):
        self.login('admin')
        with patch('services.messaging.send_sms',return_value='fake-provider-id') as send:
            response=self.web.post('/admin/clients/%s/messages' % self.cid,data={
                'body':'Δοκιμαστική ενημέρωση','portal':'y','sms':'y'},follow_redirects=True)
            self.assertEqual(response.status_code,200)
            send.assert_called_once()
        msg=Message.query.filter_by(direction='admin_to_client').first()
        self.assertTrue(msg.portal_visible)
        self.assertEqual(MessageDelivery.query.filter_by(message_id=msg.id).count(),2)
        self.web.post('/logout')
        self.login('client')
        self.assertIn('Δοκιμαστική ενημέρωση'.encode('utf8'),self.web.get('/client').data)

    def test_sms_only_not_visible_on_client_portal(self):
        self.login('admin')
        with patch('services.messaging.send_sms',return_value='fake-provider-id'):
            self.web.post('/admin/clients/%s/messages' % self.cid,
                          data={'body':'Μήνυμα μόνο σε SMS','sms':'y'})
        self.web.post('/logout');self.login('client')
        self.assertNotIn('Μήνυμα μόνο σε SMS'.encode('utf8'),self.web.get('/client').data)

if __name__=='__main__':unittest.main()
