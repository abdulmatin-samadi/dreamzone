import { ReactNode, useState } from "react";
import { useTranslation } from "react-i18next";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import type { Role } from "../api/types";
import { BILINGUAL_ROLES, useAuth } from "../auth/AuthContext";
import { LANGUAGES } from "../i18n";
import { AnimatedBackground } from "./AnimatedBackground";
import { ThemeToggle } from "./ThemeToggle";
import { cx } from "./ui";
import { useNotify } from "./Toast";

const I = (d: string) => (
  <svg viewBox="0 0 24 24" className="h-5 w-5 shrink-0" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d={d} /></svg>
);
const icons = {
  home: I("M3 11l9-8 9 8M5 10v10h14V10"), users: I("M17 20v-2a4 4 0 00-4-4H7a4 4 0 00-4 4v2M10 10a4 4 0 100-8 4 4 0 000 8M21 20v-2a4 4 0 00-3-3.9"),
  layers: I("M12 2l10 5-10 5L2 7zM2 17l10 5 10-5M2 12l10 5 10-5"), group: I("M4 6h16M4 12h16M4 18h10"),
  grad: I("M22 10L12 5 2 10l10 5zM6 12v5c3 2 9 2 12 0v-5"), desk: I("M3 5h18v10H3zM8 21h8M12 15v6"),
  exam: I("M9 5H5a2 2 0 00-2 2v12a2 2 0 002 2h14a2 2 0 002-2V7a2 2 0 00-2-2h-4M9 5a2 2 0 002 2h2a2 2 0 002-2 2 2 0 00-2-2h-2a2 2 0 00-2 2M9 14l2 2 4-4"),
  bank: I("M4 4h16v16H4zM9 9h6M9 13h6M9 17h3"), cal: I("M3 5h18v16H3zM3 10h18M8 3v4M16 3v4"),
  pen: I("M12 20h9M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4z"), live: I("M2 12h4l3-8 4 16 3-8h6"),
  log: I("M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"), report: I("M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8zM14 2v6h6M8 17v-3M12 17v-6M16 17v-4"),
  chart: I("M4 20V10M10 20V4M16 20v-8M22 20H2"), trend: I("M3 17l6-6 4 4 8-8M14 7h7v7"), check: I("M5 13l4 4L19 7"), user: I("M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2M12 11a4 4 0 100-8 4 4 0 000 8"),
};

interface Item { to: string; label: string; icon: ReactNode; end?: boolean }

function navFor(role: Role): Item[] {
  const home: Item = { to: "/", label: "nav.dashboard", icon: icons.home, end: true };
  switch (role) {
    case "ADMIN": return [home,
      { to: "/users", label: "nav.users", icon: icons.users }, { to: "/teachers", label: "nav.teachers", icon: icons.grad }, { to: "/levels", label: "nav.levels", icon: icons.layers },
      { to: "/groups", label: "nav.groups", icon: icons.group }, { to: "/students", label: "nav.students", icon: icons.grad },
      { to: "/exams", label: "nav.exams", icon: icons.exam }, { to: "/questions", label: "nav.questions", icon: icons.bank },
      { to: "/schedule", label: "nav.schedule", icon: icons.cal }, { to: "/approvals", label: "nav.approvals", icon: icons.check },
      { to: "/live", label: "nav.live", icon: icons.live }, { to: "/group-exams", label: "nav.groupExams", icon: icons.group },
      { to: "/stats", label: "nav.stats", icon: icons.trend },
      { to: "/reports", label: "nav.reports", icon: icons.report }, { to: "/audit", label: "nav.audit", icon: icons.log }];
    case "TEACHER": return [home,
      { to: "/students", label: "nav.myStudents", icon: icons.grad }, { to: "/groups", label: "nav.myGroups", icon: icons.group },
      { to: "/exams", label: "nav.exams", icon: icons.exam }, { to: "/questions", label: "nav.questions", icon: icons.bank },
      { to: "/schedule", label: "nav.schedule", icon: icons.cal }, { to: "/approvals", label: "nav.approvals", icon: icons.check },
      { to: "/writing", label: "nav.writing", icon: icons.pen },
      { to: "/results", label: "nav.history", icon: icons.chart }, { to: "/stats", label: "nav.stats", icon: icons.trend }];
    case "RECEPTIONIST": return [home,
      { to: "/students", label: "nav.students", icon: icons.grad }, { to: "/groups", label: "nav.groups", icon: icons.group }, { to: "/placements", label: "nav.placements", icon: icons.desk },
      { to: "/writing", label: "nav.writing", icon: icons.pen }, { to: "/live", label: "nav.live", icon: icons.live },
      { to: "/results", label: "nav.results", icon: icons.chart }, { to: "/reports", label: "nav.reports", icon: icons.report }];
    default: return [home, { to: "/my-exams", label: "nav.myExams", icon: icons.exam }, { to: "/my-group", label: "nav.myGroup", icon: icons.group }, { to: "/results", label: "nav.history", icon: icons.chart }];
  }
}

