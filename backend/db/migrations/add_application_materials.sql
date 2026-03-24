-- LLM-generated outreach snippets for an application (run via POST /api/applications/{id}/prepare).
-- Apply in Supabase SQL Editor or via supabase/migrations peer file.

ALTER TABLE applications
  ADD COLUMN IF NOT EXISTS linkedin_note TEXT,
  ADD COLUMN IF NOT EXISTS cold_email TEXT,
  ADD COLUMN IF NOT EXISTS cold_email_subject TEXT;

COMMENT ON COLUMN applications.linkedin_note IS 'Short LinkedIn connection/DM note tailored to the role';
COMMENT ON COLUMN applications.cold_email IS 'Cold outreach email body to a hiring manager or recruiter';
COMMENT ON COLUMN applications.cold_email_subject IS 'Suggested subject line for cold_email';
