"use client";

/**
 * Shown when the production build has no NEXT_PUBLIC_API_URL — browser calls would hit the
 * Next host (no FastAPI) unless this is set in Vercel project env.
 */
export default function ApiConfigBanner() {
  const missing =
    typeof process !== "undefined" &&
    process.env.NODE_ENV === "production" &&
    !String(process.env.NEXT_PUBLIC_API_URL || "").trim();

  if (!missing) return null;

  return (
    <div
      role="status"
      className="api-config-banner"
      style={{
        padding: "10px 16px",
        fontSize: 13,
        lineHeight: 1.45,
        background: "var(--surface-elevated, #1a1a1f)",
        borderBottom: "1px solid var(--border-subtle, #333)",
        color: "var(--text-muted, #aaa)",
      }}
    >
      <strong style={{ color: "var(--yellow, #e8c547)" }}>API URL not set.</strong> Add{" "}
      <code style={{ fontSize: 12 }}>NEXT_PUBLIC_API_URL</code> in Vercel (Environment Variables)
      to your deployed FastAPI base URL (no trailing slash), then redeploy. CORS must allow this
      origin in <code style={{ fontSize: 12 }}>FRONTEND_URL</code> on the API.
    </div>
  );
}
