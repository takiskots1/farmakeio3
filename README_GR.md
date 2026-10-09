# CHRYSPHARMACY v2 — Raspberry Pi / PostgreSQL

## Τι περιλαμβάνει
- Flask application factory, σωστοί φάκελοι services/templates/static
- Login διαχειριστή και πελάτη, κωδικοί hashed, CSRF
- Πελάτες: όνομα, ΑΜΚΑ 11 ψηφία, κινητό, email, συναίνεση ανά κανάλι, αναζήτηση ΑΜΚΑ
- Συνταγές: περιγραφή, ημερομηνία ανοίγματος, κατάσταση, εσωτερικές σημειώσεις
- Portal πελάτη, μηνύματα διαχειριστή
- SMS.to POST /sms/send Bearer token και SMTP email, καταγραφή αποδοχής/σφάλματος
- Χειροκίνητος έλεγχος και cron. Δεν στέλνει αυτόματα με το άνοιγμα του site.

## 1. Backup ΠΡΙΝ ΑΠΟ ΟΤΙΔΗΠΟΤΕ
Σταμάτησε την παλιά εφαρμογή. Αν η παλιά βάση λέγεται `chryspharmacy`:

```bash
mkdir -p ~/pharmacy_backups
pg_dump -h 127.0.0.1 -U postgres -Fc -d chryspharmacy -f ~/pharmacy_backups/chryspharmacy_before_v2.dump
ls -lh ~/pharmacy_backups/chryspharmacy_before_v2.dump
```

Αν χρησιμοποιείς διαφορετικό PostgreSQL χρήστη/βάση, άλλαξε τα αντίστοιχα ονόματα. **Μην συνεχίσεις αν το backup απέτυχε.** Μην αποθηκεύεις αντίγραφα με προσωπικά δεδομένα σε δημόσιο χώρο.

## 2. Προτεινόμενη ασφαλής εγκατάσταση: ΝΕΑ ΒΑΣΗ
Η δομή της προηγούμενης βάσης δεν έχει επιβεβαιωθεί. **Μην κάνεις init-db στην παλιά βάση** και μην θεωρήσεις ότι το SQL migration μόνο του αρκεί. Δημιούργησε πρώτα ξεχωριστή βάση και έλεγξε την εφαρμογή.

```bash
sudo -u postgres psql
```
Στο prompt της PostgreSQL:

```sql
CREATE USER chrys_user_v2 WITH PASSWORD 'ΒΑΛΕ_ΕΝΑ_ΙΣΧΥΡΟ_ΚΩΔΙΚΟ';
CREATE DATABASE chryspharmacy_v2 OWNER chrys_user_v2;
\q
```

## 3. Εγκατάσταση στο Raspberry Pi
Αποσυμπίεσε το ZIP σε νέο φάκελο (όχι επάνω στην παλιά εφαρμογή). Από το νέο project:

```bash
cd ~/Documents/farmakeio/chryspharmacy_v2
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"
nano .env
```

Συμπλήρωσε `SECRET_KEY`, `DATABASE_URL=postgresql+psycopg2://chrys_user_v2:...@127.0.0.1:5432/chryspharmacy_v2`. Αν ο κωδικός έχει ειδικούς χαρακτήρες, πρέπει να γίνει URL-encoding. Κράτησε `SMS_ENABLED=false`, `EMAIL_ENABLED=false` για τις δοκιμές.

```bash
chmod 600 .env
flask --app app:create_app init-db
flask --app app:create_app create-admin
flask --app app:create_app run --host 127.0.0.1 --port 5001
```

Για πρόσβαση από άλλη συσκευή του **έμπιστου τοπικού δικτύου** δοκίμασε προσωρινά `--host 0.0.0.0`. Το development server δεν προορίζεται για παραγωγή/Internet. Για πραγματικά στοιχεία πελατών απαιτείται HTTPS, κατάλληλη αυθεντικοποίηση, backups, περιορισμός πρόσβασης και ασφαλής παραγωγικός server.

## 4. SMS.to
Από SMS.to > API Clients δημιούργησε API Key. Στο `.env`:

```dotenv
SMS_TO_API_KEY=YOUR_REAL_API_KEY
SMS_SENDER_ID=CHRYSPHARM
SMS_ENABLED=true
```

