import { useMemo, useRef, useState } from "react";
import toast from "react-hot-toast";
import { useQueryClient } from "@tanstack/react-query";
import { useAddManualJob, useApplicationJobIds, useCreateApplication, useJobs } from "../hooks/useJobs";
import "./JobBoard.css";

const TIME_FILTERS = [
  { value: 1, label: "Last 24 Hours" },
  { value: 3, label: "Last 3 Days" },
  { value: 7, label: "Last 7 Days" },
  { value: 30, label: "Last 30 Days" },
];

const FILTER_OPTIONS = {
  domain: ["All", "Software", "Data", "ML", "AI", "Cyber Security", "Network"],
  workType: ["All", "On-site", "Remote", "Hybrid", "Full-time", "Part-time", "Contract"],
  level: ["All", "Entry", "Mid", "Senior", "2-3 years", "3+ years", "5+ years", "5-7 years"],
  industry: ["All", "Tech", "Finance", "Healthcare", "E-commerce", "Consulting", "Corporate Technology"],
};

const KNOWN_SKILLS = [
  "Python", "SQL", "R", "Java", "JavaScript", "TypeScript", "C++", "Scala",
  "TensorFlow", "PyTorch", "Keras", "scikit-learn", "XGBoost", "LightGBM",
  "Pandas", "NumPy", "Spark", "Hadoop", "Kafka", "Airflow", "dbt",
  "AWS", "GCP", "Azure", "Docker", "Kubernetes", "Terraform",
  "PostgreSQL", "MySQL", "MongoDB", "Redis", "Snowflake", "BigQuery",
  "React", "Node.js", "FastAPI", "Flask", "Django",
  "Tableau", "Power BI", "Looker", "Streamlit",
  "Machine Learning", "Deep Learning", "NLP", "Computer Vision",
  "LangChain", "OpenAI", "RAG", "LLM", "MLflow", "Databricks",
  "Excel", "Git", "Linux", "REST API", "GraphQL",
];

const CERT_PATTERNS = [
  "AWS Certified", "Google Cloud Certified", "Azure Certified",
  "PMP", "CPA", "CFA", "CISSP", "CompTIA", "Salesforce Certified",
  "ServiceNow Certified", "Certified Implementation Specialist",
  "ITIL", "Six Sigma", "Scrum Master", "CSM", "CISM", "CISA",
];

function extractSkills(job) {
  if (job.skills && Array.isArray(job.skills) && job.skills.length > 0) {
    return job.skills.slice(0, 6);
  }
  const text = `${job.description || ""} ${job.title || ""}`;
  const extracted = KNOWN_SKILLS.filter((skill) =>
    text.toLowerCase().includes(skill.toLowerCase()),
  );
  return extracted.length > 0 ? extracted.slice(0, 6) : [];
}

function extractCerts(job) {
  const text = job.description || "";
  return CERT_PATTERNS.filter((c) => text.includes(c)).slice(0, 4);
}

function inferJobType(job) {
  const text = `${job.description || ""}`.toLowerCase();
  if (job.job_type) return job.job_type;
  if (text.includes("full-time") || text.includes("full time")) return "Full-time";
  if (text.includes("part-time") || text.includes("part time")) return "Part-time";
  if (text.includes("contract")) return "Contract";
  return null;
}

function inferExperience(job) {
  if (job.experience_level) return job.experience_level;
  const text = `${job.description || ""} ${job.title || ""}`.toLowerCase();
  if (text.includes("5-7 years") || text.includes("5 to 7 years")) return "5-7 years";
  if (text.includes("2-3 years") || text.includes("2 to 3 years")) return "2-3 years";
  if (text.includes("entry") || text.includes("intern")) return "Entry";
  if (text.includes("senior")) return "Senior";
  if (text.includes("mid")) return "Mid";
  return null;
}

