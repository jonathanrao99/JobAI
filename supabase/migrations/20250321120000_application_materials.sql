-- LLM-generated outreach fields (see backend/db/migrations/add_application_materials.sql)

ALTER TABLE applications
  ADD COLUMN IF NOT EXISTS linkedin_note TEXT,
  ADD COLUMN IF NOT EXISTS cold_email TEXT,
  ADD COLUMN IF NOT EXISTS cold_email_subject TEXT;
