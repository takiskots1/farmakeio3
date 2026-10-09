import os
from datetime import date
import click
from flask import Flask, render_template, redirect, url_for, flash, request, abort
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import or_
from config import Config
from extensions import db
from models import User, Client, Prescription, Message, NotificationLog
from forms import LoginForm, ClientForm, PrescriptionForm, MessageForm
from services.notifications import send_due_notifications, send_prescription_sms

def create_app():
    app=Flask(__name__)
    app.config.from_object(Config)
    if not app.config['SECRET_KEY'] or not app.config['SQLALCHEMY_DATABASE_URI']:
        raise RuntimeError('Συμπλήρωσε SECRET_KEY και DATABASE_URL στο .env')
    db.init_app(app);CSRFProtect(app)
    login_manager=LoginManager(app)
    login_manager.login_view='client_login'
    @login_manager.user_loader
    def load_user(user_id):
        try:return db.session.get(User,int(user_id))
        except (ValueError,TypeError):return None
    def admin_only():
        if not current_user.is_authenticated or current_user.role!='admin':abort(403)
    @app.route('/')
    def index():return render_template('index.html')
    @app.route('/login/client',methods=['GET','POST'])
    def client_login():
        form=LoginForm()
        if form.validate_on_submit():
            user=User.query.filter_by(username=form.username.data,role='client').first()
            if user and check_password_hash(user.password_hash,form.password.data):
                login_user(user);return redirect(url_for('client_portal'))
            flash('Λανθασμένα στοιχεία σύνδεσης','error')
        return render_template('login.html',form=form,kind='client')
    @app.route('/login/admin',methods=['GET','POST'])
    def admin_login():
        form=LoginForm()
        if form.validate_on_submit():
            user=User.query.filter_by(username=form.username.data,role='admin').first()
            if user and check_password_hash(user.password_hash,form.password.data):
                login_user(user);return redirect(url_for('admin_dashboard'))
            flash('Λανθασμένα στοιχεία σύνδεσης','error')
        return render_template('login.html',form=form,kind='admin')
    @app.post('/logout')
    @login_required
    def logout():logout_user();return redirect(url_for('index'))
    @app.route('/admin')
    @login_required
    def admin_dashboard():
        admin_only()
        return render_template('admin/dashboard.html',clients=Client.query.count(),prescriptions=Prescription.query.count(),due=Prescription.query.filter_by(opens_on=date.today(),active=True).count(),logs=NotificationLog.query.order_by(NotificationLog.id.desc()).limit(25).all(),sms_enabled=os.getenv('SMS_ENABLED','false').lower()=='true',sms_key_ready=bool(os.getenv('SMS_TO_API_KEY','').strip()),today=date.today())
    @app.route('/admin/clients',methods=['GET','POST'])
    @login_required
    def clients():
        admin_only();form=ClientForm()
        if form.validate_on_submit():
            amka=form.amka.data or None
            if amka and Client.query.filter_by(amka=amka).first():flash('Το ΑΜΚΑ υπάρχει ήδη','error')
            elif form.username.data and User.query.filter_by(username=form.username.data).first():flash('Το username υπάρχει ήδη','error')
            elif bool(form.username.data)!=bool(form.password.data):flash('Για νέο login απαιτούνται username και password','error')
            else:
                c=Client(full_name=form.full_name.data,amka=amka,phone=form.phone.data,email=form.email.data,sms_consent=form.sms_consent.data,email_consent=form.email_consent.data)
                db.session.add(c);db.session.flush()
                if form.username.data:db.session.add(User(username=form.username.data,password_hash=generate_password_hash(form.password.data),role='client',client_id=c.id))
                db.session.commit();flash('Ο πελάτης αποθηκεύτηκε','ok');return redirect(url_for('clients'))
        q=request.args.get('q','').strip()
        query=Client.query
        if q:query=query.filter(or_(Client.full_name.ilike('%'+q+'%'),Client.amka.ilike('%'+q+'%'),Client.phone.ilike('%'+q+'%'),Client.email.ilike('%'+q+'%')))
        return render_template('admin/clients.html',form=form,clients=query.order_by(Client.full_name).limit(200).all(),q=q)
    @app.route('/admin/clients/<int:client_id>/edit',methods=['GET','POST'])
    @login_required
    def edit_client(client_id):
        admin_only();c=db.get_or_404(Client,client_id);form=ClientForm(obj=c)
        if form.validate_on_submit():
            amka=form.amka.data or None
            if amka and Client.query.filter(Client.amka==amka,Client.id!=c.id).first():flash('Το ΑΜΚΑ ανήκει σε άλλον πελάτη','error')
            else:
                c.full_name=form.full_name.data;c.amka=amka;c.phone=form.phone.data;c.email=form.email.data;c.sms_consent=form.sms_consent.data;c.email_consent=form.email_consent.data
                db.session.commit();flash('Η καρτέλα ενημερώθηκε','ok');return redirect(url_for('clients'))
        return render_template('admin/edit_client.html',form=form,client=c)
    @app.route('/admin/clients/<int:client_id>/prescriptions',methods=['GET','POST'])
    @login_required
    def prescriptions(client_id):
        admin_only();c=db.get_or_404(Client,client_id);form=PrescriptionForm()
        if form.validate_on_submit():
            db.session.add(Prescription(client_id=c.id,title=form.title.data,opens_on=form.opens_on.data,notes=form.notes.data,active=form.active.data))
            db.session.commit();flash('Η συνταγή αποθηκεύτηκε','ok');return redirect(url_for('prescriptions',client_id=c.id))
        return render_template('admin/prescriptions.html',client=c,form=form,items=Prescription.query.filter_by(client_id=c.id).order_by(Prescription.opens_on.desc()).all(),sms_enabled=os.getenv('SMS_ENABLED','false').lower()=='true',sms_key_ready=bool(os.getenv('SMS_TO_API_KEY','').strip()),today=date.today(),logs={log.prescription_id:log for log in NotificationLog.query.filter(NotificationLog.channel=='sms',NotificationLog.prescription_id.in_([i.id for i in c.prescriptions])).order_by(NotificationLog.id.asc()).all()})
    @app.post('/admin/prescriptions/<int:prescription_id>/send-sms')
    @login_required
    def send_prescription_sms_route(prescription_id):
        admin_only()
        item=db.get_or_404(Prescription,prescription_id)
        try:
            result=send_prescription_sms(item)
            flash('Το SMS έγινε δεκτό από SMS.to (σε ουρά). ID: '+str(result or '—'),'success')
        except (ValueError,RuntimeError) as exc:
            flash('Δεν στάλθηκε SMS: '+str(exc),'danger')
        except Exception:
            app.logger.exception('SMS sending failed for prescription %s',prescription_id)
            flash('Η αποστολή απέτυχε. Δες το ιστορικό ειδοποιήσεων και τα logs. Μην επαναλάβεις χωρίς έλεγχο.','danger')
        return redirect(url_for('prescriptions',client_id=item.client_id))
    @app.route('/admin/prescriptions/<int:prescription_id>/edit',methods=['GET','POST'])
    @login_required
    def edit_prescription(prescription_id):
        admin_only();item=db.get_or_404(Prescription,prescription_id);form=PrescriptionForm(obj=item)
        if form.validate_on_submit():
            item.title=form.title.data;item.opens_on=form.opens_on.data;item.notes=form.notes.data;item.active=form.active.data
            db.session.commit();flash('Η συνταγή ενημερώθηκε','ok');return redirect(url_for('prescriptions',client_id=item.client_id))
        return render_template('admin/edit_prescription.html',form=form,item=item)
    @app.route('/admin/clients/<int:client_id>/messages',methods=['GET','POST'])
    @login_required
    def messages(client_id):
        admin_only();c=db.get_or_404(Client,client_id);form=MessageForm()
        if form.validate_on_submit():
            db.session.add(Message(client_id=c.id,body=form.body.data));db.session.commit();flash('Το μήνυμα καταχωρίστηκε','ok');return redirect(url_for('messages',client_id=c.id))
        return render_template('admin/messages.html',client=c,form=form,items=Message.query.filter_by(client_id=c.id).order_by(Message.id.desc()).all())
    @app.post('/admin/send-due')
    @login_required
    def send_due():
        admin_only();r=send_due_notifications();flash('Ειδοποιήσεις — σε ουρά: {queued}, αποτυχίες: {failed}, παραλείψεις: {skipped}'.format(**r),'info');return redirect(url_for('admin_dashboard'))
    @app.route('/client')
    @login_required
    def client_portal():
        if current_user.role!='client' or not current_user.client_id:abort(403)
        c=db.get_or_404(Client,current_user.client_id)
        return render_template('client/portal.html',client=c,items=Prescription.query.filter_by(client_id=c.id).order_by(Prescription.opens_on.desc()).all(),messages=Message.query.filter_by(client_id=c.id).order_by(Message.id.desc()).all())
    @app.cli.command('init-db')
    def init_db():
        db.create_all();click.echo('Δημιουργήθηκαν οι πίνακες που έλειπαν (δεν τροποποιούνται υπάρχοντες).')
    @app.cli.command('create-admin')
    @click.option('--username',prompt=True)
    @click.password_option()
    def create_admin(username,password):
        if User.query.filter_by(username=username).first():raise click.ClickException('Το username υπάρχει ήδη')
        db.session.add(User(username=username,password_hash=generate_password_hash(password),role='admin'));db.session.commit();click.echo('Ο admin δημιουργήθηκε')
    @app.cli.command('send-due')
    def send_due_cli():click.echo(str(send_due_notifications()))
    return app

if __name__=='__main__':create_app().run(host='127.0.0.1',port=5001)
