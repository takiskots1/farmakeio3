# CHRYSPHARMACY v2.3 — Μηνύματα SMS, email, Web Push και αμφίδρομη επικοινωνία

Αυτή είναι **αναβάθμιση της v2.2**, με το ίδιο μωβ/πετρόλ/χρυσό CSS και τις ίδιες λειτουργίες πελατών, συνταγών, AMKA, SMS.to και dashboard. Δεν εγκαθιστούμε νέα βάση, δεν ξαναδημιουργούμε admin και **δεν τρέχουμε `init-db` πάνω στην υπάρχουσα βάση αντί της migration**.

## Τι προστέθηκε

- **Διαχειριστής → Κέντρο μηνυμάτων → πελάτης:** σύνταξη μηνύματος και επιλογή ενός ή πολλών: καρτέλα πελάτη, SMS.to, email SMTP, Web Push. Κατάσταση αποστολής ανά κανάλι και έλεγχοι επιλεξιμότητας πριν την αποστολή.
- **Πελάτης → /client:** «Στείλτε μήνυμα στο φαρμακείο». Τα εισερχόμενα αποθηκεύονται, εμφανίζονται στο dashboard και στη νέα καρτέλα **Εισερχόμενα πελατών**, σημειώνονται ως διαβασμένα όταν ο admin ανοίξει τη συνομιλία και μπορούν να απαντηθούν.
- **Web Push:** ο πελάτης ενεργοποιεί ο ίδιος ειδοποιήσεις ανά browser/συσκευή. Οι push προεπισκοπήσεις είναι γενικές και δεν περιέχουν ιατρικές πληροφορίες.
- Δεν γίνονται αυτόματες αποστολές email/SMS/push όταν ο πελάτης γράφει στον admin. Ο admin βλέπει το μήνυμα στο dashboard και αποφασίζει πώς θα απαντήσει.

## Α. Backup της PostgreSQL — ΠΡΙΝ ΑΛΛΑΞΕΙΣ ΟΤΙΔΗΠΟΤΕ

Από το Raspberry Pi, επιβεβαίωσε την **πραγματική** βάση που χρησιμοποιείς στο `.env` της v2.2. Παράδειγμα, αν η βάση ονομάζεται `chryspharmacy_v2` και το username `chrys_user_v2`:

```bash
mkdir -p ~/Documents/farmakeio/backups
pg_dump -h 127.0.0.1 -U chrys_user_v2 -d chryspharmacy_v2 -Fc \
  -f ~/Documents/farmakeio/backups/chryspharmacy_pre_v23.dump
ls -lh ~/Documents/farmakeio/backups/chryspharmacy_pre_v23.dump
```

**Αν τα δικά σου ονόματα είναι διαφορετικά, άλλαξέ τα.** Το dump μπορεί να περιέχει ΑΜΚΑ, τηλέφωνα και μηνύματα — φύλαξέ το ασφαλώς (`chmod 600`).

## Β. Αποσυμπίεση — διατήρηση του `.env`

```bash
cd ~/Documents/farmakeio
unzip chryspharmacy_v2_3_messages_push.zip
cd chryspharmacy_v2_3
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp ../chryspharmacy_v2_2/.env .env
chmod 600 .env
```

Αν δεν έχεις ακριβώς αυτούς τους φακέλους, προσαρμόζεις μόνο τις διαδρομές `unzip` και `cp`. **Μην αντιγράφεις παλιό `app.py`, `models.py`, `templates`, `services` πάνω από τα καινούργια.**

Για Python **3.9** στο Raspberry Pi χρησιμοποιείται `pywebpush==1.14.1` (οι νεότερες 2.x εκδόσεις απαιτούν Python 3.10+).

## Γ. PostgreSQL migration 2.2 → 2.3 (απαραίτητη)

Η έκδοση χρησιμοποιεί τους **ίδιους** πίνακες `users`, `clients`, `prescriptions`, `messages`, `notification_logs` και προσθέτει:

- `messages.direction` (`admin_to_client` ή `client_to_admin`), με default `admin_to_client` ώστε τα παλιά μηνύματα να διατηρηθούν σωστά.
- `messages.read_at` για αναγνωσμένα εισερχόμενα.
- `messages.portal_visible` (default `TRUE`) ώστε παλιά μηνύματα να συνεχίσουν να εμφανίζονται στον πελάτη.
- Νέους πίνακες `message_deliveries` και `push_subscriptions`.

