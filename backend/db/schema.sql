-- ============================================================
--  Job Search Agent — Supabase Schema
--  Run this in Supabase SQL Editor (project → SQL Editor → New query)
--  Or via: python backend/db/migrate.py
-- ============================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";    -- Fuzzy text search
CREATE EXTENSION IF NOT EXISTS "vector";     -- pgvector for semantic search

-- ── ENUMS ────────────────────────────────────────────────────────────────

CREATE TYPE application_status AS ENUM (
  'queued',           -- Waiting to be applied
  'applied',          -- Application submitted
  'viewed',           -- ATS shows profile was viewed
  'response_received',-- Got any reply
  'phone_screen',     -- Phone/recruiter screen scheduled
  'technical',        -- Technical interview
  'final_round',      -- Final round interview
  'offer',            -- Received offer
  'rejected',         -- Got rejection
  'ghosted',          -- No response after 30 days
  'manual_required',  -- Agent couldn't complete, needs human
  'skipped'           -- Deliberately skipped
);

CREATE TYPE status_source AS ENUM (
  'gmail', 'linkedin', 'calendar', 'manual', 'ats_confirmation', 'agent'
);

CREATE TYPE outreach_channel AS ENUM (
  'linkedin_dm', 'linkedin_connection', 'email', 'x_dm'
);

CREATE TYPE failure_type AS ENUM (
  'captcha', 'login_wall', 'unexpected_field', 'timeout',
  'form_error', 'hallucination_risk', 'duplicate_detected',
  'ats_blocked', 'network_error', 'unknown'
);

CREATE TYPE contact_source AS ENUM (
  'apollo', 'phantombuster', 'linkedin_search', 'manual'
);

CREATE TYPE apply_type AS ENUM (
  'easy_apply',    -- LinkedIn/Indeed 1-click
  'full_ats'       -- Multi-step ATS form
);

CREATE TYPE resume_type AS ENUM (
  'base',          -- Your original resume
  'tailored'       -- AI-tailored version for a specific job
);

-- ── TABLE: jobs ──────────────────────────────────────────────────────────
-- Raw scraped jobs + AI scoring

