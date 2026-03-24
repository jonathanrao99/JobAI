"use client";

import { useMemo, useRef, useState } from "react";
import toast from "react-hot-toast";
import { useQueryClient } from "@tanstack/react-query";
import { useAddManualJob, useApplicationJobIds, useCreateApplication, useJobs, usePrepareApplication } from "@/hooks/useJobs";
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
  const fromApi = job.jd_keywords;
  if (fromApi && Array.isArray(fromApi) && fromApi.length > 0) {
    return fromApi.slice(0, 6).map((s) => String(s));
  }
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

/**
 * Inferred seniority for pills and filters. Title and explicit role level first so
 * "Senior ..." roles are not mislabeled Entry when the JD mentions "entry-level" mentees.
 */
function inferExperienceLevel(job) {
  const raw = job.experience_level;
  if (raw != null && String(raw).trim() !== "") {
    const s = String(raw).trim().toLowerCase();
    if (s.includes("senior") || s.includes("staff") || s.includes("principal") || s.includes("director"))
      return "Senior";
    if (s.includes("mid")) return "Mid";
    if (s.includes("entry") || s.includes("junior") || s.includes("intern")) return "Entry";
  }
  const title = `${job.title || ""}`.toLowerCase();
  const text = `${job.description || ""} ${job.title || ""}`.toLowerCase();
  if (/\b(senior|sr\.?|staff|principal|distinguished|director|vp|head of)\b/.test(title)) return "Senior";
  if (/\b(mid|mid-level|intermediate)\b/.test(title)) return "Mid";
  if (/\b(junior|jr\.?|associate)\b/.test(title)) return "Entry";
  if (text.includes("5-7 years") || text.includes("5 to 7 years")) return "5-7 years";
  if (text.includes("2-3 years") || text.includes("2 to 3 years")) return "2-3 years";
  if (/\b3\s*\+?\s*years?\b/.test(text) || text.includes("3+ years")) return "3+ years";
  if (/\b5\s*\+?\s*years?\b/.test(text) || text.includes("5+ years")) return "5+ years";
  if (text.includes("senior") || text.includes("staff") || text.includes("principal")) return "Senior";
  if (text.includes("mid-level") || /\bmid\b/.test(text)) return "Mid";
  if (
    text.includes("entry") ||
    text.includes("intern") ||
    text.includes("new grad") ||
    text.includes("early career") ||
    text.includes("0-2 years")
  )
    return "Entry";
  return null;
}

function matchesDomain(job, domain) {
  if (domain === "All") return true;
  const text = `${job.title || ""} ${job.description || ""}`;
  const patterns = {
    Software: /(software|engineer|developer|full[\s-]?stack|backend|frontend|devops|\bswe\b|platform|programming)/i,
    Data: /(data scientist|data engineer|analytics|business intelligence|\banalyst\b|looker|tableau|power bi|dbt)/i,
    ML: /(machine learning|\bml\b|deep learning|pytorch|tensorflow|nlp|computer vision|keras|xgboost)/i,
    AI: /(\bai\b|artificial intelligence|llm|generative|genai|\brag\b)/i,
    "Cyber Security": /(cyber|security\b|soc\b|infosec|penetration|iam\b)/i,
    Network: /(\bnetwork\b|networking|ccna|routing|switching)/i,
  };
  const re = patterns[domain];
  if (re) return re.test(text);
  return text.toLowerCase().includes(domain.toLowerCase());
}

function matchesWorkType(job, workType) {
  if (workType === "All") return true;
  const desc = `${job.description || ""} ${job.title || ""}`.toLowerCase();
  if (workType === "Remote") return !!job.is_remote || /\bremote\b/.test(desc);
  if (workType === "Hybrid") return desc.includes("hybrid");
  if (workType === "On-site") return !job.is_remote && !desc.includes("hybrid");
  if (workType === "Full-time") {
    if (desc.includes("part-time") || desc.includes("part time")) return false;
    if (desc.includes("full-time") || desc.includes("full time") || desc.includes("fulltime") || desc.includes("permanent")) return true;
    if (/\bcontract\b/.test(desc) || desc.includes("contractor")) return false;
    return true;
  }
  if (workType === "Part-time") return desc.includes("part-time") || desc.includes("part time");
  if (workType === "Contract") return desc.includes("contract") || desc.includes("contractor");
  return desc.includes(workType.toLowerCase());
}