**Σταμάτα την παλιά v2.2 εφαρμογή** (Ctrl+C ή stop της αντίστοιχης υπηρεσίας). Με ενεργό το νέο virtualenv, εκτέλεσε:

```bash
cd ~/Documents/farmakeio/chryspharmacy_v2_3
python -m flask --app app:create_app upgrade-v23
```

Η εντολή διαβάζει το SQL `migrations/002_messaging_channels_v23.sql`, που χρησιμοποιεί `ADD COLUMN IF NOT EXISTS`/`CREATE TABLE IF NOT EXISTS` και δεν διαγράφει παλιά δεδομένα. Είναι σχεδιασμένη ώστε να είναι επαναλήψιμη, αλλά να τρέξει πρώτα σε backup/δοκιμαστική βάση αν είναι δυνατό.

Εναλλακτικά, μόνο εφόσον χρησιμοποιείς `psql` και **την ίδια** βάση:

```bash
psql -h 127.0.0.1 -U chrys_user_v2 -d chryspharmacy_v2 \
  -v ON_ERROR_STOP=1 -f migrations/002_messaging_channels_v23.sql
```

**Δεν χρειάζεται να τρέξεις και τις δύο εντολές.** Μετά, προαιρετικός έλεγχος:

```bash
psql -h 127.0.0.1 -U chrys_user_v2 -d chryspharmacy_v2 -c '\d messages'
psql -h 127.0.0.1 -U chrys_user_v2 -d chryspharmacy_v2 -c '\dt *message*'
psql -h 127.0.0.1 -U chrys_user_v2 -d chryspharmacy_v2 -c '\dt push_subscriptions'
```

Προσοχή: για εκτέλεση της migration ο χρήστης PostgreSQL πρέπει να έχει δικαιώματα `ALTER`/`CREATE` στους αντίστοιχους πίνακες και schema.

## Δ. `.env` — SMS.to, email, Push

Κράτησε το πραγματικό `SECRET_KEY` και `DATABASE_URL` της v2.2. Πρόσθεσε/επιβεβαίωσε:

```dotenv
SMS_ENABLED=true
SMS_TO_API_KEY=TO_DIΚO_SOU_API_KEY
SMS_SENDER_ID=CHRYSPHARM

EMAIL_ENABLED=true
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=your_email@example.com
SMTP_PASSWORD=APP_PASSWORD
SMTP_FROM=your_email@example.com
SMTP_STARTTLS=true

# Συμπλήρωσε τα VAPID παρακάτω σύμφωνα με το Βήμα Ε
VAPID_PRIVATE_KEY=instance/vapid_private.pem
VAPID_PUBLIC_KEY=
VAPID_CONTACT=mailto:info@chryspharmacy.gr
```

Η αποστολή SMS γίνεται μέσω της υπάρχουσας υπηρεσίας SMS.to. Το email χρησιμοποιεί SMTP. Απαιτούνται έγκυρο κινητό/email και η σχετική συναίνεση που είναι αποθηκευμένη στην καρτέλα πελάτη. Μην κοινοποιήσεις API key, SMTP password ή πλήρες `.env`.

## Ε. Web Push: δημιουργία VAPID κλειδιών

```bash
cd ~/Documents/farmakeio/chryspharmacy_v2_3
source .venv/bin/activate
python scripts/generate_vapid.py
```

Η εντολή δημιουργεί μία φορά το `instance/vapid_private.pem` και εμφανίζει τιμές `VAPID_PRIVATE_KEY`, `VAPID_PUBLIC_KEY`, `VAPID_CONTACT`. Αντίγραψε τις τιμές στο `.env`. Το αρχείο ιδιωτικού κλειδιού έχει περιορισμένα permissions. **Μην το διαγράψεις/αναδημιουργήσεις** μετά την εγγραφή πελατών, επειδή οι παλιές push συνδρομές θα πάψουν να δουλεύουν.

**HTTPS είναι υποχρεωτικό για πραγματικά Web Push από κινητά ή άλλους υπολογιστές**. Το `http://192.168.1.30:5001` δεν είναι ασφαλές origin και ο browser δεν επιτρέπει Service Worker/Push API. Για δοκιμή στο ίδιο το Raspberry Pi μπορεί να λειτουργήσει το `http://localhost:5001` ανά browser. Για πρόσβαση από δίκτυο/ίντερνετ χρειάζεται HTTPS με έγκυρο πιστοποιητικό και reverse proxy (π.χ. Caddy/Nginx), καθώς και ασφαλές authentication. Μην εκθέσεις το Flask development server δημόσια.

