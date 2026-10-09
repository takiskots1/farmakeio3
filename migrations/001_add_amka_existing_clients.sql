-- ΜΟΝΟ για συμβατή υπάρχουσα βάση με πίνακα public.clients.
-- ΠΡΩΤΑ pg_dump. Εκτέλεση με psql -v ON_ERROR_STOP=1 -1 -f ...
ALTER TABLE public.clients ADD COLUMN IF NOT EXISTS amka VARCHAR(11);
CREATE UNIQUE INDEX IF NOT EXISTS uq_clients_amka ON public.clients(amka);
-- Δεν αλλάζει παλιές εγγραφές ούτε διαγράφει δεδομένα.
