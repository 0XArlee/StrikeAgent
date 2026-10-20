-- 2026-10-20: the audit trail, for claims. Every owner action and what the site answered, with the exact message the
-- wallet signed and the signature (proof of consent: builder fee, settings, tests...). Append-only: the triggers refuse
-- any change or deletion, and deleting an agent keeps its rows. The agents' host copies the rows every minute
-- (runs/web-audit-<env>.jsonl) and sends the heads of its own logs (audit_anchors).
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
