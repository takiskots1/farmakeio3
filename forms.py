import re
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, DateField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Optional, Length, Email, ValidationError
class LoginForm(FlaskForm):
    username=StringField('Όνομα χρήστη',validators=[DataRequired()])
    password=PasswordField('Κωδικός',validators=[DataRequired()])
    submit=SubmitField('Σύνδεση')
class ClientForm(FlaskForm):
    full_name=StringField('Ονοματεπώνυμο',validators=[DataRequired(),Length(max=150)])
    amka=StringField('ΑΜΚΑ (11 ψηφία)',validators=[Optional(),Length(min=11,max=11)])
    phone=StringField('Κινητό',validators=[Optional(),Length(max=30)])
    email=StringField('Email',validators=[Optional(),Email()])
    sms_consent=BooleanField('Συγκατάθεση για SMS υπενθυμίσεις')
    email_consent=BooleanField('Συγκατάθεση για email υπενθυμίσεις')
    username=StringField('Username πελάτη (προαιρετικό)',validators=[Optional(),Length(max=100)])
    password=PasswordField('Αρχικός κωδικός (για νέο login)')
    submit=SubmitField('Αποθήκευση')
    def validate_amka(self,field):
        if field.data and not re.fullmatch(r'\d{11}',field.data): raise ValidationError('Το ΑΜΚΑ πρέπει να έχει 11 ψηφία.')
class PrescriptionForm(FlaskForm):
    title=StringField('Περιγραφή',validators=[DataRequired(),Length(max=150)])
    opens_on=DateField('Ημερομηνία ανοίγματος',format='%Y-%m-%d',validators=[DataRequired()])
    notes=TextAreaField('Εσωτερικές σημειώσεις')
    active=BooleanField('Ενεργή',default=True)
    submit=SubmitField('Αποθήκευση')
class MessageForm(FlaskForm):
    body=TextAreaField('Μήνυμα',validators=[DataRequired(),Length(min=1,max=3000)])
    portal=BooleanField('Στην προσωπική καρτέλα',default=True)
    sms=BooleanField('SMS μέσω SMS.to')
    email=BooleanField('Email μέσω SMTP')
    push=BooleanField('Push notification στη συσκευή')
    submit=SubmitField('Καταχώριση και αποστολή')

class ClientReplyForm(FlaskForm):
    body=TextAreaField('Το μήνυμά σας',validators=[DataRequired(),Length(min=2,max=2000)])
    submit=SubmitField('Αποστολή στο φαρμακείο')
