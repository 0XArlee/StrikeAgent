-- 2026-10-20: the owner asks their live agent for a test trade (the minimum size, held ~2 minutes); the host runs it.
ALTER TABLE live_links ADD COLUMN test_at INTEGER;
