import os
from datetime import date, timedelta
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
from services.notifications import (send_due_notifications, send_prescription_sms,
    sms_blockers, sms_settings, local_today)

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
        today = local_today()
        due_today = (Prescription.query.filter_by(opens_on=today, active=True)
                     .order_by(Prescription.id.desc()).all())
        overdue = (Prescription.query.filter(Prescription.opens_on < today, Prescription.active.is_(True))
                   .order_by(Prescription.opens_on.desc()).limit(20).all())
        upcoming = (Prescription.query.filter(Prescription.opens_on > today, Prescription.active.is_(True))
                    .order_by(Prescription.opens_on.asc()).limit(12).all())
        logs = NotificationLog.query.order_by(NotificationLog.id.desc()).limit(30).all()
        recent_messages = (db.session.query(Message, Client.full_name)
                           .join(Client, Message.client_id == Client.id)
                           .order_by(Message.id.desc()).limit(5).all())
        due_rows = [{'item': p, 'blockers': sms_blockers(p, today=today)} for p in due_today]
        return render_template(
            'admin/dashboard.html', clients=Client.query.count(),
            prescriptions=Prescription.query.count(), due=len(due_today),
            due_rows=due_rows, overdue=overdue, upcoming=upcoming, logs=logs,
            sms=sms_settings(), today=today, recent_messages=recent_messages,
            messages_count=Message.query.count(),
        )
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
        admin_only()
        c=db.get_or_404(Client,client_id)
        account=User.query.filter_by(client_id=c.id,role='client').first()
        form=ClientForm(obj=c)
        if request.method=='GET' and account:
            form.username.data=account.username
        if form.validate_on_submit():
            amka=(form.amka.data or '').strip() or None
            new_username=(form.username.data or '').strip()
            new_password=form.password.data or ''
            other=User.query.filter_by(username=new_username).first() if new_username else None
            if amka and Client.query.filter(Client.amka==amka,Client.id!=c.id).first():
                flash('Το ΑΜΚΑ ανήκει σε άλλον πελάτη','danger')
            elif new_username and other and (not account or other.id!=account.id):
                flash('Το όνομα χρήστη χρησιμοποιείται από άλλον λογαριασμό','danger')
            elif not account and bool(new_username)!=bool(new_password):
                flash('Για νέα πρόσβαση πελάτη χρειάζονται username και password μαζί','danger')
            elif account and not new_username:
                flash('Ο υπάρχων λογαριασμός χρειάζεται username','danger')
            else:
                c.full_name=form.full_name.data
                c.amka=amka
                c.phone=form.phone.data
                c.email=form.email.data
                c.sms_consent=form.sms_consent.data
                c.email_consent=form.email_consent.data
                if not account and new_username and new_password:
                    account=User(username=new_username,password_hash=generate_password_hash(new_password),role='client',client_id=c.id)
                    db.session.add(account)
                elif account:
                    account.username=new_username
                    if new_password:
                        account.password_hash=generate_password_hash(new_password)
                db.session.commit()
                flash('Η καρτέλα και η πρόσβαση πελάτη ενημερώθηκαν','success')
                return redirect(url_for('edit_client',client_id=c.id))
        return render_template('admin/edit_client.html',form=form,client=c,account=account)
    @app.route('/admin/clients/<int:client_id>/prescriptions',methods=['GET','POST'])
    @login_required
    def prescriptions(client_id):
        admin_only()
        c = db.get_or_404(Client, client_id)
        form = PrescriptionForm()
        if form.validate_on_submit():
            db.session.add(Prescription(client_id=c.id, title=form.title.data,
                opens_on=form.opens_on.data, notes=form.notes.data, active=form.active.data))
            db.session.commit()
            flash('Η συνταγή αποθηκεύτηκε', 'ok')
            return redirect(url_for('prescriptions', client_id=c.id))
        items = Prescription.query.filter_by(client_id=c.id).order_by(Prescription.opens_on.desc()).all()
        logs = (NotificationLog.query.filter(NotificationLog.channel == 'sms',
                    NotificationLog.prescription_id.in_([p.id for p in items]))
                .order_by(NotificationLog.id.desc()).all()) if items else []
        latest = {}
        for log in logs:
            latest.setdefault(log.prescription_id, log)
        rows = [{'item': p, 'log': latest.get(p.id),
                 'blockers': sms_blockers(p, existing_log=latest.get(p.id))} for p in items]
        return render_template('admin/prescriptions.html', client=c, form=form,
            rows=rows, sms=sms_settings(), today=local_today())
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
    @app.route('/admin/messages')
    @login_required
    def admin_messages():
        admin_only()
        q=request.args.get('q','').strip()
        client_query=Client.query
        if q:
            client_query=client_query.filter(or_(
                Client.full_name.ilike('%'+q+'%'), Client.amka.ilike('%'+q+'%'),
                Client.phone.ilike('%'+q+'%')))
        target_clients=client_query.order_by(Client.full_name).limit(100).all()
        latest=(db.session.query(Message,Client.full_name)
                .join(Client,Message.client_id==Client.id)
                .order_by(Message.id.desc()).limit(30).all())
        return render_template('admin/message_center.html', clients=target_clients,
                               q=q,latest=latest,count=Message.query.count())
    @app.route('/admin/clients/<int:client_id>/messages',methods=['GET','POST'])
    @login_required
    def messages(client_id):
        admin_only();c=db.get_or_404(Client,client_id);form=MessageForm()
        if form.validate_on_submit():
            db.session.add(Message(client_id=c.id,body=form.body.data));db.session.commit();flash('Το μήνυμα αποθηκεύτηκε και εμφανίζεται στην προσωπική καρτέλα του πελάτη. Δεν στάλθηκε SMS.','success');return redirect(url_for('messages',client_id=c.id))
        account=User.query.filter_by(client_id=c.id,role='client').first()
        return render_template('admin/messages.html',client=c,form=form,account=account,items=Message.query.filter_by(client_id=c.id).order_by(Message.id.desc()).all())
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
