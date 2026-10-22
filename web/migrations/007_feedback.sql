-- 2026-10-22: suggestions and feedback from the site (web/server/feedback.ts). Apply once, QA first:
-- wrangler d1 execute smartflow-city-qa --remote --file migrations/007_feedback.sql   (then smartflow-city)
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