export function AppLayout() {
  const { t, i18n } = useTranslation();
  const { user, logout, setLanguage } = useAuth();
  const notify = useNotify();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  if (!user) return null;

  const switchLang = async (code: string) => {
    try { await setLanguage(code); } catch (e) { notify.fail(e); }
  };

  const sidebar = (
    <nav className="dz-keep flex h-full flex-col bg-gradient-to-b from-[#0a2a5e] via-[#082350] to-[#051a3d] text-sky-200/80">
      <div className="flex items-center gap-2 px-5 py-5 text-white">
        <img src="/logo.jpg" alt="Dreamzone" className="h-10 w-10 rounded-full ring-2 ring-white/30" />
        <span className="text-lg font-semibold">Dreamzone</span>
      </div>
      <ul className="flex-1 space-y-1 overflow-y-auto px-3">
        {navFor(user.role).map((i) => (
          <li key={i.to}>
            <NavLink to={i.to} end={i.end} onClick={() => setOpen(false)}
              className={({ isActive }) => cx("flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium", isActive ? "bg-gradient-to-r from-blue-600 to-cyan-500 text-white shadow-md shadow-blue-900/40" : "hover:bg-white/10 hover:text-white")}>
              {i.icon}{t(i.label)}
            </NavLink>
          </li>
        ))}
      </ul>
      <div className="border-t border-white/10 px-3 py-3">
        <NavLink to="/profile" onClick={() => setOpen(false)} className={({ isActive }) => cx("flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium", isActive ? "bg-white/15 text-white" : "hover:bg-white/10")}>
          {icons.user}{t("nav.profile")}
        </NavLink>
      </div>
    </nav>
  );

  return (
    <div className="flex h-full">
      <AnimatedBackground />
      <aside className="hidden w-64 shrink-0 lg:block">{sidebar}</aside>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-[#0b1b38]/50" onClick={() => setOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-64">{sidebar}</aside>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between gap-3 border-b border-white/70 bg-white/70 px-4 py-3 backdrop-blur sm:px-6">
          <button className="rounded p-2 text-slate-600 hover:bg-slate-100 lg:hidden" onClick={() => setOpen(true)} aria-label="Menu">☰</button>
          <div className="hidden text-sm text-slate-500 sm:block">{t(`roles.${user.role}`)}</div>
          <div className="ml-auto flex items-center gap-3">
            <ThemeToggle className="border border-slate-300 text-slate-600 hover:bg-slate-50" />
            {BILINGUAL_ROLES.includes(user.role) && (
              <div className="flex overflow-hidden rounded-lg border border-slate-300 text-xs font-medium" role="group" aria-label="Language">
                {LANGUAGES.map((l) => (
                  <button key={l.code} onClick={() => switchLang(l.code)}
                    className={cx("px-3 py-1.5", i18n.language === l.code ? "bg-indigo-600 text-on-accent" : "bg-white text-slate-600 hover:bg-slate-50")}>
                    {l.code.toUpperCase()}
                  </button>
                ))}
              </div>
            )}
            <span className="hidden text-sm font-medium text-slate-700 sm:inline">{user.full_name}</span>
            <button onClick={async () => { await logout(); nav("/login"); }}
              className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50">{t("nav.logout")}</button>
          </div>
        </header>
        <main className="flex-1 overflow-y-auto p-4 sm:p-6"><div className="mx-auto max-w-7xl"><BackButton role={user.role} /><Outlet /></div></main>
      </div>
    </div>
  );
}

/** Admin and teacher: one "Back" button on every page except the home page.
 *  Opened straight from a link (no history inside the app): goes one level up instead. */
function BackButton({ role }: { role: Role }) {
  const { t } = useTranslation();
  const nav = useNavigate();
  const loc = useLocation();
  if (!(role === "ADMIN" || role === "TEACHER") || loc.pathname === "/") return null;
  const up = loc.pathname.replace(/\/[^/]+\/?$/, "") || "/";
  return (
    <button type="button" onClick={() => (loc.key !== "default" ? nav(-1) : nav(up))}
      className="mb-3 inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50">
      <span aria-hidden>←</span> {t("common.back")}
    </button>
  );
}
