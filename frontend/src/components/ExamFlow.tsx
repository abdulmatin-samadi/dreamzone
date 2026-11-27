import type { AxiosInstance } from "axios";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import type { AttemptPayload, MyAssignment, ResultDetail } from "../api/types";
import { fmtDate } from "../lib/hooks";
import { ExamRunner, enterFullscreen, fullscreenSupported } from "./ExamRunner";
import { ResultView } from "./ResultView";
import { useNotify } from "./Toast";
import { Button, Card, PageLoader } from "./ui";

export type Stage = { k: "instructions"; assignmentId: number } | { k: "runner"; attemptId: number } | { k: "result"; resultId: number };

function Instructions({ api, assignmentId, onStarted, onExit }: { api: AxiosInstance; assignmentId: number; onStarted: (attemptId: number) => void; onExit: () => void }) {
  const { t } = useTranslation();
  const notify = useNotify();
  const [a, setA] = useState<MyAssignment | null | undefined>(undefined);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get<MyAssignment[]>("/my/assignments/").then((r) => setA(r.data.find((x) => x.id === assignmentId) ?? null)).catch((e) => { notify.fail(e); setA(null); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, assignmentId]);

  if (a === undefined) return <PageLoader />;
  if (a === null) return <Card><p>{t("errors.assignment_not_found")}</p><Button className="mt-4" onClick={onExit}>{t("common.back")}</Button></Card>;

  const startable = a.state === "available" || a.state === "in_progress";
  const start = async () => {
    setBusy(true);
    try {
      await enterFullscreen();   // must happen inside the click: browsers only allow fullscreen after a user gesture
      const { data } = await api.post<AttemptPayload>(`/assignments/${a.id}/start/`);
      onStarted(data.id);
    } catch (e) { notify.fail(e); setBusy(false); }
  };

  return (
    <Card title={a.examination_title}>
      <dl className="grid gap-4 text-sm sm:grid-cols-2">
        <div><dt className="text-slate-500">{t("exam.level")}</dt><dd className="font-medium">{a.level_code}{a.target_level_code ? ` → ${a.target_level_code}` : ""}</dd></div>
        <div><dt className="text-slate-500">{t("exam.duration")}</dt><dd className="font-medium">{a.duration_minutes} {t("common.minutes")}</dd></div>
        <div><dt className="text-slate-500">{t("exam.questions")}</dt><dd className="font-medium">{a.question_count}</dd></div>
        <div><dt className="text-slate-500">{t("exam.passingScore")}</dt><dd className="font-medium">{a.passing_points} / {a.max_points} {t("exam.points")}</dd></div>
        {a.available_from && <div><dt className="text-slate-500">{t("exam.availableFrom")}</dt><dd className="font-medium">{fmtDate(a.available_from)}</dd></div>}
        {a.available_until && <div><dt className="text-slate-500">{t("exam.availableUntil")}</dt><dd className="font-medium">{fmtDate(a.available_until)}</dd></div>}
      </dl>
      {a.instructions && <p className="mt-4 whitespace-pre-wrap rounded-lg bg-slate-50 p-4 text-sm">{a.instructions}</p>}
      <ul className="mt-4 list-disc space-y-1 pl-5 text-sm text-slate-600">
        {["rule1", "rule2", "rule3", "rule4"].map((k) => <li key={k}>{t(`exam.${k}`)}</li>)}
      </ul>
      {/* phones without fullscreen (iPhone) get no warning box: the 10 s rule still applies there */}
      {fullscreenSupported() && <div className="mt-4 rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-900">{t("exam.fs.rule")}</div>}
      <div className="mt-6 flex flex-wrap gap-3">
        <Button size="lg" disabled={!startable} loading={busy} onClick={start}>{a.state === "in_progress" ? t("exam.continue") : t("exam.start")}</Button>
        <Button size="lg" variant="secondary" onClick={onExit}>{t("common.back")}</Button>
      </div>
      {!startable && <p className="mt-3 text-sm text-amber-700">{t(`states.${a.state}`)}</p>}
    </Card>
  );
}

function ResultStage({ api, resultId, onNextAssignment, onExit, exitLabel }: { api: AxiosInstance; resultId: number; onNextAssignment: (id: number) => void; onExit: () => void; exitLabel: string }) {
  const { t } = useTranslation();
  const notify = useNotify();
  const [result, setResult] = useState<ResultDetail | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { api.get<ResultDetail>(`/results/${resultId}/`).then((r) => setResult(r.data)).catch(notify.fail);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, resultId]);

  const answer = async (accept: boolean) => {
    setBusy(true);
    try {
      const { data } = await api.post<{ result: ResultDetail; assignment_id: number | null }>(`/results/${resultId}/offer/`, { accept });
      if (accept && data.assignment_id) return onNextAssignment(data.assignment_id);
      setResult(data.result);
    } catch (e) { notify.fail(e); } finally { setBusy(false); }
  };

  if (!result) return <PageLoader />;
  return (
    <>
      <ResultView result={result} onOffer={answer} offerBusy={busy} />
      {result.offer_status !== "PENDING" && <div className="mt-6"><Button size="lg" onClick={onExit}>{exitLabel}</Button></div>}
      {result.offer_status === "PENDING" && <p className="mt-4 text-sm text-slate-500">{t("offer.mustAnswer")}</p>}
    </>
  );
}

/** instructions → exam → result → (optional follow-up exam). Used by students and the reception kiosk. */
export function ExamFlow({ api, initial, onExit, exitLabel, desk = false }: { api: AxiosInstance; initial: Stage; onExit: () => void; exitLabel: string; desk?: boolean }) {
  const [stage, setStage] = useState<Stage>(initial);
  const notify = useNotify();
  if (stage.k === "runner") {
    return <ExamRunner api={api} attemptId={stage.attemptId} onFinished={(resultId) => setStage({ k: "result", resultId })}
      onStopped={() => { notify.ok(desk ? "exam.fs.stoppedDesk" : "exam.fs.stopped"); onExit(); }} />;
  }
  return (
    <div className="mx-auto max-w-3xl p-4 sm:p-6">
      {stage.k === "instructions"
        ? <Instructions api={api} assignmentId={stage.assignmentId} onExit={onExit} onStarted={(attemptId) => setStage({ k: "runner", attemptId })} />
        : <ResultStage api={api} resultId={stage.resultId} onExit={onExit} exitLabel={exitLabel}
            onNextAssignment={(assignmentId) => setStage({ k: "instructions", assignmentId })} />}
    </div>
  );
}
