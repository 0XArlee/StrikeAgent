-- 2026-10-22: the agent's personality and trade in the city (web/src/city/persona.ts). Apply once:
-- wrangler d1 execute smartflow-city --remote --file migrations/006_persona.sql (QA first: smartflow-city-qa)
ALTER TABLE users ADD COLUMN persona TEXT;
