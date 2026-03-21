import { useState, useRef, useEffect } from "react";
import { Link } from "react-router-dom";
import { useJobs, useCreateApplication, useTailorResume } from "../hooks/useJobs";

const VERDICT_STYLES = {
  APPLY: { bg: "var(--green-dim)", color: "var(--green)", label: "APPLY" },
  MAYBE: { bg: "var(--yellow-dim)", color: "var(--yellow)", label: "MAYBE" },
  SKIP:  { bg: "var(--red-dim)",    color: "var(--red)",    label: "SKIP" },
};

const TIME_FILTERS = [
  { value: 1, label: "24h" },
  { value: 3, label: "3 Days" },
  { value: 7, label: "7 Days" },
  { value: 30, label: "30 Days" },
  { value: null, label: "All" },
];

function VerdictBadge({ verdict }) {
  const s = VERDICT_STYLES[verdict] || VERDICT_STYLES.MAYBE;
  return (
    <span style={{
      padding: "3px 10px", borderRadius: 12, fontSize: 11, fontWeight: 700,
      background: s.bg, color: s.color, letterSpacing: 0.5,
    }}>
      {s.label}
    </span>
  );
}

function JobRow({ job, onAddToApps, addingId, onTailor, tailoringId }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div style={{
      background: "var(--bg-raised)", borderRadius: 10,
      border: "1px solid var(--border)", overflow: "hidden",
    }}>
      <div
        onClick={() => setExpanded(!expanded)}
        style={{
          display: "grid",
          gridTemplateColumns: "44px 1fr auto auto auto",
          alignItems: "center", gap: 16, padding: "14px 20px", cursor: "pointer",
        }}
      >
        <div style={{
          width: 40, height: 40, borderRadius: 8, display: "flex",
          alignItems: "center", justifyContent: "center", fontSize: 15,
          fontWeight: 700, flexShrink: 0,
          background: job.ai_score >= 7 ? "var(--green-dim)" : job.ai_score >= 4 ? "var(--yellow-dim)" : "var(--red-dim)",
          color: job.ai_score >= 7 ? "var(--green)" : job.ai_score >= 4 ? "var(--yellow)" : "var(--red)",
        }}>
          {job.ai_score || "—"}
        </div>
        <div style={{ minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <span style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)" }}>
              {job.title}
            </span>
            <VerdictBadge verdict={job.ai_verdict} />
            {job.is_remote && (
              <span style={{
                fontSize: 10, color: "var(--purple)", background: "var(--bg-hover)",
                padding: "2px 8px", borderRadius: 10,
              }}>
                Remote
              </span>
            )}
          </div>
          <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 3 }}>
            {job.company}
            {job.location ? ` · ${job.location}` : ""}
          </div>
        </div>
        <div style={{ fontSize: 11, color: "var(--text-muted)", flexShrink: 0, whiteSpace: "nowrap" }}>
          {job.scraped_at ? new Date(job.scraped_at).toLocaleDateString() : ""}
        </div>
        <div style={{ fontSize: 11, color: "var(--text-muted)", flexShrink: 0 }}>
          {job.source_board}
        </div>
        <span style={{
          color: "var(--text-muted)", fontSize: 18, flexShrink: 0,
          transition: "transform 0.15s", transform: expanded ? "rotate(180deg)" : "none",
        }}>
          ▾
        </span>
      </div>

      {expanded && (
        <div style={{ padding: "0 20px 20px", borderTop: "1px solid var(--border)" }}>
          {job.ai_reason && (
            <div style={{ padding: "12px 0", fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.6 }}>
              <strong style={{ color: "var(--text-primary)" }}>AI Assessment:</strong> {job.ai_reason}
            </div>
          )}

          {(job.ai_strengths?.length > 0 || job.ai_missing_skills?.length > 0) && (
            <div style={{ display: "flex", gap: 24, padding: "8px 0", flexWrap: "wrap" }}>
              {job.ai_strengths?.length > 0 && (
                <div>
                  <div style={{ fontSize: 11, color: "var(--green)", marginBottom: 6, fontWeight: 600 }}>Strengths</div>
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {job.ai_strengths.map((s, i) => (
                      <span key={i} style={{ fontSize: 11, padding: "3px 8px", borderRadius: 6, background: "var(--green-dim)", color: "var(--green)" }}>{s}</span>
                    ))}
                  </div>
                </div>
              )}
              {job.ai_missing_skills?.length > 0 && (
                <div>
                  <div style={{ fontSize: 11, color: "var(--red)", marginBottom: 6, fontWeight: 600 }}>Gaps</div>
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {job.ai_missing_skills.map((s, i) => (
                      <span key={i} style={{ fontSize: 11, padding: "3px 8px", borderRadius: 6, background: "var(--red-dim)", color: "var(--red)" }}>{s}</span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {job.description && (
            <details style={{ marginTop: 8 }}>
              <summary style={{ fontSize: 12, color: "var(--text-muted)", cursor: "pointer", marginBottom: 8 }}>
                Job Description
              </summary>
              <div style={{
                fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.7,
                maxHeight: 300, overflow: "auto", whiteSpace: "pre-wrap",
                background: "var(--bg-surface)", padding: 16, borderRadius: 8,
              }}>
                {job.description}
              </div>
            </details>
          )}

          <div style={{ display: "flex", gap: 8, marginTop: 16, alignItems: "center", flexWrap: "wrap" }}>
            <button
              onClick={(e) => { e.stopPropagation(); onAddToApps(job.id); }}
              disabled={addingId === job.id}
              style={{
                padding: "7px 16px", borderRadius: 6, fontSize: 12, fontWeight: 600,
                background: "var(--accent)", color: "#fff", border: "none",
                cursor: addingId === job.id ? "wait" : "pointer",
                opacity: addingId === job.id ? 0.7 : 1,
              }}
            >
              {addingId === job.id ? "Adding…" : "+ Add to Applications"}
            </button>
            <button
              onClick={(e) => { e.stopPropagation(); onTailor(job.id); }}
              disabled={tailoringId === job.id}
              style={{
                padding: "7px 14px", borderRadius: 6, fontSize: 11, fontWeight: 600,
                background: "var(--bg-hover)", color: "var(--text-primary)",
                border: "1px solid var(--border)",
                cursor: tailoringId === job.id ? "wait" : "pointer",
                opacity: tailoringId === job.id ? 0.7 : 1,
              }}
            >
              {tailoringId === job.id ? "Tailoring…" : "Tailor Resume"}
            </button>
            {job.job_url && (
              <a href={job.job_url} target="_blank" rel="noopener noreferrer" style={{
                padding: "7px 14px", borderRadius: 6, fontSize: 12, fontWeight: 600,
                background: "var(--bg-hover)", color: "var(--blue)",
                border: "1px solid var(--border)", textDecoration: "none",
              }}>
                View Posting →
              </a>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default function JobBoard() {
  const [sinceDays, setSinceDays] = useState(7);
  const [verdict, setVerdict] = useState(null);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [page, setPage] = useState(0);
  const [flash, setFlash] = useState(null);
  const limit = 30;
  const searchTimerRef = useRef(null);

  const createApp = useCreateApplication();
  const tailor = useTailorResume();
  const { data, isLoading, isFetching } = useJobs({
    verdict,
    search: debouncedSearch || undefined,
    sinceDays,
    limit,
    offset: page * limit,
  });

  const jobs = data?.jobs || [];
  const total = data?.total ?? 0;
  const hasMore = data?.has_more ?? false;

  useEffect(() => {
    return () => { if (searchTimerRef.current) clearTimeout(searchTimerRef.current); };
  }, []);

  const handleSearch = (val) => {
    setSearch(val);
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    searchTimerRef.current = setTimeout(() => {
      setDebouncedSearch(val);
      setPage(0);
    }, 400);
  };

  const handleAddToApps = (jobId) => {
    createApp.mutate(jobId, {
      onSuccess: () => {
        setFlash("Added to applications!");
        setTimeout(() => setFlash(null), 4000);
      },
      onError: (e) => {
        setFlash(e.message?.includes("already exists") ? "Already in applications" : e.message);
        setTimeout(() => setFlash(null), 4000);
      },
    });
  };

  const verdictFilters = [
    { value: null, label: "All" },
    { value: "APPLY", label: "Apply" },
    { value: "MAYBE", label: "Maybe" },
    { value: "SKIP", label: "Skip" },
  ];

  return (
    <div style={{ padding: "32px 40px", maxWidth: 1100, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 24, flexWrap: "wrap", gap: 16 }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 4 }}>Job Board</h1>
          <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>
            Browse scraped jobs · {total} result{total !== 1 ? "s" : ""}
          </p>
        </div>
        <Link to="/add-job" style={{
          padding: "10px 20px", borderRadius: 8, fontSize: 13, fontWeight: 600,
          background: "var(--accent)", color: "#fff", textDecoration: "none",
        }}>
          + Add Job
        </Link>
      </div>

      {/* Time tabs */}
      <div style={{
        display: "flex", gap: 4, marginBottom: 16,
        padding: "3px", background: "var(--bg-surface)", borderRadius: 10,
        border: "1px solid var(--border)", width: "fit-content",
      }}>
        {TIME_FILTERS.map((t) => (
          <button
            key={t.label}
            onClick={() => { setSinceDays(t.value); setPage(0); }}
            style={{
              padding: "7px 16px", borderRadius: 8, fontSize: 12, fontWeight: 600,
              border: "none", cursor: "pointer",
              background: sinceDays === t.value ? "var(--accent)" : "transparent",
              color: sinceDays === t.value ? "#fff" : "var(--text-secondary)",
              transition: "all 0.15s",
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Search + verdict filter */}
      <div style={{ display: "flex", gap: 12, marginBottom: 20, flexWrap: "wrap", alignItems: "center" }}>
        <input
          type="text"
          placeholder="Search titles or companies…"
          value={search}
          onChange={(e) => handleSearch(e.target.value)}
          style={{
            flex: "1 1 260px", padding: "10px 16px", borderRadius: 8, fontSize: 13,
            background: "var(--bg-raised)", border: "1px solid var(--border)",
            color: "var(--text-primary)", outline: "none",
          }}
        />
        <div style={{ display: "flex", gap: 4 }}>
          {verdictFilters.map((f) => (
            <button
              key={f.label}
              onClick={() => { setVerdict(f.value); setPage(0); }}
              style={{
                padding: "8px 16px", borderRadius: 8, fontSize: 12, fontWeight: 600,
                border: "none", cursor: "pointer", transition: "all 0.15s",
                background: verdict === f.value ? "var(--accent)" : "var(--bg-raised)",
                color: verdict === f.value ? "#fff" : "var(--text-secondary)",
              }}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* Flash message */}
      {flash && (
        <div style={{
          marginBottom: 16, padding: "10px 16px", borderRadius: 8, fontSize: 13,
          background: flash.includes("already") || flash.includes("Failed") ? "var(--yellow-dim)" : "var(--green-dim)",
          color: flash.includes("already") || flash.includes("Failed") ? "var(--yellow)" : "var(--green)",
        }}>
          {flash}
        </div>
      )}

      {isFetching && !isLoading && (
        <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 8 }}>Refreshing…</div>
      )}

      {/* Job list */}
      {isLoading ? (
        <div style={{ color: "var(--text-muted)", padding: 40, textAlign: "center" }}>Loading…</div>
      ) : jobs.length === 0 ? (
        <div style={{
          textAlign: "center", padding: 60, color: "var(--text-muted)", fontSize: 14,
          background: "var(--bg-raised)", borderRadius: 12, border: "1px solid var(--border)",
        }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>∅</div>
          No jobs found. {!sinceDays ? "Run a scrape first." : "Try a wider time window or different filter."}
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {jobs.map((job) => (
            <JobRow
              key={job.id}
              job={job}
              onAddToApps={handleAddToApps}
              addingId={createApp.isPending ? createApp.variables : null}
              onTailor={(id) => tailor.mutate(id)}
              tailoringId={tailor.isPending ? tailor.variables : null}
            />
          ))}
        </div>
      )}

      {/* Pagination */}
      {jobs.length > 0 && (
        <div style={{ display: "flex", justifyContent: "center", gap: 12, marginTop: 24 }}>
          <button
            disabled={page === 0}
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            style={{
              padding: "8px 20px", borderRadius: 8, fontSize: 12, fontWeight: 600,
              background: "var(--bg-raised)", color: page === 0 ? "var(--text-muted)" : "var(--text-primary)",
              border: "1px solid var(--border)", cursor: page === 0 ? "default" : "pointer",
            }}
          >
            ← Prev
          </button>
          <span style={{ fontSize: 12, color: "var(--text-secondary)", display: "flex", alignItems: "center" }}>
            Page {page + 1}
            {total > 0 && (
              <span style={{ marginLeft: 8, color: "var(--text-muted)" }}>
                ({Math.min((page + 1) * limit, total)} / {total})
              </span>
            )}
          </span>
          <button
            disabled={!hasMore}
            onClick={() => setPage((p) => p + 1)}
            style={{
              padding: "8px 20px", borderRadius: 8, fontSize: 12, fontWeight: 600,
              background: "var(--bg-raised)", color: !hasMore ? "var(--text-muted)" : "var(--text-primary)",
              border: "1px solid var(--border)", cursor: !hasMore ? "default" : "pointer",
            }}
          >
            Next →
          </button>
        </div>
      )}
    </div>
  );
}
