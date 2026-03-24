-- Forward migration: add LLM-extracted job description keywords (existing projects).
-- Run in Supabase SQL Editor if your jobs table predates this column.

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS jd_keywords TEXT[];

COMMENT ON COLUMN jobs.jd_keywords IS 'Skills/tools/domains extracted from JD by filter agent';
