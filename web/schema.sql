-- Strike City (Cloudflare D1). Apply: wrangler d1 execute smartflow-city --remote --file schema.sql
-- users: one paper agent per Cardano wallet; public = shown in Strike City (the owner's choice, off unless chosen).
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,                 -- "u-" + 12 hex of SHA-256(address): stable across sign-ins
  address TEXT NOT NULL UNIQUE,        -- bech32, ownership proven with a CIP-30 signature
  name TEXT NOT NULL,
  risk TEXT NOT NULL,                  -- conservative | standard | assertive
  markets TEXT NOT NULL,               -- JSON array of Strike markets
  public INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'active',   -- active | paused
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  look TEXT,                           -- the character (JSON, validated by web/src/city/look.ts)
  persona TEXT,                        -- personality and trade in the city (JSON, web/src/city/persona.ts)
  strategy TEXT NOT NULL DEFAULT 'smartflow'   -- smartflow | pyramid
);
-- databases created before 2026-10-19 (look column): migrations/001_look.sql; before 2026-10-20 (strategy): 003
-- challenges: one-time messages to sign (5 min, single use)
CREATE TABLE IF NOT EXISTS challenges (
  id TEXT PRIMARY KEY,
  address TEXT NOT NULL,
  kind TEXT NOT NULL,                  -- connect | action
  payload TEXT NOT NULL,
  message TEXT NOT NULL,
  ip TEXT,
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  used INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS challenges_ip ON challenges (ip, created_at);
CREATE INDEX IF NOT EXISTS challenges_address ON challenges (address, created_at);
-- events: what the owner did (start, pause, resume, show, hide)
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL,
  time INTEGER NOT NULL,
  code TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_user ON events (user_id, time);
-- snapshots: the real agents' public state, pushed by the agents' host
CREATE TABLE IF NOT EXISTS snapshots (
  key TEXT PRIMARY KEY,
  body TEXT NOT NULL,
  updated_at INTEGER NOT NULL
);
-- builder connect (migrations/002_live.sql)
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
  updated_at INTEGER NOT NULL,
  test_at INTEGER                      -- the owner asked for a test trade at (ms); migrations/004_test_trade.sql
);
-- audit trail (migrations/005_audit.sql): every owner action with the signed message; append-only
CREATE TABLE IF NOT EXISTS audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  time INTEGER NOT NULL,
  env TEXT NOT NULL,
  user_id TEXT,
  address TEXT,
  action TEXT NOT NULL,    -- create | signin | pause | resume | show | hide | look | settings | test | revoke | live_connect | live_off
  ok INTEGER NOT NULL,     -- 0: refused (the reason in detail.error)
  detail TEXT,             -- JSON: what changed, before and after, Strike's answer
  message TEXT,            -- the exact text the wallet signed
  signature TEXT,          -- the wallet's CIP-30 signature, as sent
  ip TEXT,                 -- shortened: /24 (IPv4) or /48 (IPv6)
  country TEXT
);
CREATE INDEX IF NOT EXISTS audit_user ON audit (user_id, time);
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit BEGIN SELECT RAISE(ABORT, 'audit is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit BEGIN SELECT RAISE(ABORT, 'audit is append-only'); END;
-- audit_anchors: the head (seq, hash) of each tamper-evident log on the agents' host, as it was at `time`
CREATE TABLE IF NOT EXISTS audit_anchors (
  file TEXT NOT NULL,
  seq INTEGER NOT NULL,
  hash TEXT NOT NULL,
  time INTEGER NOT NULL,
  PRIMARY KEY (file, seq)
);
CREATE TRIGGER IF NOT EXISTS anchors_no_update BEFORE UPDATE ON audit_anchors BEGIN SELECT RAISE(ABORT, 'anchors are append-only'); END;
CREATE TRIGGER IF NOT EXISTS anchors_no_delete BEFORE DELETE ON audit_anchors BEGIN SELECT RAISE(ABORT, 'anchors are append-only'); END;
CREATE TABLE IF NOT EXISTS feedback (
  id TEXT PRIMARY KEY,
  created_at INTEGER NOT NULL,
  subject TEXT NOT NULL,
  message TEXT NOT NULL,
  image TEXT,              -- data:image/...;base64 (the page shrinks it under 1 MB)
  page TEXT, lang TEXT,
  user_id TEXT,            -- the agent of whoever sent it, if they were signed in
  ua TEXT,
  ip_net TEXT,             -- the sender's network (/24, /48), only to limit how many an hour
  read_at INTEGER,         -- an admin read it in My agent
  sent_at INTEGER          -- the agents' host sent it to the operator's phone
);
CREATE INDEX IF NOT EXISTS feedback_time ON feedback (created_at);
CREATE INDEX IF NOT EXISTS feedback_unsent ON feedback (sent_at);