function inferArrangement(job) {
  const text = `${job.description || ""} ${job.title || ""}`.toLowerCase();
  if (job.is_remote) return "remote";
  if (text.includes("hybrid")) return "hybrid";
  return "onsite";
}

function formatDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

/** Parse min/max annual USD from job description when structured fields are empty. Mirrors backend/utils/salary_parse.py. */
function parseSalaryFromDescription(text) {
  if (!text || typeof text !== "string") return null;

  const parseMoney = (raw) => {
    const n = parseFloat(String(raw).replace(/,/g, "").replace(/\s/g, ""));
    return Number.isFinite(n) ? n : null;
  };

  const sane = (a, b) => {
    if (a == null || b == null) return null;
    const min = Math.min(a, b);
    const max = Math.max(a, b);
    if (max < 5000 || max > 10_000_000) return null;
    return { min, max };
  };

  // 1) Dice: "Minimum Salary" … "$ 170,000.00" … "Maximum Salary" … "$ 210,000.00" (often at end of posting)
  const mm = text.match(
    /minimum\s+salary\s*[\r\n\s]*\$\s*([\d,]+(?:\.\d+)?)[\s\S]{0,6000}?maximum\s+salary\s*[\r\n\s]*\$\s*([\d,]+(?:\.\d+)?)/i,
  );
  if (mm) {
    const r = sane(parseMoney(mm[1]), parseMoney(mm[2]));
    if (r) return r;
  }

  const head = text.slice(0, 16000);
  const afterSalary = head.split(/salary\s*:/i)[1] || head.split(/compensation\s*:/i)[1] || head;
  const block = (afterSalary || head).slice(0, 2000);
  const pairInBlock = block.match(/\$\s*([\d,]+(?:\.\d+)?)\s*[^$]{0,400}[-–—]\s*\$\s*([\d,]+(?:\.\d+)?)/i);
  if (pairInBlock) {
    const r = sane(parseMoney(pairInBlock[1]), parseMoney(pairInBlock[2]));
    if (r) return r;
  }

  const usd = head.match(
    /USD\s*([\d,]+(?:\.\d+)?)\s*(?:to|[-–—])\s*([\d,]+(?:\.\d+)?)\s*(?:per\s*year|annually|\/yr|a\s*year)/i,
  );
  if (usd) {
    const r = sane(parseMoney(usd[1]), parseMoney(usd[2]));
    if (r) return r;
  }

  const loose = head.match(
    /\$\s*([\d,]{4,}(?:\.\d+)?)\s*[^$]{0,320}[-–—]\s*\$\s*([\d,]{4,}(?:\.\d+)?)/i,
  );
  if (loose) {
    const r = sane(parseMoney(loose[1]), parseMoney(loose[2]));
    if (r) return r;
  }

  return null;
}

function resolvedSalaryRange(job) {
  const min = job.min_amount ?? job.salary_min;
  const max = job.max_amount ?? job.salary_max;
  if (min != null || max != null) {
    return { min: min != null ? Number(min) : null, max: max != null ? Number(max) : null };
  }
  const parsed = parseSalaryFromDescription(job.description || "");
  if (parsed) return { min: parsed.min, max: parsed.max };
  return { min: null, max: null };
}

function formatSalaryK(min, max) {
  const fmt = (v) => `$${Math.round(Number(v) / 1000)}k`;
  if (min != null && max != null) return `${fmt(min)} – ${fmt(max)}`;
  if (min != null) return `${fmt(min)}+`;
  if (max != null) return `Up to ${fmt(max)}`;
  return "Not listed";
}

function salaryPillText(job) {
  const { min, max } = resolvedSalaryRange(job);
  if (min == null && max == null) return null;
  const fmt = (v) => `$${Math.round(Number(v) / 1000)}k`;
  if (min != null && max != null) return `${fmt(min)}–${fmt(max)}`;
  if (min != null) return `${fmt(min)}+`;
  return `Up to ${fmt(max)}`;
}

