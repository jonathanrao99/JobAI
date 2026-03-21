import { useState, useRef, useEffect, useMemo } from "react";
import toast from "react-hot-toast";
import { useJobs, useCreateApplication, useAddManualJob } from "../hooks/useJobs";

const FILTER_OPTIONS = {
  domain: ["AI", "Cyber Security", "Data", "ML", "Network", "Software"],
  workType: ["Remote", "On-site", "Hybrid", "Full-time", "Part-time", "Contract", "Internship"],
  level: ["Entry", "Mid", "Senior", "Staff+"],
  industry: ["Tech", "Finance", "Healthcare", "Retail", "E-commerce", "Consulting"],
  certification: ["AWS", "Azure", "GCP", "Security+", "CISSP", "None"],
};

const TIME_FILTERS = [
  { value: 1, label: "24h" },
  { value: 3, label: "3 Days" },
  { value: 7, label: "7 Days" },
  { value: 30, label: "30 Days" },
  { value: null, label: "All" },
];

function formatPostedAt(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function inferTags(job) {
  const text = `${job.title || ""} ${job.description || ""}`.toLowerCase();
  const tags = [];
  tags.push(job.is_remote ? "Remote" : "On-site");
  if (text.includes("hybrid")) tags.push("Hybrid");
  if (text.includes("full-time")) tags.push("Full-time");
  else if (text.includes("part-time")) tags.push("Part-time");
  else if (text.includes("contract")) tags.push("Contract");
  if (text.includes("senior")) tags.push("Senior");
  else if (text.includes("staff")) tags.push("Staff+");
  else if (text.includes("intern")) tags.push("Entry");
  return [...new Set(tags)].slice(0, 4);
}

function getSkillTags(job) {
  const strengths = Array.isArray(job.ai_strengths) ? job.ai_strengths : [];
  if (strengths.length) return strengths.slice(0, 6);
  const gaps = Array.isArray(job.ai_missing_skills) ? job.ai_missing_skills : [];
  if (gaps.length) return gaps.slice(0, 6);
  const fallback = `${job.title || ""} ${job.description || ""}`
    .toLowerCase()
    .split(/[^a-z0-9+.#-]+/)
    .filter((w) => w.length > 2);
  const uniq = [];
  for (const token of fallback) {
    if (!uniq.includes(token)) uniq.push(token);
    if (uniq.length >= 6) break;
  }
  return uniq;
}

function JobRow({ job, onAddToApps, addingId }) {
  const topTags = inferTags(job);
  const skillTags = getSkillTags(job);

  return (
    <div style={{
      background: "var(--bg-raised)", borderRadius: 12,
      border: "1px solid var(--border)", overflow: "hidden",
      boxShadow: "0 6px 20px rgba(0, 0, 0, 0.2)",
    }}>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "44px 1fr auto",
          alignItems: "center",
          gap: 16,
          padding: "16px 20px",
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
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginBottom: 2 }}>
            <span style={{ fontSize: 14, fontWeight: 700, color: "var(--text-primary)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: 520 }}>
              {job.title}
            </span>
            <span style={{ fontSize: 12, color: "var(--text-muted)" }}>⌄</span>
          </div>

          <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 3 }}>
            {job.company}
            {job.location ? ` · ${job.location}` : ""}
            {formatPostedAt(job.posted_at) || formatPostedAt(job.scraped_at)
              ? ` · ${formatPostedAt(job.posted_at) || formatPostedAt(job.scraped_at)}`
              : ""}
          </div>

          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 8 }}>
            {topTags.map((t) => (
              <span key={t} style={{
                fontSize: 10, padding: "3px 8px", borderRadius: 6,
                background: "var(--bg-hover)", color: "var(--text-secondary)", fontWeight: 600,
              }}>
                {t}
              </span>
            ))}
          </div>
          {skillTags.length > 0 && (
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 6 }}>
              {skillTags.map((s) => (
                <span key={s} style={{
                  fontSize: 10, padding: "3px 8px", borderRadius: 6,
                  background: "rgba(128, 163, 255, 0.18)", color: "var(--text-primary)",
                  border: "1px solid rgba(128, 163, 255, 0.4)", fontWeight: 500,
                }}>
                  {s}
                </span>
              ))}
            </div>
          )}
        </div>

        <div style={{ display: "flex", gap: 8, marginLeft: 12, alignItems: "flex-end", flexDirection: "column" }}>
          <button
            onClick={(e) => { e.stopPropagation(); onAddToApps(job.id); }}
            disabled={addingId === job.id}
            style={{
              padding: "7px 14px", borderRadius: 8, fontSize: 12, fontWeight: 700,
              background: "var(--accent)", color: "#fff", border: "none",
              cursor: addingId === job.id ? "wait" : "pointer",
              opacity: addingId === job.id ? 0.7 : 1,
            }}
          >
            {addingId === job.id ? "Adding…" : "Add Job"}
          </button>
          {job.job_url && (
            <a href={job.job_url} target="_blank" rel="noopener noreferrer"
              style={{
                padding: "7px 14px", borderRadius: 8, fontSize: 12, fontWeight: 700,
                background: "var(--bg-hover)", color: "var(--text-primary)",
                border: "1px solid var(--border)", textDecoration: "none",
              }}
            >
              Apply ↗
            </a>
          )}
        </div>
      </div>
    </div>
  );
}

