import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { makeKioskApi } from "../api/client";
import { ExamFlow, Stage } from "../components/ExamFlow";

interface KioskState { token: string; attemptId?: number; assignmentId?: number; studentName: string }
const KEY = "dz_kiosk";

export function openKiosk(nav: ReturnType<typeof useNavigate>, s: KioskState) {
  sessionStorage.setItem(KEY, JSON.stringify(s)); // survives a browser refresh
  nav("/kiosk", { state: s });
}

/** Full-screen placement exam for a walk-in student, run on the receptionist's machine
 * with a restricted token that only works for the examination endpoints. */
export default function KioskPage() {
  const { t } = useTranslation();
  const nav = useNavigate();
  const loc = useLocation();
  const s: KioskState | null = useMemo(() => {
    if (loc.state) return loc.state as KioskState;
    try { return JSON.parse(sessionStorage.getItem(KEY) || "null"); } catch { return null; }
  }, [loc.state]);
  const api = useMemo(() => (s ? makeKioskApi(s.token) : null), [s]);
  if (!s || !api) return <Navigate to="/placements" replace />;

  const initial: Stage = s.attemptId ? { k: "runner", attemptId: s.attemptId } : { k: "instructions", assignmentId: s.assignmentId! };
  const exit = () => { sessionStorage.removeItem(KEY); nav("/placements", { replace: true }); };
  return (
    <div className="min-h-full bg-slate-50">
      <div className="border-b border-slate-200 bg-white px-6 py-3 text-sm text-slate-600">{t("placements.kioskFor", { name: s.studentName })}</div>
      <ExamFlow api={api} initial={initial} onExit={exit} exitLabel={t("placements.finishReturn")} desk />
    </div>
  );
}
