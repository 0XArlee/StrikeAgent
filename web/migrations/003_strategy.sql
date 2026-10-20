-- 2026-10-20: the strategy each user's agent runs (smartflow = the published one, pyramid = up to 3 stacked trades).
ALTER TABLE users ADD COLUMN strategy TEXT NOT NULL DEFAULT 'smartflow';
