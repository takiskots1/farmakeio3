-- Non-destructive upgrade from CHRYSPHARMACY v2.2 to v2.3.
-- Take pg_dump backup first. Run ONCE using the same PostgreSQL database.
BEGIN;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS direction VARCHAR(20) NOT NULL DEFAULT 'admin_to_client';
ALTER TABLE messages ADD COLUMN IF NOT EXISTS read_at TIMESTAMP WITH TIME ZONE NULL;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS portal_visible BOOLEAN NOT NULL DEFAULT TRUE;
CREATE INDEX IF NOT EXISTS ix_messages_direction ON messages (direction);
CREATE TABLE IF NOT EXISTS message_deliveries (
  id SERIAL PRIMARY KEY,
  message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
  channel VARCHAR(12) NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'processing',
  provider_id VARCHAR(120),
  error VARCHAR(300),
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT uq_message_delivery_channel UNIQUE (message_id, channel)
);
CREATE INDEX IF NOT EXISTS ix_message_deliveries_message_id ON message_deliveries (message_id);
CREATE TABLE IF NOT EXISTS push_subscriptions (
  id SERIAL PRIMARY KEY,
  client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  endpoint TEXT NOT NULL UNIQUE,
  p256dh TEXT NOT NULL,
  auth TEXT NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_push_subscriptions_client_id ON push_subscriptions (client_id);
COMMIT;
