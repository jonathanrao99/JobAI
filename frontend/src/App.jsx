import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useStats } from "./hooks/useJobs";

import Dashboard from "./pages/Dashboard";
import JobBoard from "./pages/JobBoard";
import AddJob from "./pages/AddJob";
import Applied from "./pages/Applied";
import Pipeline from "./pages/Pipeline";
import Agents from "./pages/Agents";
import Analytics from "./pages/Analytics";
import Outreach from "./pages/Outreach";
import Profile from "./pages/Profile";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchInterval: 30_000,
      staleTime: 10_000,
    },
  },
});

const navSections = [
  {
    label: null,
    items: [
      { to: "/", label: "Dashboard", icon: "◈" },
    ],
  },
  {
    label: "JOBS",
    items: [
      { to: "/board", label: "Job Board", icon: "⬡" },
      { to: "/add-job", label: "Add Job", icon: "＋" },
      { to: "/applied", label: "Applied", icon: "✓" },
      { to: "/profile", label: "Profile", icon: "◇" },
    ],
  },
  {
    label: "TOOLS",
    items: [
      { to: "/pipeline", label: "Pipeline", icon: "⚙" },
      { to: "/agents", label: "Agents", icon: "⚡" },
      { to: "/analytics", label: "Analytics", icon: "∿" },
      { to: "/outreach", label: "Outreach", icon: "✉" },
    ],
  },
];

function StatusIndicator() {
  const { data, isError } = useStats();
  const total = data?.total || 0;
  const ok = !isError;

  return (
    <div style={{ padding: "16px 20px", borderTop: "1px solid var(--border)" }}>
      <div style={{ fontSize: 10, color: "var(--text-muted)", marginBottom: 8, letterSpacing: 1.5 }}>STATUS</div>
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
        <div style={{
          width: 6, height: 6, borderRadius: "50%",
          background: ok ? "var(--green)" : "var(--red)",
        }} />
        <span style={{ fontSize: 11, color: ok ? "var(--green)" : "var(--red)" }}>
          {ok ? "Connected" : "Offline"}
        </span>
      </div>
      <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
        {total} jobs in DB
      </div>
    </div>
  );
}

function Layout({ children }) {
  return (
    <div style={{ display: "flex", height: "100vh" }}>
      <nav style={{
        width: 200, borderRight: "1px solid var(--border)",
        background: "var(--bg-surface)", display: "flex", flexDirection: "column",
        flexShrink: 0,
      }}>
        <div style={{ padding: "24px 20px 20px", borderBottom: "1px solid var(--border)" }}>
          <div style={{ fontSize: 10, color: "var(--text-muted)", letterSpacing: 4, marginBottom: 4 }}>JOB AGENT</div>
          <div style={{ fontSize: 14, fontWeight: 700, fontFamily: "monospace" }}>v1.0</div>
        </div>
        <div style={{ padding: "8px 0", flex: 1, overflowY: "auto" }}>
          {navSections.map((section, si) => (
            <div key={si}>
              {section.label && (
                <div style={{
                  fontSize: 10, color: "var(--text-muted)", letterSpacing: 1.5,
                  padding: "16px 20px 6px", fontWeight: 600,
                }}>
                  {section.label}
                </div>
              )}
              {section.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === "/"}
                  style={({ isActive }) => ({
                    display: "flex", alignItems: "center", gap: 10,
                    padding: "9px 20px", textDecoration: "none",
                    color: isActive ? "var(--accent)" : "var(--text-secondary)",
                    background: isActive ? "var(--accent-glow)" : "transparent",
                    borderLeft: isActive ? "2px solid var(--accent)" : "2px solid transparent",
                    fontSize: 13, fontWeight: isActive ? 600 : 400,
                    transition: "all 0.15s",
                  })}
                >
                  <span style={{ width: 18, textAlign: "center", fontSize: 14 }}>{item.icon}</span>
                  {item.label}
                </NavLink>
              ))}
            </div>
          ))}
        </div>
        <StatusIndicator />
      </nav>

      <main style={{ flex: 1, overflow: "auto", background: "var(--bg-base)" }}>
        {children}
      </main>
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Layout>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/board" element={<JobBoard />} />
            <Route path="/add-job" element={<AddJob />} />
            <Route path="/applied" element={<Applied />} />
            <Route path="/pipeline" element={<Pipeline />} />
            <Route path="/agents" element={<Agents />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/outreach" element={<Outreach />} />
            <Route path="/profile" element={<Profile />} />
          </Routes>
        </Layout>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
