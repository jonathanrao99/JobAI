-- Incremental migration: dedup helper RPC + explicit client-role deny policies.
-- Apply after base schema from backend/db/schema.sql (or merge into a greenfield project).

CREATE OR REPLACE FUNCTION public.jobs_dedup_hashes_in(p_hashes text[])
RETURNS text[]
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT COALESCE(
    ARRAY(SELECT dedup_hash FROM jobs WHERE dedup_hash = ANY(COALESCE(p_hashes, '{}'))),
    '{}'::text[]
  );
$$;

COMMENT ON FUNCTION public.jobs_dedup_hashes_in IS 'Returns subset of p_hashes that already exist in jobs.';

-- Block direct PostgREST access for anon/authenticated; backend uses service_role (bypasses RLS).
DO $pol$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'jobs', 'resumes', 'applications', 'status_events', 'contacts',
    'outreach', 'failures', 'answer_memory', 'agent_runs'
  ]
  LOOP
    EXECUTE format('DROP POLICY IF EXISTS jobai_block_anon_%I ON public.%I', t, t);
    EXECUTE format(
      'CREATE POLICY jobai_block_anon_%I ON public.%I FOR ALL TO anon USING (false) WITH CHECK (false)',
      t, t
    );
    EXECUTE format('DROP POLICY IF EXISTS jobai_block_authenticated_%I ON public.%I', t, t);
    EXECUTE format(
      'CREATE POLICY jobai_block_authenticated_%I ON public.%I FOR ALL TO authenticated USING (false) WITH CHECK (false)',
      t, t
    );
  END LOOP;
END
$pol$;
