"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useStats } from "@/hooks/useJobs";
import "./Nav.css";

const mainNav = [
  { href: "/", label: "Dashboard", icon: "◈" },
  { href: "/board", label: "Job Board", icon: "⬡" },
  { href: "/applied", label: "Pipeline", icon: "⚙" },
  { href: "/analytics", label: "Analytics", icon: "∿" },
  { href: "/admin", label: "Admin", icon: "⌘" },
];

function StatusIndicator() {
  const { data, isError } = useStats();
  const total = data?.total || 0;
  const ok = !isError;

  return (
    <div className="app-nav__status">
      <div className="app-nav__status-label">Status</div>
      <div className="app-nav__status-row">
        <div className={`app-nav__status-dot ${ok ? "app-nav__status-dot--ok" : "app-nav__status-dot--bad"}`} />
        <span className={`app-nav__status-text ${ok ? "app-nav__status-text--ok" : "app-nav__status-text--bad"}`}>
          {ok ? "Connected" : "Offline"}
        </span>
      </div>
      <div className="app-nav__jobs-count">{total} jobs in DB</div>
    </div>
  );
}

function NavItem({ href, label, icon }) {
  const pathname = usePathname();
  const isActive = href === "/" ? pathname === "/" : pathname.startsWith(href);

  return (
    <Link href={href} className={`app-nav__link${isActive ? " is-active" : ""}`}>
      <span className="app-nav__icon">{icon}</span>
      {label}
    </Link>
  );
}

export default function Nav() {
  return (
    <nav className="app-nav" aria-label="Main">
      <div className="app-nav__brand">
        <div className="app-nav__kicker">JOB AGENT</div>
        <div className="app-nav__version">v2.0</div>
      </div>
      <div className="app-nav__links">
        {mainNav.map((item) => (
          <NavItem key={item.href} {...item} />
        ))}
      </div>
      <div className="app-nav__footer">
        <NavItem href="/profile" label="Profile" icon="◇" />
      </div>
      <StatusIndicator />
    </nav>
  );
}