function salaryDetailText(job) {
  const { min, max } = resolvedSalaryRange(job);
  return formatSalaryK(min, max);
}

function formatSourceBoard(s) {
  if (!s || typeof s !== "string") return "—";
  return s
    .replace(/_/g, " ")
    .split(" ")
    .map((w) => (w ? w.charAt(0).toUpperCase() + w.slice(1).toLowerCase() : ""))
    .join(" ");
}

function JobDescriptionPanel({ job }) {
  const [showAll, setShowAll] = useState(false);
  const raw = job.description || "";
  const needsTruncate = raw.length > 1500;
  const body = needsTruncate && !showAll ? raw.slice(0, 1500) : raw;

  return (
    <div className="job-desc-scroll">
      <div className="job-desc-text">
        {body}
        {needsTruncate && !showAll ? "…" : ""}
      </div>
      {needsTruncate && !showAll && (
        <button type="button" className="show-more-btn" onClick={() => setShowAll(true)}>
          Show more
        </button>
      )}
    </div>
  );
}

function JobDetailsPanel({ job }) {
  const posted = formatDate(job.posted_at || job.scraped_at) || "—";
  const edu = job.min_education_level != null && String(job.min_education_level).trim() !== ""
    ? String(job.min_education_level)
    : "Not specified";
  const levelRaw = job.experience_level != null && String(job.experience_level).trim() !== ""
    ? String(job.experience_level)
    : null;
  const level = levelRaw || inferExperience(job) || "Not specified";

  return (
    <>
      <div className="detail-row">
        <div className="detail-label">Education</div>
        <div className="detail-value">{edu}</div>
      </div>
      <div className="detail-row">
        <div className="detail-label">Source</div>
        <div className="detail-value">{formatSourceBoard(job.source_board)}</div>
      </div>
      <div className="detail-row">
        <div className="detail-label">Posted</div>
        <div className="detail-value">{posted}</div>
      </div>
      <div className="detail-row">
        <div className="detail-label">Salary</div>
        <div className="detail-value">{salaryDetailText(job)}</div>
      </div>
      <div className="detail-row">
        <div className="detail-label">Remote</div>
        <div className="detail-value">{job.is_remote ? "Yes" : "No"}</div>
      </div>
      <div className="detail-row">
        <div className="detail-label">Level</div>
        <div className="detail-value">{level}</div>
      </div>
      <div className="detail-row">
        <div className="detail-label">Job ID</div>
        <div className="detail-value detail-job-id">{String(job.id).slice(0, 8)}</div>
      </div>
    </>
  );
}

