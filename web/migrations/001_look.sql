-- 2026-10-19: the character creator. Apply once: wrangler d1 execute smartflow-city --remote --file migrations/001_look.sql
ALTER TABLE users ADD COLUMN look TEXT;