CREATE TABLE jobs (
  id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  
  -- Core job data
  title                 TEXT NOT NULL,
  company               TEXT NOT NULL,
  location              TEXT,
  description           TEXT,
  job_url               TEXT UNIQUE NOT NULL,
  source_board          TEXT NOT NULL,       -- linkedin, indeed, greenhouse, lever, etc.
  ats_platform          TEXT,               -- workday, greenhouse, lever, ashby, etc.
  
  -- Dates
  posted_at             TIMESTAMPTZ,
  scraped_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  -- Deduplication
  dedup_hash            TEXT UNIQUE NOT NULL,  -- SHA256(company+title+location)
  
  -- AI scoring (from filter agent)
  ai_score              SMALLINT CHECK (ai_score BETWEEN 1 AND 10),
  ai_verdict            TEXT CHECK (ai_verdict IN ('APPLY', 'MAYBE', 'SKIP')),
  ai_reason             TEXT,
  ai_scored_at          TIMESTAMPTZ,
  
  -- Compensation
  salary_min            INTEGER,
  salary_max            INTEGER,
  salary_currency       TEXT DEFAULT 'USD',
  
  -- Job characteristics
  is_remote             BOOLEAN DEFAULT FALSE,
  requires_clearance    BOOLEAN DEFAULT FALSE,
  requires_sponsorship  BOOLEAN,
  company_size          TEXT,
  
  -- Company intelligence
  glassdoor_rating      FLOAT4,
  has_recent_layoffs    BOOLEAN DEFAULT FALSE,
  company_news          TEXT,                -- Recent news pulled by Claude
  
  -- Referral opportunity
  has_mutual_connection BOOLEAN DEFAULT FALSE,
  mutual_connection_name TEXT,
  
  -- Metadata
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_jobs_verdict ON jobs (ai_verdict);
CREATE INDEX idx_jobs_score ON jobs (ai_score DESC);
CREATE INDEX idx_jobs_company ON jobs (company);
CREATE INDEX idx_jobs_source ON jobs (source_board);
CREATE INDEX idx_jobs_scraped_at ON jobs (scraped_at DESC);
CREATE INDEX idx_jobs_posted_at ON jobs (posted_at DESC);
CREATE INDEX idx_jobs_trgm_title ON jobs USING GIN (title gin_trgm_ops);
CREATE INDEX idx_jobs_trgm_company ON jobs USING GIN (company gin_trgm_ops);

-- ── TABLE: resumes ───────────────────────────────────────────────────────
-- Base and AI-tailored resume versions

CREATE TABLE resumes (
  id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  
  version_name          TEXT NOT NULL,        -- e.g. "base_v1", "stripe_swe_2024"
  resume_type           resume_type NOT NULL DEFAULT 'base',
  file_path             TEXT NOT NULL,        -- Local path to .docx file
  
  -- For tailored resumes
  job_id                UUID REFERENCES jobs(id) ON DELETE SET NULL,
  diff_summary          TEXT,                 -- What Claude changed vs base
  keywords_added        TEXT[],              -- Keywords Claude inserted
  
  -- Performance tracking
  times_used            INTEGER DEFAULT 0,
  responses_received    INTEGER DEFAULT 0,
  response_rate         FLOAT4 GENERATED ALWAYS AS (
                          CASE WHEN times_used > 0 
                          THEN responses_received::float / times_used 
                          ELSE 0 END
                        ) STORED,
  
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_resumes_type ON resumes (resume_type);
CREATE INDEX idx_resumes_response_rate ON resumes (response_rate DESC);

-- ── TABLE: applications ──────────────────────────────────────────────────
-- Full application audit trail

CREATE TABLE applications (
  id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  job_id                UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  resume_id             UUID REFERENCES resumes(id),
  
  -- Status
  status                application_status NOT NULL DEFAULT 'queued',
  status_updated_at     TIMESTAMPTZ DEFAULT NOW(),
  status_source         status_source,
  
  -- Application details
  apply_type            apply_type,
  cover_letter          TEXT,
  
  -- Form Q&A (array of {question, answer, field_type} objects)
  form_qa               JSONB DEFAULT '[]'::JSONB,
  
  -- Timing
  applied_at            TIMESTAMPTZ,
  time_to_submit_secs   INTEGER,             -- How long the agent took
  
  -- Confirmation
  confirmation_url      TEXT,
  confirmation_code     TEXT,
  
  -- Notes
  notes                 TEXT,
  
  -- Metadata
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  -- One application per job
  CONSTRAINT unique_application_per_job UNIQUE (job_id)
);

CREATE INDEX idx_applications_status ON applications (status);
CREATE INDEX idx_applications_applied_at ON applications (applied_at DESC);
CREATE INDEX idx_applications_job_id ON applications (job_id);
CREATE INDEX idx_applications_resume_id ON applications (resume_id);

-- ── TABLE: status_events ─────────────────────────────────────────────────
-- Immutable event log for every application status change

CREATE TABLE status_events (
  id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  application_id        UUID NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
  
  -- Event data
  from_status           application_status,
  to_status             application_status NOT NULL,
  source                status_source NOT NULL,
  
  -- Raw content that triggered the change
  raw_content           TEXT,              -- Email body, LinkedIn message, etc.
  parsed_by_ai          BOOLEAN DEFAULT FALSE,
  ai_confidence         FLOAT4,           -- Claude's confidence in the parse (0-1)
  
  -- Manual input fields
  manual_note           TEXT,
  
  occurred_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_status_events_application ON status_events (application_id);
CREATE INDEX idx_status_events_occurred_at ON status_events (occurred_at DESC);
CREATE INDEX idx_status_events_source ON status_events (source);

-- ── TABLE: contacts ──────────────────────────────────────────────────────
-- Hiring managers and referral targets

CREATE TABLE contacts (
  id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  
  -- Identity
  name                  TEXT NOT NULL,
  title                 TEXT,
  company               TEXT NOT NULL,
  department            TEXT,
  seniority             TEXT,             -- IC, manager, director, VP, etc.
  
  -- Contact info
  linkedin_url          TEXT,
  email                 TEXT,
  email_verified        BOOLEAN DEFAULT FALSE,
  
  -- Source
  source                contact_source NOT NULL,
  apollo_id             TEXT,             -- Apollo.io internal ID
  
  -- Relevance
  relevance_rank        SMALLINT DEFAULT 1,  -- 1=direct HM, 2=skip-level, 3=recruiter
  is_mutual_connection  BOOLEAN DEFAULT FALSE,
  
  -- Status
  do_not_contact        BOOLEAN DEFAULT FALSE,
  do_not_contact_reason TEXT,
  
  -- Metadata
  found_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_contacts_company ON contacts (company);
CREATE INDEX idx_contacts_email ON contacts (email);
CREATE INDEX idx_contacts_do_not_contact ON contacts (do_not_contact);

-- ── TABLE: outreach ──────────────────────────────────────────────────────
-- Every outreach message sent

CREATE TABLE outreach (
  id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  contact_id            UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
  application_id        UUID REFERENCES applications(id) ON DELETE SET NULL,
  
  -- Message
  channel               outreach_channel NOT NULL,
  message_text          TEXT NOT NULL,
  subject_line          TEXT,              -- For emails
  
  -- Context Claude used
  company_news_snippet  TEXT,
  prompt_version        TEXT,             -- Which prompt template was used
  touch_number          SMALLINT DEFAULT 1,  -- 1st/2nd/3rd touch
  
  -- Timing
  sent_at               TIMESTAMPTZ,
  scheduled_for         TIMESTAMPTZ,
  
  -- Response tracking
  opened_at             TIMESTAMPTZ,      -- Email pixel tracking
  responded_at          TIMESTAMPTZ,
  response_text         TEXT,
  
  -- Outcome
  resulted_in_referral  BOOLEAN DEFAULT FALSE,
  resulted_in_interview BOOLEAN DEFAULT FALSE,
  
  -- Status
  status                TEXT DEFAULT 'queued'  -- queued, sent, delivered, failed
    CHECK (status IN ('queued', 'sent', 'delivered', 'opened', 'responded', 'failed')),
  
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_outreach_contact ON outreach (contact_id);
CREATE INDEX idx_outreach_application ON outreach (application_id);
CREATE INDEX idx_outreach_sent_at ON outreach (sent_at DESC);
CREATE INDEX idx_outreach_channel ON outreach (channel);
CREATE INDEX idx_outreach_status ON outreach (status);

-- ── TABLE: failures ──────────────────────────────────────────────────────
-- Agent failure log for manual review + learning system

CREATE TABLE failures (
  id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  job_id                UUID REFERENCES jobs(id) ON DELETE CASCADE,
  application_id        UUID REFERENCES applications(id) ON DELETE SET NULL,
  
  -- Failure details
  error_type            failure_type NOT NULL,
  error_message         TEXT,
  
  -- Evidence
  screenshot_path       TEXT,            -- Local path to screenshot
  page_url              TEXT,
  dom_snapshot          TEXT,            -- Truncated DOM for debugging
  
  -- What the agent tried
  attempted_action      TEXT,
  claude_attempted_qa   JSONB,           -- The Q&A Claude tried to submit
  
  -- Resolution
  retry_count           SMALLINT DEFAULT 0,
  max_retries           SMALLINT DEFAULT 2,
  resolved              BOOLEAN DEFAULT FALSE,
  resolution_type       TEXT CHECK (resolution_type IN ('auto_retry', 'manual', 'skipped', 'pending')),
  resolved_at           TIMESTAMPTZ,
  resolved_by           TEXT,            -- 'agent' or 'human'
  
  -- Learning
  incorporated_in_learning BOOLEAN DEFAULT FALSE,
  learning_session_date    DATE,
  
  occurred_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_failures_job ON failures (job_id);
CREATE INDEX idx_failures_error_type ON failures (error_type);
CREATE INDEX idx_failures_resolved ON failures (resolved);
CREATE INDEX idx_failures_occurred_at ON failures (occurred_at DESC);

-- ── TABLE: answer_memory ─────────────────────────────────────────────────
-- Vector store for semantic answer retrieval (learning system)

CREATE TABLE answer_memory (
  id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  
  -- The question
  question_text         TEXT NOT NULL,
  question_embedding    vector(1536),     -- OpenAI/Anthropic embedding
  question_category     TEXT,            -- 'experience', 'motivation', 'technical', etc.
  
  -- The answer
  answer_text           TEXT NOT NULL,
  confidence_score      FLOAT4 DEFAULT 0.5,  -- 0-1, updated based on outcomes
  
  -- Outcome tracking
  times_used            INTEGER DEFAULT 0,
  positive_outcomes     INTEGER DEFAULT 0,  -- Used in apps that got interviews
  negative_outcomes     INTEGER DEFAULT 0,  -- Used in apps that got rejected
  
  -- Source
  source_application_id UUID REFERENCES applications(id) ON DELETE SET NULL,
  
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_answer_memory_embedding ON answer_memory 
  USING ivfflat (question_embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_answer_memory_confidence ON answer_memory (confidence_score DESC);
CREATE INDEX idx_answer_memory_category ON answer_memory (question_category);

-- ── TABLE: agent_runs ────────────────────────────────────────────────────
-- Audit log of every agent execution

CREATE TABLE agent_runs (
  id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  
  agent_name            TEXT NOT NULL,   -- scraper, filter, apply, outreach, learning
  status                TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed', 'cancelled')),
  
  -- Stats
  items_processed       INTEGER DEFAULT 0,
  items_succeeded       INTEGER DEFAULT 0,
  items_failed          INTEGER DEFAULT 0,
  
  -- Cost tracking
  claude_tokens_used    INTEGER DEFAULT 0,
  claude_cost_usd       FLOAT4 DEFAULT 0,
  
  -- Timing
  started_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at          TIMESTAMPTZ,
  duration_seconds      INTEGER GENERATED ALWAYS AS (
    EXTRACT(EPOCH FROM (completed_at - started_at))::INTEGER
  ) STORED,
  
  -- Error info
  error_message         TEXT,
  
  metadata              JSONB DEFAULT '{}'::JSONB
);

CREATE INDEX idx_agent_runs_agent ON agent_runs (agent_name);
CREATE INDEX idx_agent_runs_status ON agent_runs (status);
CREATE INDEX idx_agent_runs_started_at ON agent_runs (started_at DESC);

-- ── FUNCTIONS & TRIGGERS ─────────────────────────────────────────────────

-- Auto-update updated_at timestamps
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_jobs_updated_at
  BEFORE UPDATE ON jobs
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_applications_updated_at
  BEFORE UPDATE ON applications
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_contacts_updated_at
  BEFORE UPDATE ON contacts
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Auto-log status changes to status_events
CREATE OR REPLACE FUNCTION log_status_change()
RETURNS TRIGGER AS $$
BEGIN
  IF OLD.status IS DISTINCT FROM NEW.status THEN
    INSERT INTO status_events (application_id, from_status, to_status, source)
    VALUES (NEW.id, OLD.status, NEW.status, 'agent');
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_log_application_status
  AFTER UPDATE ON applications
  FOR EACH ROW EXECUTE FUNCTION log_status_change();

-- Purge jobs older than 7 days with no application
CREATE OR REPLACE FUNCTION purge_old_jobs() RETURNS void AS $$
BEGIN
  DELETE FROM jobs
  WHERE scraped_at < NOW() - INTERVAL '7 days'
  AND id NOT IN (SELECT DISTINCT job_id FROM applications);
END;
$$ LANGUAGE plpgsql;

-- Auto-ghost applications with no activity for 30 days
CREATE OR REPLACE FUNCTION auto_ghost_stale_applications()
RETURNS void AS $$
BEGIN
  UPDATE applications
  SET status = 'ghosted'
  WHERE status = 'applied'
    AND applied_at < NOW() - INTERVAL '30 days'
    AND id NOT IN (
      SELECT DISTINCT application_id FROM status_events
      WHERE occurred_at > NOW() - INTERVAL '30 days'
    );
END;
$$ LANGUAGE plpgsql;

-- Fast dashboard stats for JobAI API (single round-trip; avoids full-table scans in Python)
CREATE OR REPLACE FUNCTION public.job_dashboard_stats()
RETURNS json
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
SELECT json_build_object(
  'total', COUNT(*)::int,
  'remote_count', COUNT(*) FILTER (WHERE is_remote IS TRUE),
  'avg_score', COALESCE(ROUND(AVG(ai_score)::numeric, 1), 0),
  'by_verdict', json_build_object(
    'APPLY', COUNT(*) FILTER (WHERE COALESCE(NULLIF(lower(trim(ai_verdict)), ''), 'maybe') = 'apply'),
    'MAYBE', COUNT(*) FILTER (WHERE COALESCE(NULLIF(lower(trim(ai_verdict)), ''), 'maybe') = 'maybe'),
    'SKIP',  COUNT(*) FILTER (WHERE COALESCE(NULLIF(lower(trim(ai_verdict)), ''), 'maybe') = 'skip')
  ),
  'by_source', COALESCE((
    SELECT json_object_agg(source_board, cnt)
    FROM (
      SELECT source_board, count(*)::int AS cnt
      FROM jobs
      GROUP BY source_board
      ORDER BY cnt DESC
      LIMIT 40
    ) sub2
  ), '{}'::json)
) FROM jobs;
$$;

COMMENT ON FUNCTION public.job_dashboard_stats IS 'Aggregated job stats for JobAI dashboard.';

-- ── ROW LEVEL SECURITY ───────────────────────────────────────────────────
-- Enable RLS on all tables (Supabase best practice)

ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE resumes ENABLE ROW LEVEL SECURITY;
ALTER TABLE applications ENABLE ROW LEVEL SECURITY;
ALTER TABLE status_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE contacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE outreach ENABLE ROW LEVEL SECURITY;
ALTER TABLE failures ENABLE ROW LEVEL SECURITY;
ALTER TABLE answer_memory ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_runs ENABLE ROW LEVEL SECURITY;

-- Service role has full access (backend uses service key)
-- Anon role has no access (frontend uses service key through backend API, not directly)

-- ── USEFUL VIEWS ─────────────────────────────────────────────────────────

-- Dashboard summary view
CREATE OR REPLACE VIEW dashboard_summary AS
SELECT
  COUNT(*) FILTER (WHERE status = 'applied')           AS total_applied,
  COUNT(*) FILTER (WHERE status = 'response_received') AS total_responses,
  COUNT(*) FILTER (WHERE status IN ('phone_screen', 'technical', 'final_round')) AS total_interviews,
  COUNT(*) FILTER (WHERE status = 'offer')             AS total_offers,
  COUNT(*) FILTER (WHERE status = 'rejected')          AS total_rejected,
  COUNT(*) FILTER (WHERE status = 'ghosted')           AS total_ghosted,
  COUNT(*) FILTER (WHERE status = 'manual_required')   AS needs_attention,
  ROUND(
    COUNT(*) FILTER (WHERE status != 'applied')::numeric /
    NULLIF(COUNT(*) FILTER (WHERE status = 'applied'), 0) * 100, 1
  )                                                     AS response_rate_pct,
  MIN(applied_at)                                       AS first_application_date,
  MAX(applied_at)                                       AS latest_application_date
FROM applications;

-- Application pipeline with job details
CREATE OR REPLACE VIEW application_pipeline AS
SELECT
  a.id,
  a.status,
  a.apply_type,
  a.applied_at,
  a.cover_letter,
  a.form_qa,
  a.notes,
  j.title,
  j.company,
  j.location,
  j.job_url,
  j.source_board,
  j.ai_score,
  j.salary_min,
  j.salary_max,
  j.is_remote,
  r.version_name AS resume_version,
  r.file_path AS resume_path,
  -- Outreach status
  (SELECT COUNT(*) FROM outreach o WHERE o.application_id = a.id) AS outreach_sent,
  (SELECT COUNT(*) FROM outreach o WHERE o.application_id = a.id AND o.responded_at IS NOT NULL) AS outreach_responses
FROM applications a
JOIN jobs j ON a.job_id = j.id
LEFT JOIN resumes r ON a.resume_id = r.id
ORDER BY a.applied_at DESC;

-- Outreach funnel view
CREATE OR REPLACE VIEW outreach_funnel AS
SELECT
  channel,
  COUNT(*) AS total_sent,
  COUNT(*) FILTER (WHERE opened_at IS NOT NULL) AS opened,
  COUNT(*) FILTER (WHERE responded_at IS NOT NULL) AS responded,
  COUNT(*) FILTER (WHERE resulted_in_referral = TRUE) AS referrals,
  COUNT(*) FILTER (WHERE resulted_in_interview = TRUE) AS interviews,
  ROUND(COUNT(*) FILTER (WHERE responded_at IS NOT NULL)::numeric / NULLIF(COUNT(*), 0) * 100, 1) AS response_rate_pct
FROM outreach
WHERE sent_at IS NOT NULL
GROUP BY channel;

-- Weekly agent cost summary
CREATE OR REPLACE VIEW weekly_agent_costs AS
SELECT
  DATE_TRUNC('week', started_at) AS week,
  agent_name,
  SUM(claude_cost_usd) AS total_cost_usd,
  SUM(claude_tokens_used) AS total_tokens,
  COUNT(*) AS total_runs,
  AVG(duration_seconds) AS avg_duration_secs
FROM agent_runs
WHERE status = 'completed'
GROUP BY DATE_TRUNC('week', started_at), agent_name
ORDER BY week DESC, total_cost_usd DESC;

-- ── SEED DATA ────────────────────────────────────────────────────────────
-- Insert base resume placeholder (update file_path after setup)

INSERT INTO resumes (version_name, resume_type, file_path)
VALUES ('base_v1', 'base', 'data/resumes/resume_base.docx');
