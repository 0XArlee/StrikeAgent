-- 2026-10-22: copy with your agent (web/server/copyplan.ts; smartflow/copytrade/pilot.py on the agents' host).
-- Apply once, QA first: wrangler d1 execute smartflow-city-qa --remote --file migrations/008_copy.sql (then smartflow-city)
CREATE TABLE IF NOT EXISTS copy_plans (
  user_id TEXT PRIMARY KEY,
  env TEXT NOT NULL,           -- testnet (QA) or mainnet
  plan TEXT NOT NULL,          -- JSON: whom (manual or pilot), how much, stop-loss, leverage, markets never opened, until, alarm pause
  version INTEGER NOT NULL,    -- each signed change: the host acts on a version once
  updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS copy_status (
  user_id TEXT PRIMARY KEY,
  body TEXT NOT NULL,          -- JSON the host reports: copying whom, since, its sub-account, PnL, why, its latest decisions
  updated_at INTEGER NOT NULL
);