function matchesLevel(job, level) {
  if (level === "All") return true;
  const inferred = inferExperienceLevel(job);
  if (inferred === level) return true;
  return false;
}

function matchesIndustry(job, industry) {
  if (industry === "All") return true;
  const blob = `${job.title || ""} ${job.description || ""} ${job.company || ""}`;
  const jf = String(job.industry || job.job_function || "");
  const patterns = {
    Tech: /(technology|software|saas|startup|engineering|platform|cryptocurrency|digital product)/i,
    Finance: /(finance|bank|banking|trading|fintech|investment|asset|hedge|capital)/i,
    Healthcare: /(health|medical|pharma|hospital|clinical|patient|biotech|life science)/i,
    "E-commerce": /(e-commerce|ecommerce|retail|commerce|marketplace|shopify|amazon retail)/i,
    Consulting: /(consulting|consultant|advisory|deloitte|accenture|pwc)/i,
    "Corporate Technology": /(enterprise|corporate|internal it|fortune 500)/i,
  };
  const re = patterns[industry];
  if (re) return re.test(blob) || re.test(jf);
  return blob.toLowerCase().includes(industry.toLowerCase()) || jf.toLowerCase().includes(industry.toLowerCase());
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

function salaryPillText(job) {
  const { min, max } = resolvedSalaryRange(job);
  if (min == null && max == null) return null;
  const fmt = (v) => `$${Math.round(Number(v) / 1000)}k`;
  if (min != null && max != null) return `${fmt(min)}–${fmt(max)}`;
  if (min != null) return `${fmt(min)}+`;
  return `Up to ${fmt(max)}`;
}

function formatSourceBoard(s) {
  if (!s || typeof s !== "string") return "—";
  return s
    .replace(/_/g, " ")
    .split(" ")
    .map((w) => (w ? w.charAt(0).toUpperCase() + w.slice(1).toLowerCase() : ""))
    .join(" ");
}

/** Display job type / employment pill with consistent casing */
function formatJobTypePill(jobType) {
  if (!jobType) return "";
  const t = String(jobType).trim();
  if (!t) return "";
  const key = t.toLowerCase();
  const map = {
    "full-time": "Full-time",
    "part-time": "Part-time",
    contract: "Contract",
    "full time": "Full-time",
    "part time": "Part-time",
  };
  if (map[key]) return map[key];
  return t.charAt(0).toUpperCase() + t.slice(1).toLowerCase();
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
  const edu = job.min_education_level != null && String(job.min_education_level).trim() !== ""
    ? String(job.min_education_level)
    : "Not specified";

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
  const exp = inferExperienceLevel(job);
  const arrangement = inferArrangement(job);
  const titleId = `job-title-${job.id}`;

  return (
    <article className="job-card" aria-labelledby={titleId}>
      <div className="job-card-header">
        <div className="job-card-header-main">
          <div className="job-title-row">
            <h3 className="job-title" id={titleId}>
              {job.title}
            </h3>
            <button
              type="button"
              className={`chevron-btn${expanded ? " open" : ""}`}
              onClick={() => toggleExpand(job.id)}
              aria-expanded={expanded}
              aria-controls={`job-panel-${job.id}`}
              aria-label={expanded ? "Collapse job details" : "Expand job description and details"}
            >
              <span aria-hidden>▼</span>
            </button>
          </div>
        </div>
        <div className="job-card-actions-top">
          {job.job_url ? (
            <a
              className="btn-apply-primary"
              href={job.job_url}
              target="_blank"
              rel="noopener noreferrer"
            >
              Apply <span className="btn-apply-icon" aria-hidden>↗</span>
            </a>
          ) : null}
          {isAdded ? (
            <button type="button" className="btn-pipeline-added" disabled>
              In pipeline
            </button>
          ) : (
            <button type="button" className="btn-add-pipeline" onClick={() => onAdd(job.id)} disabled={addPending}>
              {addPending ? "Adding…" : "Add to pipeline"}
            </button>
          )}
        </div>
      </div>

      <div className="job-meta-row">
        <div className="job-meta">
          <span className="job-meta-company">{job.company || "Unknown Company"}</span>
          {job.location ? (
            <>
              <span className="meta-sep" aria-hidden>
                ·
              </span>
              <span>{job.location}</span>
            </>
          ) : null}
          {(job.posted_at || job.scraped_at) ? (
            <>
              <span className="meta-sep" aria-hidden>
                ·
              </span>
              <time dateTime={job.posted_at || job.scraped_at}>{formatDate(job.posted_at || job.scraped_at)}</time>
            </>
          ) : null}
        </div>
      </div>

      <div className="job-pills" role="group" aria-label="Job attributes">
        {arrangement === "remote" ? (
          <span className="pill pill-remote">Remote</span>
        ) : arrangement === "hybrid" ? (
          <span className="pill pill-worktype">Hybrid</span>
        ) : (
          <span className="pill pill-worktype">On-site</span>
        )}
        {jobType ? <span className="pill pill-worktype">{formatJobTypePill(jobType)}</span> : null}
        {exp ? <span className="pill pill-worktype">{exp}</span> : null}
        {salary ? <span className="pill pill-salary">{salary}</span> : null}
        {industry ? <span className="pill pill-industry">{industry}</span> : null}
      </div>

      {skills.length > 0 && (
        <div className="job-skills-wrap">
          <p className="job-skills-label">Skills</p>
          <div className="job-skills" role="list">
            {skills.map((skill, i) => (
              <span key={`${skill}-${i}`} className="skill-chip" role="listitem">
                {skill}
              </span>
            ))}
          </div>
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
        <div className="job-expanded" id={`job-panel-${job.id}`}>
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
    </article>
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
        position: "fixed", inset: 0, background: "rgba(0,0,0,0.55)",
        display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "var(--bg-surface)", borderRadius: 14,
          border: "1px solid var(--border)", width: "100%", maxWidth: 560, padding: 24,
        }}
      >
        <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 14 }}>Add Job</h2>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            onSubmit({ title, company, job_url: jobUrl, location, description, is_remote: isRemote, tailor: false });
          }}
        >
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            <input required placeholder="Job title" value={title} onChange={(e) => setTitle(e.target.value)}
              style={{ padding: "10px 12px", borderRadius: 8, border: "1px solid var(--border)", background: "var(--bg-raised)", color: "var(--text-primary)" }} />
            <input required placeholder="Company" value={company} onChange={(e) => setCompany(e.target.value)}
              style={{ padding: "10px 12px", borderRadius: 8, border: "1px solid var(--border)", background: "var(--bg-raised)", color: "var(--text-primary)" }} />
          </div>
          <input required placeholder="Job URL" value={jobUrl} onChange={(e) => setJobUrl(e.target.value)}
            style={{ marginTop: 10, width: "100%", padding: "10px 12px", borderRadius: 8, border: "1px solid var(--border)", background: "var(--bg-raised)", color: "var(--text-primary)" }} />
          <input placeholder="Location" value={location} onChange={(e) => setLocation(e.target.value)}
            style={{ marginTop: 10, width: "100%", padding: "10px 12px", borderRadius: 8, border: "1px solid var(--border)", background: "var(--bg-raised)", color: "var(--text-primary)" }} />
          <textarea placeholder="Description" value={description} onChange={(e) => setDescription(e.target.value)} rows={5}
            style={{ marginTop: 10, width: "100%", padding: "10px 12px", borderRadius: 8, border: "1px solid var(--border)", background: "var(--bg-raised)", color: "var(--text-primary)" }} />
          <label style={{ marginTop: 10, display: "flex", alignItems: "center", gap: 8, color: "var(--text-secondary)", fontSize: 13 }}>
            <input type="checkbox" checked={isRemote} onChange={(e) => setIsRemote(e.target.checked)} />
            Remote
          </label>
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 14 }}>
            <button type="button" onClick={onClose}
              style={{ padding: "9px 14px", borderRadius: 8, border: "1px solid var(--border)", background: "transparent", color: "var(--text-secondary)", cursor: "pointer" }}>
              Cancel
            </button>
            <button type="submit" disabled={pending} className="btn-add-job" style={{ fontWeight: 600 }}>
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
  const prepareApp = usePrepareApplication();
  const { data: appliedJobIds } = useApplicationJobIds();

  const { data, isLoading, isFetching } = useJobs({
    verdict: undefined,
    search: debouncedSearch || undefined,
    sinceDays,
    includeDescription: true,
    limit: visibleCount,
    offset: 0,
  });

  const jobs = useMemo(() => data?.jobs ?? [], [data]);

  const filteredJobs = useMemo(() => {
    return jobs.filter(
      (job) =>
        !appliedJobIds?.has(job.id) &&
        matchesDomain(job, domain) &&
        matchesWorkType(job, workType) &&
        matchesLevel(job, level) &&
        matchesIndustry(job, industry),
    );
  }, [jobs, appliedJobIds, domain, workType, level, industry]);

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
      onSuccess: (data) => {
        toast.success("Added to pipeline");
        queryClient.setQueryData(["applications", "jobIds"], (prev) => {
          const next = new Set(prev instanceof Set ? prev : []);
          next.add(jobId);
          return next;
        });
        const appId = data?.application?.id;
        if (appId) {
          const t = toast.loading("Preparing resume and outreach…");
          prepareApp.mutate(appId, {
            onSettled: () => toast.dismiss(t),
            onSuccess: () => {
              toast.success("Resume and materials ready");
            },
            onError: (err) => {
              toast.error(err?.message || "Could not generate materials");
            },
          });
        }
      },
      onError: (e) => {
        if ((e.message || "").toLowerCase().includes("already")) {
          toast.success("Already in pipeline");
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
          <p className="job-board-subtitle">
            Openings from your latest scrape · {totalResults} {totalResults === 1 ? "result" : "results"}
          </p>
        </div>
        <button type="button" className="btn-add-job" onClick={() => setShowAddModal(true)}>
          + Add Job
        </button>
      </div>

      <div className="job-board-toolbar">
        <div className="job-board-time-tabs" role="group" aria-label="Time range">
        {TIME_FILTERS.map((t) => (
          <button
            key={t.value}
            type="button"
            className={`job-board-time-tab${sinceDays === t.value ? " is-active" : ""}`}
            onClick={() => { setSinceDays(t.value); setVisibleCount(25); }}
          >
            {t.label}
          </button>
        ))}
        </div>

        <div className="job-board-filters-row">
        <input type="search" className="job-board-search" placeholder="Search title or company..." value={search} onChange={(e) => handleSearch(e.target.value)} autoComplete="off" />
        <select className="job-board-select" aria-label="Domain" value={domain} onChange={(e) => setDomain(e.target.value)}>
          {FILTER_OPTIONS.domain.map((opt) => (<option key={opt} value={opt}>{opt === "All" ? "Domain" : opt}</option>))}
        </select>
        <select className="job-board-select" aria-label="Work Type" value={workType} onChange={(e) => setWorkType(e.target.value)}>
          {FILTER_OPTIONS.workType.map((opt) => (<option key={opt} value={opt}>{opt === "All" ? "Work Type" : opt}</option>))}
        </select>
        <select className="job-board-select" aria-label="Level" value={level} onChange={(e) => setLevel(e.target.value)}>
          {FILTER_OPTIONS.level.map((opt) => (<option key={opt} value={opt}>{opt === "All" ? "Level" : opt}</option>))}
        </select>
        <select className="job-board-select" aria-label="Industry" value={industry} onChange={(e) => setIndustry(e.target.value)}>
          {FILTER_OPTIONS.industry.map((opt) => (<option key={opt} value={opt}>{opt === "All" ? "Industry" : opt}</option>))}
        </select>
        </div>
      </div>

      {isFetching && !isLoading && <div className="job-board-refresh">Updating listings…</div>}

      {isLoading ? (
        <div className="job-board-loading" role="status" aria-live="polite">
          Loading openings…
        </div>
      ) : filteredJobs.length === 0 ? (
        <div className="job-board-empty">
          <p className="job-board-empty-title">No roles match these filters</p>
          <p className="job-board-empty-hint">Try a wider time range, another domain, or a shorter search.</p>
        </div>
      ) : (
        <div className="job-board-list">
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
            onSuccess: () => { toast.success("Job added"); setShowAddModal(false); },
            onError: (e) => toast.error(e.message || "Failed to add"),
          })
        }
      />
    </div>
  );
}
