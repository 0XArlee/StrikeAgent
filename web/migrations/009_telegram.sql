-- 2026-10-23: alerts on Telegram (web/server/telegram.ts; smartflow/alerts on the agents' host).
-- Apply once, QA first: wrangler d1 execute smartflow-city-qa --remote --file migrations/009_telegram.sql (then smartflow-city)
CREATE TABLE IF NOT EXISTS tg_links (
  code TEXT PRIMARY KEY,       -- one use, ten minutes: made with the owner's session, sent to the bot as /start <code>
  user_id TEXT NOT NULL,
  lang TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  claimed_at INTEGER           -- when the bot used it
);
CREATE TABLE IF NOT EXISTS tg_chats (
  user_id TEXT NOT NULL,
  chat TEXT NOT NULL,          -- the Telegram chat the bot writes to about this owner's agent
  label TEXT NOT NULL,         -- its name as Telegram gives it, shown to the owner in the Alerts tab
  linked_at INTEGER NOT NULL,
  PRIMARY KEY (user_id, chat)
);