function JobCard({ job, expanded, toggleExpand, onAdd, addPending, isAdded }) {
  const skills = extractSkills(job);
  const certs = extractCerts(job);
  const salary = salaryPillText(job);
  const industry = job.job_function || job.industry;
  const jobType = inferJobType(job);
  const exp = inferExperience(job);
  const arrangement = inferArrangement(job);

  return (
    <div className="job-card">
      <div className="job-card-header">
        <div className="job-title-row">
          <h3 className="job-title">{job.title}</h3>
          <button
            type="button"
            className={`chevron-btn${expanded ? " open" : ""}`}
            onClick={() => toggleExpand(job.id)}
            aria-expanded={expanded}
            aria-label={expanded ? "Collapse" : "Expand"}
          >
            ▼
          </button>
        </div>
        <div className="job-card-actions-top">
          {isAdded ? (
            <button type="button" className="btn-added" disabled>
              Added ✓
            </button>
          ) : (
            <button type="button" className="btn-add-job" onClick={() => onAdd(job.id)} disabled={addPending}>
              {addPending ? "Adding…" : "Add Job"}
            </button>
          )}
        </div>
      </div>

      <div className="job-meta-row">
        <div className="job-meta">
          <span>{job.company || "Unknown Company"}</span>
          {job.location ? (
            <>
              <span className="meta-sep">·</span>
              <span>{job.location}</span>
            </>
          ) : null}
          {(job.posted_at || job.scraped_at) ? (
            <>
              <span className="meta-sep">·</span>
              <span>{formatDate(job.posted_at || job.scraped_at)}</span>
            </>
          ) : null}
        </div>
        {job.job_url ? (
          <a className="btn-apply" href={job.job_url} target="_blank" rel="noopener noreferrer">
            Apply ↗
          </a>
        ) : null}
      </div>

      <div className="job-pills">
        {arrangement === "remote" ? (
          <span className="pill pill-remote">Remote</span>
        ) : arrangement === "hybrid" ? (
          <span className="pill pill-worktype">Hybrid</span>
        ) : (
          <span className="pill pill-worktype">On-site</span>
        )}
        {jobType ? <span className="pill pill-worktype">{jobType.toLowerCase()}</span> : null}
        {exp ? <span className="pill pill-worktype">{exp}</span> : null}
        {salary ? <span className="pill pill-salary">{salary}</span> : null}
        {industry ? <span className="pill pill-industry">{industry}</span> : null}
      </div>

      {skills.length > 0 && (
        <div className="job-skills">
          {skills.map((skill) => (
            <span key={skill} className="skill-chip">
              {skill}
            </span>
          ))}
        </div>
      )}

      {certs.length > 0 && (
        <div className="job-certs">
          {certs.map((c) => (
            <span key={c} className="pill pill-cert">
              {c}
            </span>
          ))}
        </div>
      )}

      {expanded && (
        <div className="job-expanded">
          <div className="job-desc-col">
            <h4>Job Description</h4>
            <JobDescriptionPanel job={job} />
          </div>
          <div className="job-details-col">
            <h4>Details</h4>
            <JobDetailsPanel job={job} />
          </div>
        </div>
      )}
    </div>
  );
}

