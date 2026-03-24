# Database migrations

- **Canonical full schema:** [../schema.sql](../schema.sql) — use for new environments or documentation.
- **Versioned deltas:** [../../supabase/migrations/](../../supabase/migrations/) — timestamped SQL applied in order by Supabase CLI (`supabase db push`) or your migration runner.

After changing `schema.sql`, add a matching incremental file under `supabase/migrations/` so existing deployments can upgrade without re-applying the entire schema.

- **`add_application_materials.sql`** — adds `linkedin_note`, `cold_email`, `cold_email_subject` on `applications` for `POST /api/applications/{id}/prepare`. If you skip this, prepare still works: LinkedIn/cold fields are stored in `notes` under `__JOBAI_MATERIALS_JSON__:` until you run the migration.
