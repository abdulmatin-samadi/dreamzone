import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { openKiosk } from "../pages/KioskPage";
import { enterFullscreen } from "./ExamRunner";
import { fmtDate, useGet } from "../lib/hooks";
import { useNotify } from "./Toast";
import { Button, Card } from "./ui";

interface Stopped {
  id: number; student: string; is_guest: boolean; assignment_id: number; examination: string; level: string; terminated_at: string; remaining_seconds: number;
  answered: number; total: number; resume_count: number; violations: { kind: string; at: string }[];
}

/** Tests that were stopped by the fullscreen rule: the teacher lets the student continue or closes the test. */
export function StoppedAttempts() {
  const { t } = useTranslation();
  const notify = useNotify();
  const qc = useQueryClient();
  const { user } = useAuth();
  const nav = useNavigate();
  const desk = user?.role === "RECEPTIONIST";  // the front desk restarts the test on this computer right away
  const { data } = useGet<Stopped[]>("stopped-attempts");
  const [busy, setBusy] = useState<string | null>(null);
  if (!data?.length) return null;

  const act = async (id: number, what: "resume" | "finalize") => {
    const row = data.find((r) => r.id === id)!;
    if (desk && what === "resume") await enterFullscreen();  // inside the click: browsers allow fullscreen only here
    setBusy(`${what}${id}`);
    try {
      await api.post(`/stopped-attempts/${id}/${what}/`);
      if (desk && what === "resume") {
        const { data: k } = await api.post<{ attempt_id: number; kiosk_token: string; student_name: string }>(`/placements/${row.assignment_id}/start/`);
        return openKiosk(nav, { token: k.kiosk_token, attemptId: k.attempt_id, studentName: k.student_name });
      }
      notify.ok(what === "resume" ? "stopped.resumed" : "stopped.finalized");
      await qc.invalidateQueries();
    } catch (e) { notify.fail(e); } finally { setBusy(null); }
  };

  return (
    <Card title={`⏸ ${t("stopped.title")} (${data.length})`} className="mb-6 border-amber-300">
      <p className="mb-3 text-sm text-slate-600">{t(desk ? "stopped.hintDesk" : "stopped.hint")}</p>
      <ul className="divide-y divide-slate-100">
        {data.map((a) => (
          <li key={a.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
            <div className="min-w-0 text-sm">
              <p className="font-semibold text-slate-900">{a.student}{a.is_guest && <span className="ml-2 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800">{t("stopped.guest")}</span>} <span className="font-normal text-slate-500">· {a.examination} ({a.level})</span></p>
              <p className="text-slate-500">
                {t("stopped.info", { done: a.answered, total: a.total, min: Math.ceil(a.remaining_seconds / 60), when: fmtDate(a.terminated_at) })}
                {a.resume_count > 0 && ` · ${t("stopped.resumedTimes", { n: a.resume_count })}`}
              </p>
            </div>
            <div className="flex gap-2">
              <Button loading={busy === `resume${a.id}`} onClick={() => act(a.id, "resume")}>{t(desk ? "stopped.resumeDesk" : "stopped.resume")}</Button>
              <Button variant="secondary" loading={busy === `finalize${a.id}`} onClick={() => act(a.id, "finalize")}>{t("stopped.finalize")}</Button>
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}