function AddJobModal({ open, onClose, onSubmit, pending }) {
  const [title, setTitle] = useState("");
  const [company, setCompany] = useState("");
  const [jobUrl, setJobUrl] = useState("");
  const [location, setLocation] = useState("");
  const [description, setDescription] = useState("");
  const [isRemote, setIsRemote] = useState(false);

  if (!open) return null;

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.55)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "var(--bg-surface)",
          borderRadius: 14,
          border: "1px solid var(--border)",
          width: "100%",
          maxWidth: 560,
          padding: 24,
        }}
      >
        <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 14 }}>Add Job</h2>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            onSubmit({
              title,
              company,
              job_url: jobUrl,
              location,
              description,
              is_remote: isRemote,
              tailor: false,
            });
          }}
        >
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            <input
              required
              placeholder="Job title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              style={{
                padding: "10px 12px",
                borderRadius: 8,
                border: "1px solid var(--border)",
                background: "var(--bg-raised)",
                color: "var(--text-primary)",
              }}
            />
            <input
              required
              placeholder="Company"
              value={company}
              onChange={(e) => setCompany(e.target.value)}
              style={{
                padding: "10px 12px",
                borderRadius: 8,
                border: "1px solid var(--border)",
                background: "var(--bg-raised)",
                color: "var(--text-primary)",
              }}
            />
          </div>
          <input
            required
            placeholder="Job URL"
            value={jobUrl}
            onChange={(e) => setJobUrl(e.target.value)}
            style={{
              marginTop: 10,
              width: "100%",
              padding: "10px 12px",
              borderRadius: 8,
              border: "1px solid var(--border)",
              background: "var(--bg-raised)",
              color: "var(--text-primary)",
            }}
          />
          <input
            placeholder="Location"
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            style={{
              marginTop: 10,
              width: "100%",
              padding: "10px 12px",
              borderRadius: 8,
              border: "1px solid var(--border)",
              background: "var(--bg-raised)",
              color: "var(--text-primary)",
            }}
          />
          <textarea
            placeholder="Description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={5}
            style={{
              marginTop: 10,
              width: "100%",
              padding: "10px 12px",
              borderRadius: 8,
              border: "1px solid var(--border)",
              background: "var(--bg-raised)",
              color: "var(--text-primary)",
            }}
          />
          <label
            style={{
              marginTop: 10,
              display: "flex",
              alignItems: "center",
              gap: 8,
              color: "var(--text-secondary)",
              fontSize: 13,
            }}
          >
            <input type="checkbox" checked={isRemote} onChange={(e) => setIsRemote(e.target.checked)} />
            Remote
          </label>
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 14 }}>
            <button
              type="button"
              onClick={onClose}
              style={{
                padding: "9px 14px",
                borderRadius: 8,
                border: "1px solid var(--border)",
                background: "transparent",
                color: "var(--text-secondary)",
                cursor: "pointer",
              }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={pending}
              className="btn-add-job"
              style={{ fontWeight: 600 }}
            >
              {pending ? "Adding…" : "Add Job"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function JobBoard() {
  const queryClient = useQueryClient();
  const [showAddModal, setShowAddModal] = useState(false);
  const [sinceDays, setSinceDays] = useState(7);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [visibleCount, setVisibleCount] = useState(25);
  const [expanded, setExpanded] = useState({});

  const [domain, setDomain] = useState("All");
  const [workType, setWorkType] = useState("All");
  const [level, setLevel] = useState("All");
  const [industry, setIndustry] = useState("All");

  const searchTimerRef = useRef(null);
  const addJob = useAddManualJob();
  const createApp = useCreateApplication();
  const { data: appliedJobIds } = useApplicationJobIds();

  const { data, isLoading, isFetching } = useJobs({
    verdict: undefined,
    search: debouncedSearch || undefined,
    sinceDays,
    limit: visibleCount,
    offset: 0,
  });

  const jobs = data?.jobs || [];

  const filteredJobs = useMemo(() => {
    return jobs.filter((job) => {
      const text = `${job.title || ""} ${job.description || ""} ${job.company || ""} ${job.location || ""}`.toLowerCase();
      const domainOk = domain === "All" || text.includes(domain.toLowerCase());
      const desc = `${job.description || ""} ${job.title || ""}`.toLowerCase();
      const workTypeOk =
        workType === "All" ||
        (workType === "Remote" && !!job.is_remote) ||
        (workType === "Hybrid" && desc.includes("hybrid")) ||
        (workType === "On-site" && !job.is_remote && !desc.includes("hybrid")) ||
        (workType !== "Remote" &&
          workType !== "Hybrid" &&
          workType !== "On-site" &&
          text.includes(workType.toLowerCase()));
      const levelOk = level === "All" || text.includes(level.toLowerCase());
      const industryOk =
        industry === "All" ||
        text.includes(industry.toLowerCase()) ||
        String(job.industry || job.job_function || "").toLowerCase().includes(industry.toLowerCase());
      return domainOk && workTypeOk && levelOk && industryOk;
    });
  }, [jobs, domain, workType, level, industry]);

  const handleSearch = (val) => {
    setSearch(val);
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    searchTimerRef.current = setTimeout(() => {
      setDebouncedSearch(val);
      setVisibleCount(25);
    }, 350);
  };

  const handleAddToPipeline = (jobId) => {
    if (appliedJobIds?.has(jobId)) return;
    createApp.mutate(jobId, {
      onSuccess: () => {
        toast.success("Added to pipeline");
        queryClient.setQueryData(["applications", "jobIds"], (prev) => {
          const next = new Set(prev instanceof Set ? prev : []);
          next.add(jobId);
          return next;
        });
      },
      onError: (e) => {
        if ((e.message || "").toLowerCase().includes("already")) {
          toast.success("Added to pipeline");
          queryClient.setQueryData(["applications", "jobIds"], (prev) => {
            const next = new Set(prev instanceof Set ? prev : []);
            next.add(jobId);
            return next;
          });
          return;
        }
        toast.error(e.message || "Failed to add");
      },
    });
  };

  const toggleExpand = (id) => setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));

  const totalResults = filteredJobs.length;
  const canLoadMore = jobs.length < (data?.total ?? 0);

  return (
    <div className="job-board-page">
      <div className="job-board-header">
        <div>
          <h1 className="job-board-title">Job Board</h1>
          <p className="job-board-subtitle">Browse scraped jobs · {totalResults} results</p>
        </div>
        <button type="button" className="btn-add-job" onClick={() => setShowAddModal(true)}>
          + Add Job
        </button>
      </div>

      <div className="job-board-time-tabs">
        {TIME_FILTERS.map((t) => (
          <button
            key={t.value}
            type="button"
            className={`job-board-time-tab${sinceDays === t.value ? " is-active" : ""}`}
            onClick={() => {
              setSinceDays(t.value);
              setVisibleCount(25);
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="job-board-filters-row">
        <input
          type="search"
          className="job-board-search"
          placeholder="Search title or company..."
          value={search}
          onChange={(e) => handleSearch(e.target.value)}
          autoComplete="off"
        />
        <select className="job-board-select" aria-label="Domain" value={domain} onChange={(e) => setDomain(e.target.value)}>
          {FILTER_OPTIONS.domain.map((opt) => (
            <option key={opt} value={opt}>
              {opt === "All" ? "Domain" : opt}
            </option>
          ))}
        </select>
        <select
          className="job-board-select"
          aria-label="Work Type"
          value={workType}
          onChange={(e) => setWorkType(e.target.value)}
        >
          {FILTER_OPTIONS.workType.map((opt) => (
            <option key={opt} value={opt}>
              {opt === "All" ? "Work Type" : opt}
            </option>
          ))}
        </select>
        <select className="job-board-select" aria-label="Level" value={level} onChange={(e) => setLevel(e.target.value)}>
          {FILTER_OPTIONS.level.map((opt) => (
            <option key={opt} value={opt}>
              {opt === "All" ? "Level" : opt}
            </option>
          ))}
        </select>
        <select
          className="job-board-select"
          aria-label="Industry"
          value={industry}
          onChange={(e) => setIndustry(e.target.value)}
        >
          {FILTER_OPTIONS.industry.map((opt) => (
            <option key={opt} value={opt}>
              {opt === "All" ? "Industry" : opt}
            </option>
          ))}
        </select>
      </div>

      {isFetching && !isLoading && <div className="job-board-refresh">Refreshing…</div>}

      {isLoading ? (
        <div className="job-board-loading">Loading…</div>
      ) : filteredJobs.length === 0 ? (
        <div className="job-board-empty">No jobs found for this filter set.</div>
      ) : (
        <div>
          {filteredJobs.map((job) => (
            <JobCard
              key={job.id}
              job={job}
              expanded={!!expanded[job.id]}
              toggleExpand={toggleExpand}
              onAdd={handleAddToPipeline}
              addPending={createApp.isPending && createApp.variables === job.id}
              isAdded={appliedJobIds instanceof Set && appliedJobIds.has(job.id)}
            />
          ))}
        </div>
      )}

      {canLoadMore && !isLoading && (
        <div className="job-board-load-more">
          <button type="button" onClick={() => setVisibleCount((v) => v + 25)}>
            Load 25 more
          </button>
        </div>
      )}

      <AddJobModal
        open={showAddModal}
        onClose={() => setShowAddModal(false)}
        pending={addJob.isPending}
        onSubmit={(payload) =>
          addJob.mutate(payload, {
            onSuccess: () => {
              toast.success("Job added");
              setShowAddModal(false);
            },
            onError: (e) => toast.error(e.message || "Failed to add"),
          })
        }
      />
    </div>
  );
}
