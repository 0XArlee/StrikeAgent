-- 2026-10-20: builder connect (users' agents trading on their own Strike account). Apply once per database.
-- live_keys: public keys of API-wallet pairs generated on the agents' host (private keys never leave it)
CREATE TABLE IF NOT EXISTS live_keys (
  pub TEXT PRIMARY KEY,
  env TEXT NOT NULL,                   -- testnet | mainnet
  status TEXT NOT NULL DEFAULT 'free', -- free | pending | active | revoked (a key handed out is never offered again)
  user_id TEXT,
  account_id TEXT,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS live_keys_free ON live_keys (env, status);
-- live_sessions: one Strike request-signature waiting for the user's wallet signature (5 min, single use)
CREATE TABLE IF NOT EXISTS live_sessions (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  pub TEXT NOT NULL,
  env TEXT NOT NULL,
  nonce TEXT NOT NULL,
  address TEXT NOT NULL,
  message TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  used INTEGER NOT NULL DEFAULT 0
);
-- live_links: the user's agent trades on their Strike account through this API wallet
CREATE TABLE IF NOT EXISTS live_links (
  user_id TEXT PRIMARY KEY,
  env TEXT NOT NULL,
  pub TEXT NOT NULL,
  account_id TEXT NOT NULL,
  fee_bps INTEGER NOT NULL,
  status TEXT NOT NULL,                -- active | off
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