Το `sender_id` υπόκειται στους κανόνες/εγκρίσεις του παρόχου. Τα κινητά δέχονται `69xxxxxxxx`, `003069xxxxxxxx` ή `+3069xxxxxxxx`. Ο λογαριασμός χρειάζεται διαθέσιμο υπόλοιπο. Η αποστολή γίνεται με HTTPS POST `https://api.sms.to/sms/send`, Authorization Bearer. Δεν υπάρχει live δοκιμή με πραγματικό API key σε αυτό το πακέτο.

**Προσοχή:** Η ένδειξη `queued` σημαίνει αποδοχή από το SMS.to, **όχι παράδοση στο κινητό**. Για επιβεβαίωση παράδοσης χρειάζεται επόμενη υλοποίηση με ασφαλή status webhook. Αν ο πάροχος δεχτεί SMS αλλά διακοπεί η σύνδεση πριν λάβουμε απάντηση, η καταγραφή μπορεί να δείχνει αποτυχία· γι' αυτό οι αποτυχίες **δεν επαναστέλλονται αυτόματα**.

## 5. Email
Στο `.env` ορίζεις SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM και EMAIL_ENABLED=true. Οι πελάτες πρέπει να έχουν έγκυρο email και ενεργή συναίνεση.

## 6. Αυτόματος ημερήσιος έλεγχος
Πρώτα δοκίμασε χειροκίνητα από το admin ή:

```bash
cd ~/Documents/farmakeio/chryspharmacy_v2
.venv/bin/flask --app app:create_app send-due
```

Έπειτα `crontab -e` και πρόσθεσε (08:30 ώρα Raspberry Pi):

```cron
30 8 * * * cd /home/takis/Documents/farmakeio/chryspharmacy_v2 && /home/takis/Documents/farmakeio/chryspharmacy_v2/.venv/bin/flask --app app:create_app send-due >> /home/takis/chryspharmacy_cron.log 2>&1
```

Έλεγξε `timedatectl` για ζώνη ώρας `Europe/Athens`. Μία εγγραφή ανά συνταγή/ημέρα/κανάλι εμποδίζει επαναλαμβανόμενες αυτόματες αποστολές. Η εφαρμογή **δεν** δημιουργεί μόνη της νέες μηνιαίες ημερομηνίες: κάθε νέα συνταγή χρειάζεται νέα ημερομηνία.

## 7. Υπάρχουσα PostgreSQL βάση — αλλαγή ΑΜΚΑ
ΠΡΩΤΑ έλεγξε τη δομή της παλιάς βάσης:

```bash
psql -h 127.0.0.1 -U postgres -d chryspharmacy -c '\d+ public.clients'
psql -h 127.0.0.1 -U postgres -d chryspharmacy -c '\dt'
```

Αν υπάρχει πίνακας `public.clients` και μόνο το πεδίο ΑΜΚΑ λείπει, μπορείς να προσθέσεις **μόνο** το πεδίο στην ΠΑΛΙΑ βάση, αφού έχεις επιτυχές backup:

```bash
psql -v ON_ERROR_STOP=1 -1 -h 127.0.0.1 -U postgres -d chryspharmacy -f migrations/001_add_amka_existing_clients.sql
```

**Αυτό το migration ΔΕΝ μετατρέπει ολόκληρη την παλιά βάση στη νέα δομή**. Για μεταφορά παλιών πελατών, συνταγών, χρηστών και μηνυμάτων χρειάζεται αντιστοίχιση με τα πραγματικά παλιά πεδία και προσεκτικό migration. Δεν κάνουμε `DROP TABLE`, `db.drop_all()` ή αντιγραφή στα τυφλά. Εφόσον οι πίνακες διαφέρουν, άφησε την παλιά βάση ανέπαφη και χρησιμοποίησε τη νέα βάση για δοκιμές.

## 8. Ασφάλεια και προστασία δεδομένων
Το ΑΜΚΑ είναι ευαίσθητο αναγνωριστικό. Η αναζήτηση/εμφάνισή του επιτρέπεται μόνο στον διαχειριστή. Δεν μπαίνει σε SMS/email, ούτε σε logs αποστολής. Εξασφάλισε κατάλληλη νομική βάση επεξεργασίας και τεκμηριωμένη συγκατάθεση για ειδοποιήσεις, όπου απαιτείται. Η εφαρμογή είναι λειτουργικό starter, **όχι πιστοποιημένη παραγωγική λύση**. Πριν χρησιμοποιηθεί με πραγματικά δεδομένα χρειάζεται έλεγχος ασφαλείας, HTTPS, πολιτική διατήρησης, κρυπτογράφηση αντιγράφων και διαχείριση πρόσβασης.