Οι χρήστες εγγράφονται μέσα από την προσωπική τους καρτέλα πατώντας **Ενεργοποίηση push** και επιτρέποντας browser notifications. Η συνδρομή γίνεται σε κάθε συσκευή χωριστά. Στο iOS συνήθως απαιτείται να προστεθεί η εφαρμογή στην αρχική οθόνη από Safari (Share → Add to Home Screen). Για αυτό το ZIP περιλαμβάνει και `manifest.webmanifest` με τα εικονίδια 192/512.

## ΣΤ. Εκκίνηση

```bash
cd ~/Documents/farmakeio/chryspharmacy_v2_3
source .venv/bin/activate
python -m flask --app app:create_app run --host 0.0.0.0 --port 5001
```

Ακολούθησε αυτές τις δοκιμές χωρίς πραγματικά προσωπικά στοιχεία:

1. Σύνδεση ως admin → **Κέντρο μηνυμάτων** → επίλεξε δοκιμαστικό πελάτη → γράψε μήνυμα → επίλεξε **μόνο Portal**. Σύνδεση ως αυτός ο πελάτης → το μήνυμα πρέπει να εμφανιστεί.
2. Σύνδεση ως πελάτης → γράψε απάντηση → **Αποστολή στο φαρμακείο** → σύνδεση ως admin → `/admin` και `/admin/inbox`: πρέπει να εμφανιστεί ως νέο εισερχόμενο.
3. Άνοιξε την συνομιλία ως admin → το μήνυμα επισημαίνεται ως αναγνωσμένο.
4. Για SMS/email χρησιμοποίησε **δικό σου δοκιμαστικό κινητό/email**, κατάλληλη συναίνεση και συμπληρωμένα credentials. Στείλε από το Κέντρο μηνυμάτων. Μπορεί να υπάρξουν χρεώσεις.
5. Για push, άνοιξε μέσω HTTPS τη δοκιμαστική καρτέλα, επίτρεψε την εγγραφή συσκευής και στείλε νέο μήνυμα επιλέγοντας **Push**. Η ειδοποίηση έχει μόνο γενικό κείμενο.

## Ζ. Ασφάλεια / σημαντικοί περιορισμοί

- Το AMKA, οι λεπτομέρειες συνταγών και ευαίσθητα ιατρικά στοιχεία **δεν πρέπει** να στέλνονται σε απλό SMS/email ή σε push preview. Χρησιμοποίησε ουδέτερες ειδοποιήσεις και την προστατευμένη καρτέλα για την ουσιαστική επικοινωνία.
- Το υπάρχον πεδίο `sms_consent` / `email_consent` στην καρτέλα πρέπει να αντανακλά την πραγματική, κατάλληλη συναίνεση για τη χρήση που κάνεις (ιδίως για προωθητικές ενέργειες).
- Push subscription endpoints θεωρούνται εμπιστευτικά στοιχεία. Περιορίζεται ο τύπος provider URL και δεν εμφανίζονται στο frontend του admin.
- Εάν SMS.to δεχτεί μήνυμα, η κατάσταση `queued` δεν σημαίνει παραδομένο. Το `sent` για SMTP σημαίνει αποδοχή από το SMTP server, όχι ανάγνωση από παραλήπτη. Τα μηνύματα από πελάτη φτάνουν στο admin inbox **χωρίς επιπλέον SMS/email alert**.
- Αυτό το project είναι για τοπική/ελεγχόμενη χρήση και χρειάζεται έλεγχο ασφάλειας, απορρήτου, διαχείρισης αντιγράφων, HTTPS, session policy και κώδικα πριν χρησιμοποιηθεί ως παραγωγική υπηρεσία με ευαίσθητα δεδομένα. Το Flask development server **δεν** προορίζεται για production.

## Η. Δοκιμές χωρίς πραγματική αποστολή

Σε ξεχωριστό περιβάλλον ελέγχου (οι δοκιμές χρησιμοποιούν προσωρινή SQLite στη μνήμη, όχι την PostgreSQL), με τις εξαρτήσεις εγκατεστημένες:

```bash
python -m unittest discover -s tests -v
```

Οι δοκιμές κάνουν mock το SMS, άρα δεν στέλνουν πραγματικά μηνύματα.
