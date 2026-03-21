import { useState, useRef, useEffect } from "react";
import { useJobs, useOverrideVerdict, useTailorResume } from "../hooks/useJobs";

const VERDICT_STYLES = {
  APPLY: { bg: "var(--green-dim)", color: "var(--green)", label: "APPLY" },
  MAYBE: { bg: "var(--yellow-dim)", color: "var(--yellow)", label: "MAYBE" },
  SKIP:  { bg: "var(--red-dim)",    color: "var(--red)",    label: "SKIP" },
};

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

function ScorePill({ score }) {
  const color = score >= 8 ? "var(--green)" : score >= 5 ? "var(--yellow)" : "var(--red)";
  const bg = score >= 8 ? "var(--green-dim)" : score >= 5 ? "var(--yellow-dim)" : "var(--red-dim)";
  return (
    <div style={{
      width: 36, height: 36, borderRadius: 8, display: "flex", alignItems: "center",
      justifyContent: "center", fontSize: 15, fontWeight: 700, background: bg, color, flexShrink: 0,
    }}>
      {score}
    </div>
  );
}

function JobCard({ job, onOverride, onTailor, isTailoring }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div style={{
      background: "var(--bg-raised)", borderRadius: 10, border: "1px solid var(--border)",
      overflow: "hidden", transition: "border-color 0.15s",
    }}>
      <div
        onClick={() => setExpanded(!expanded)}
        style={{
          display: "flex", alignItems: "center", gap: 16, padding: "16px 20px", cursor: "pointer",
        }}
      >
        <ScorePill score={job.ai_score || 0} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <span style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)" }}>
              {job.title}
            </span>
            <VerdictBadge verdict={job.ai_verdict} />
            {job.is_remote && (
              <span style={{ fontSize: 10, color: "var(--purple)", background: "var(--bg-hover)", padding: "2px 8px", borderRadius: 10 }}>
                Remote
              </span>
            )}
          </div>
          <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 4 }}>
            {job.company}
            {job.location ? ` · ${job.location}` : ""}
            {job.source_board ? ` · ${job.source_board}` : ""}
          </div>
        </div>
        <span style={{ color: "var(--text-muted)", fontSize: 18, flexShrink: 0, transition: "transform 0.15s", transform: expanded ? "rotate(180deg)" : "none" }}>
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
                      <span key={i} style={{
                        fontSize: 11, padding: "3px 8px", borderRadius: 6,
                        background: "var(--green-dim)", color: "var(--green)",
                      }}>{s}</span>
                    ))}
                  </div>
                </div>
              )}
              {job.ai_missing_skills?.length > 0 && (
                <div>
                  <div style={{ fontSize: 11, color: "var(--red)", marginBottom: 6, fontWeight: 600 }}>Gaps</div>
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {job.ai_missing_skills.map((s, i) => (
                      <span key={i} style={{
                        fontSize: 11, padding: "3px 8px", borderRadius: 6,
                        background: "var(--red-dim)", color: "var(--red)",
                      }}>{s}</span>
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
            {job.job_url && (
              <a href={job.job_url} target="_blank" rel="noopener noreferrer" style={{
                padding: "7px 16px", borderRadius: 6, fontSize: 12, fontWeight: 600,
                background: "var(--accent)", color: "#fff", textDecoration: "none",
              }}>
                Apply →
              </a>
            )}
            <button
              type="button"
              disabled={isTailoring}
              onClick={(e) => {
                e.stopPropagation();
                onTailor(job);
              }}
              style={{
                padding: "7px 14px", borderRadius: 6, fontSize: 11, fontWeight: 600,
                background: "var(--bg-hover)", color: "var(--text-primary)",
                border: "1px solid var(--border)", cursor: isTailoring ? "wait" : "pointer",
                opacity: isTailoring ? 0.7 : 1,
              }}
            >
              {isTailoring ? "Tailoring…" : "Tailor resume"}
            </button>
            {["APPLY", "MAYBE", "SKIP"].filter((v) => v !== job.ai_verdict).map((v) => (
              <button key={v} onClick={() => onOverride(job.id, v)} style={{
                padding: "7px 14px", borderRadius: 6, fontSize: 11, fontWeight: 600,
                background: VERDICT_STYLES[v].bg, color: VERDICT_STYLES[v].color,
                border: "none", cursor: "pointer",
              }}>
                Mark {v}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default function Pipeline() {
  const [verdict, setVerdict] = useState(null);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [page, setPage] = useState(0);
  const [tailorFlash, setTailorFlash] = useState(null);
  const limit = 30;
  const searchTimerRef = useRef(null);

  const override = useOverrideVerdict();
  const tailor = useTailorResume();
  const { data, isLoading, isFetching } = useJobs({
    verdict: verdict,
    search: debouncedSearch || undefined,
    limit,
    offset: page * limit,
  });

  const jobs = data?.jobs || [];
  const total = data?.total ?? 0;
  const hasMore = data?.has_more ?? false;

  useEffect(() => {
    return () => {
      if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    };
  }, []);

  const handleSearch = (val) => {
    setSearch(val);
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    searchTimerRef.current = setTimeout(() => {
      setDebouncedSearch(val);
      setPage(0);
    }, 400);
  };

  const handleOverride = (jobId, newVerdict) => {
    override.mutate({ jobId, verdict: newVerdict });
  };

  const handleTailor = (job) => {
    tailor.mutate(job.id, {
      onSuccess: (d) => {
        setTailorFlash({
          jobId: d.job_id,
          resumeId: d.resume_id || null,
          company: d.company,
          pdfPath: d.pdf_path || null,
        });
        setTimeout(() => setTailorFlash(null), 12_000);
      },
    });
  };

  const tailoringId = tailor.isPending ? tailor.variables : null;

  const filters = [
    { value: null, label: "All" },
    { value: "APPLY", label: "Apply" },
    { value: "MAYBE", label: "Maybe" },
    { value: "SKIP", label: "Skip" },
  ];

  return (
    <div style={{ padding: "32px 40px", maxWidth: 1000, margin: "0 auto" }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 4 }}>Pipeline</h1>
      <p style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 24 }}>
        Browse, filter, tailor resumes, and manage scraped jobs
      </p>

      {tailor.isError && (
        <div style={{
          marginBottom: 16, padding: "12px 16px", borderRadius: 8,
          background: "var(--red-dim)", color: "var(--red)", fontSize: 13,
        }}>
          {tailor.error?.message || "Resume tailoring failed"}
        </div>
      )}

      {tailorFlash && (
        <div style={{
          marginBottom: 16, padding: "12px 16px", borderRadius: 8,
          background: "var(--green-dim)", color: "var(--green)", fontSize: 13,
          display: "flex", flexWrap: "wrap", gap: 12, alignItems: "center",
        }}>
          <span>Tailored for {tailorFlash.company || "job"}.</span>
          {tailorFlash.resumeId ? (
            <>
              <a
                href={`/api/resumes/${tailorFlash.resumeId}/download?format=pdf`}
                style={{ color: "var(--accent)", fontWeight: 600 }}
              >
                Download PDF
              </a>
              <a
                href={`/api/resumes/${tailorFlash.resumeId}/download?format=tex`}
                style={{ color: "var(--text-secondary)", fontWeight: 600 }}
              >
                Download TeX
              </a>
            </>
          ) : (
            <span style={{ color: "var(--text-secondary)" }}>
              {tailorFlash.pdfPath ? `Files: ${tailorFlash.pdfPath}` : "Saved locally — DB row missing id."}
            </span>
          )}
        </div>
      )}

      {/* Search + Filters */}
      <div style={{ display: "flex", gap: 12, marginBottom: 24, flexWrap: "wrap", alignItems: "center" }}>
        <input
          type="text"
          placeholder="Search titles or companies..."
          value={search}
          onChange={(e) => handleSearch(e.target.value)}
          style={{
            flex: "1 1 260px", padding: "10px 16px", borderRadius: 8, fontSize: 13,
            background: "var(--bg-raised)", border: "1px solid var(--border)",
            color: "var(--text-primary)", outline: "none",
          }}
        />
        <div style={{ display: "flex", gap: 4 }}>
          {filters.map((f) => (
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

      {isFetching && (
        <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 12 }}>Loading...</div>
      )}

      {/* Job list */}
      {!isLoading && jobs.length === 0 ? (
        <div style={{
          textAlign: "center", padding: 60, color: "var(--text-muted)", fontSize: 14,
          background: "var(--bg-raised)", borderRadius: 12, border: "1px solid var(--border)",
        }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>∅</div>
          No jobs found. {!verdict ? "Run a scrape first." : "Try a different filter."}
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {jobs.map((job) => (
            <JobCard
              key={job.id}
              job={job}
              onOverride={handleOverride}
              onTailor={handleTailor}
              isTailoring={tailoringId === job.id}
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