function FilterDropdown({ label, options, selected, onToggle, open, setOpen }) {
  return (
    <div style={{ position: "relative" }} onClick={(e) => e.stopPropagation()}>
      <button
        type="button"
        onClick={() => setOpen(open ? null : label)}
        style={{
          padding: "9px 10px",
          borderRadius: 8,
          fontSize: 12,
          background: "var(--bg-raised)",
          border: "1px solid var(--border)",
          color: "var(--text-secondary)",
          cursor: "pointer",
          minWidth: 100,
          textAlign: "left",
        }}
      >
        {label}{selected.length ? ` (${selected.length})` : ""} ⌄
      </button>
      {open === label && (
        <div style={{
          position: "absolute",
          top: 40,
          left: 0,
          zIndex: 30,
          minWidth: 170,
          background: "var(--bg-surface)",
          border: "1px solid var(--border)",
          borderRadius: 10,
          padding: 10,
          boxShadow: "0 12px 24px rgba(0,0,0,0.3)",
        }}>
          {options.map((opt) => (
            <label key={opt} style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 4px", fontSize: 12, color: "var(--text-primary)" }}>
              <input
                type="checkbox"
                checked={selected.includes(opt)}
                onChange={() => onToggle(opt)}
                style={{ accentColor: "var(--accent)" }}
              />
              {opt}
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

function AddJobModal({ open, onClose }) {
  const [title, setTitle] = useState("");
  const [company, setCompany] = useState("");
  const [jobUrl, setJobUrl] = useState("");
  const [location, setLocation] = useState("");
  const [description, setDescription] = useState("");
  const [isRemote, setIsRemote] = useState(false);
  const [tailor, setTailor] = useState(true);
  const addJob = useAddManualJob();

  if (!open) return null;

  const reset = () => {
    setTitle(""); setCompany(""); setJobUrl(""); setLocation(""); setDescription("");
    setIsRemote(false); setTailor(true);
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!title.trim() || !company.trim() || !jobUrl.trim()) return;
    addJob.mutate(
      { title, company, job_url: jobUrl, location, description, is_remote: isRemote, tailor },
      {
        onSuccess: (res) => {
          toast.success(`Added ${title} @ ${company}` + (res.tailor_result ? " — resume tailored" : ""));
          reset();
          onClose();
        },
        onError: (err) => toast.error(err?.message || "Failed to add job"),
      },
    );
  };

  const inputStyle = {
    width: "100%", padding: "10px 14px", borderRadius: 8, fontSize: 13,
    background: "var(--bg-raised)", border: "1px solid var(--border)",
    color: "var(--text-primary)", outline: "none", boxSizing: "border-box",
  };
  const labelStyle = { fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", display: "block", marginBottom: 6 };

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed", inset: 0, zIndex: 1000,
        background: "rgba(0,0,0,.55)", display: "flex", alignItems: "center", justifyContent: "center",
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "var(--bg-surface)", borderRadius: 14,
          border: "1px solid var(--border)", width: "100%", maxWidth: 520,
          maxHeight: "90vh", overflow: "auto", padding: 28,
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
          <h2 style={{ fontSize: 18, fontWeight: 700, margin: 0 }}>Add Job</h2>
          <button onClick={onClose} style={{
            background: "none", border: "none", color: "var(--text-muted)", fontSize: 20, cursor: "pointer",
          }}>×</button>
        </div>

        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: 16 }}>
            <label style={labelStyle}>Job Title *</label>
            <input type="text" required value={title} onChange={(e) => setTitle(e.target.value)}
              placeholder="Senior Software Engineer" style={inputStyle} />
          </div>
          <div style={{ marginBottom: 16 }}>
            <label style={labelStyle}>Company *</label>
            <input type="text" required value={company} onChange={(e) => setCompany(e.target.value)}
              placeholder="Stripe" style={inputStyle} />
          </div>
          <div style={{ marginBottom: 16 }}>
            <label style={labelStyle}>Job Link *</label>
            <input type="url" required value={jobUrl} onChange={(e) => setJobUrl(e.target.value)}
              placeholder="https://www.linkedin.com/jobs/view/..." style={inputStyle} />
          </div>
          <div style={{ display: "flex", gap: 16, marginBottom: 16 }}>
            <div style={{ flex: 1 }}>
              <label style={labelStyle}>Location</label>
              <input type="text" value={location} onChange={(e) => setLocation(e.target.value)}
                placeholder="San Francisco, CA" style={inputStyle} />
            </div>
            <label style={{
              display: "flex", alignItems: "flex-end", gap: 8, paddingBottom: 10,
              fontSize: 12, color: "var(--text-secondary)", cursor: "pointer", flexShrink: 0,
            }}>
              <input type="checkbox" checked={isRemote} onChange={(e) => setIsRemote(e.target.checked)}
                style={{ accentColor: "var(--accent)" }} />
              Remote
            </label>
          </div>
          <div style={{ marginBottom: 16 }}>
            <label style={labelStyle}>Job Description</label>
            <textarea value={description} onChange={(e) => setDescription(e.target.value)}
              placeholder="Paste the full job description here…" rows={6}
              style={{ ...inputStyle, resize: "vertical", lineHeight: 1.6, fontFamily: "inherit" }} />
          </div>
          <label style={{
            display: "flex", alignItems: "center", gap: 8, marginBottom: 20,
            fontSize: 13, color: "var(--text-secondary)", cursor: "pointer",
          }}>
            <input type="checkbox" checked={tailor} onChange={(e) => setTailor(e.target.checked)}
              style={{ accentColor: "var(--accent)" }} />
            Auto-tailor resume for this job
          </label>
          <button type="submit" disabled={addJob.isPending || !title.trim() || !company.trim() || !jobUrl.trim()}
            style={{
              width: "100%", padding: "12px 0", borderRadius: 8, border: "none",
              cursor: addJob.isPending ? "wait" : "pointer",
              background: addJob.isPending ? "var(--border)" : "var(--accent)",
              color: "#fff", fontWeight: 700, fontSize: 14,
              opacity: addJob.isPending ? 0.7 : 1, transition: "all 0.15s",
            }}
          >
            {addJob.isPending ? "Adding…" : "Add Job"}
          </button>
        </form>
      </div>
    </div>
  );
}

export default function JobBoard() {
  const [showAddModal, setShowAddModal] = useState(false);
  const [sinceDays, setSinceDays] = useState(7);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [page, setPage] = useState(0);
  const [flash, setFlash] = useState(null);
  const [domain, setDomain] = useState([]);
  const [workType, setWorkType] = useState([]);
  const [level, setLevel] = useState([]);
  const [industry, setIndustry] = useState([]);
  const [certification, setCertification] = useState([]);
  const [openDropdown, setOpenDropdown] = useState(null);
  const limit = 30;
  const searchTimerRef = useRef(null);

  const createApp = useCreateApplication();
  const { data, isLoading, isFetching } = useJobs({
    search: debouncedSearch || undefined,
    sinceDays,
    limit,
    offset: page * limit,
  });

  const jobs = data?.jobs || [];
  const total = data?.total ?? data?.count ?? jobs.length ?? 0;
  const hasMore = data?.has_more ?? false;

  useEffect(() => {
    return () => { if (searchTimerRef.current) clearTimeout(searchTimerRef.current); };
  }, []);
  useEffect(() => {
    const onDocClick = () => setOpenDropdown(null);
    document.addEventListener("click", onDocClick);
    return () => document.removeEventListener("click", onDocClick);
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

  const toggleIn = (value, setter) => {
    setter((prev) => (prev.includes(value) ? prev.filter((x) => x !== value) : [...prev, value]));
  };

  const filteredJobs = useMemo(() => {
    const matches = (text, vals) => vals.length === 0 || vals.some((v) => text.includes(v.toLowerCase()));
    return jobs.filter((job) => {
      const text = `${job.title || ""} ${job.description || ""} ${job.company || ""}`.toLowerCase();
      return (
        matches(text, domain) &&
        matches(text, workType) &&
        matches(text, level) &&
        matches(text, industry) &&
        matches(text, certification)
      );
    });
  }, [jobs, domain, workType, level, industry, certification]);

  return (
    <div style={{ padding: "32px 40px", maxWidth: 1100, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 24, flexWrap: "wrap", gap: 16 }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 4 }}>Job Board</h1>
          <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>
            Browse scraped jobs · {total} result{total !== 1 ? "s" : ""}
          </p>
        </div>
        <button
          onClick={() => setShowAddModal(true)}
          style={{
            padding: "10px 20px", borderRadius: 8, fontSize: 13, fontWeight: 600,
            background: "var(--accent)", color: "#fff", border: "none", cursor: "pointer",
          }}
        >
          + Add Job
        </button>
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

      {/* Search + filter row */}
      <div style={{ display: "flex", gap: 12, marginBottom: 20, flexWrap: "wrap", alignItems: "center", position: "relative" }}>
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
        <FilterDropdown
          label="Domain"
          options={FILTER_OPTIONS.domain}
          selected={domain}
          onToggle={(v) => toggleIn(v, setDomain)}
          open={openDropdown}
          setOpen={setOpenDropdown}
        />
        <FilterDropdown
          label="Work Type"
          options={FILTER_OPTIONS.workType}
          selected={workType}
          onToggle={(v) => toggleIn(v, setWorkType)}
          open={openDropdown}
          setOpen={setOpenDropdown}
        />
        <FilterDropdown
          label="Level"
          options={FILTER_OPTIONS.level}
          selected={level}
          onToggle={(v) => toggleIn(v, setLevel)}
          open={openDropdown}
          setOpen={setOpenDropdown}
        />
        <FilterDropdown
          label="Industry"
          options={FILTER_OPTIONS.industry}
          selected={industry}
          onToggle={(v) => toggleIn(v, setIndustry)}
          open={openDropdown}
          setOpen={setOpenDropdown}
        />
        <FilterDropdown
          label="Certification"
          options={FILTER_OPTIONS.certification}
          selected={certification}
          onToggle={(v) => toggleIn(v, setCertification)}
          open={openDropdown}
          setOpen={setOpenDropdown}
        />
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
      ) : filteredJobs.length === 0 ? (
        <div style={{
          textAlign: "center", padding: 60, color: "var(--text-muted)", fontSize: 14,
          background: "var(--bg-raised)", borderRadius: 12, border: "1px solid var(--border)",
        }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>∅</div>
          No jobs found. {!sinceDays ? "Run a scrape first." : "Try a wider time window or different filter."}
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {filteredJobs.map((job) => (
            <JobRow
              key={job.id}
              job={job}
              onAddToApps={handleAddToApps}
              addingId={createApp.isPending ? createApp.variables : null}
            />
          ))}
        </div>
      )}

      {/* Pagination */}
      {filteredJobs.length > 0 && (
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

      <AddJobModal open={showAddModal} onClose={() => setShowAddModal(false)} />
    </div>
  );
}
