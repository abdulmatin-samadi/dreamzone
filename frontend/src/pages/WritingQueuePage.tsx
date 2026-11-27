import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import type { WritingItem } from "../api/types";
import { KindBadge, LevelBadge } from "../components/badges";
import { useNotify } from "../components/Toast";
import { Badge, Button, Card, EmptyState, PageHeader, PageLoader, ProgressBar, Textarea } from "../components/ui";
import { fmtDate } from "../lib/hooks";

interface QueueRow { id: number; student: string; student_id: number; examination: string; level: string; kind: string; created_at: string; writing: WritingItem[] }

/** Every unscored writing answer, one after another: read, type the points, "save and next". */
export default function WritingQueuePage() {
  const { t } = useTranslation();
  const notify = useNotify();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["writing-queue"], queryFn: async () => (await api.get<QueueRow[]>("/results/writing-queue/")).data });
  const [idx, setIdx] = useState(0);
  const [vals, setVals] = useState<Record<number, { points: string; feedback: string; max?: string }>>({});
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(0);
  const firstInput = useRef<HTMLInputElement>(null);

  const rows = useMemo(() => q.data ?? [], [q.data]);
  const total = rows.length + done;
  const cur = rows[Math.min(idx, Math.max(0, rows.length - 1))];
  useEffect(() => { setVals({}); firstInput.current?.focus(); }, [cur?.id]);

  if (!q.data) return <PageLoader />;
  if (!cur) return (
    <>
      <PageHeader title={t("writing.title")} subtitle={t("writing.subtitle")} />
      <Card><EmptyState text={t("writing.empty")} /></Card>
    </>
  );

  const set = (id: number, k: "points" | "feedback" | "max", v: string) => setVals((s) => ({ ...s, [id]: { points: s[id]?.points ?? "", feedback: s[id]?.feedback ?? "", max: s[id]?.max, [k]: v } }));
  // like speaking: the reviewer may say what the writing is out of (e.g. 15 instead of the question's 10)
  const maxOf = (w: { question_id: number; max_points: number }) => Number(vals[w.question_id]?.max ?? w.max_points);
  const valid = cur.writing.every((w) => {
    const raw = vals[w.question_id]?.points;
    if (raw === undefined || raw === "") return false;
    const p = Number(raw), m = maxOf(w);
    return m > 0 && p >= 0 && p <= m;
  });

  const save = async () => {
    setBusy(true);
    try {
      await api.post(`/results/${cur.id}/grade-writing/`, {
        grades: cur.writing.map((w) => ({ question_id: w.question_id, points: Number(vals[w.question_id].points), feedback: vals[w.question_id].feedback ?? "", max: maxOf(w) })),
      });
      notify.ok("writing.saved");
      setDone((d) => d + 1);
      qc.setQueryData<QueueRow[]>(["writing-queue"], (old) => (old ?? []).filter((r) => r.id !== cur.id));  // the next one slides in
      if (idx >= rows.length - 1) setIdx(0);
      void qc.invalidateQueries({ queryKey: ["results"] });
    } catch (e) { notify.fail(e); } finally { setBusy(false); }
  };
  const go = (d: number) => setIdx((i) => (i + d + rows.length) % rows.length);

  return (
    <>
      <PageHeader title={t("writing.title")} subtitle={t("writing.subtitle")}
        actions={<Badge tone="amber">{t("writing.left", { n: rows.length })}</Badge>} />
      <div className="mb-4">
        <div className="mb-1 flex justify-between text-xs text-slate-500"><span>{t("writing.checkedNow", { n: done })}</span><span>{done} / {total}</span></div>
        <ProgressBar value={total ? (done / total) * 100 : 0} tone="green" />
      </div>
      <Card>
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 pb-4">
          <div>
            <p className="text-lg font-semibold text-slate-900">{cur.student}</p>
            <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-slate-500">
              <KindBadge kind={cur.kind} /> <LevelBadge code={cur.level} /> {cur.examination} · {fmtDate(cur.created_at)}
            </p>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <span className="text-slate-500">{Math.min(idx, rows.length - 1) + 1} / {rows.length}</span>
            <Button size="sm" variant="secondary" disabled={rows.length < 2} onClick={() => go(-1)} aria-label={t("writing.prev")}>←</Button>
            <Button size="sm" variant="secondary" disabled={rows.length < 2} onClick={() => go(1)} aria-label={t("writing.skip")}>→</Button>
          </div>
        </div>
        <div className="space-y-6">
          {cur.writing.map((w, i) => (
            <div key={w.question_id}>
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">{t("writing.task")}</p>
              <p className="mt-1 text-sm font-semibold text-slate-800">{w.prompt}</p>
              <p className="mt-3 text-xs font-semibold uppercase tracking-wide text-slate-400">{t("writing.answer")}</p>
              <div className="mt-1 max-h-[45vh] overflow-y-auto whitespace-pre-wrap rounded-lg border border-slate-200 bg-slate-50 p-4 text-[15px] leading-7 text-slate-800">
                {w.text || <span className="italic text-slate-400">{t("result.noAnswer")}</span>}
              </div>
              <p className="mt-1 text-xs text-slate-500">{t("exam.wordCount", { n: w.words })}</p>
              <div className="mt-3 grid gap-3 sm:grid-cols-[10rem_10rem_1fr]">
                <label className="text-sm font-medium text-slate-700">{t("result.points")} (0–{maxOf(w) || 0})
                  <input ref={i === 0 ? firstInput : undefined} type="number" min={0} max={maxOf(w) || undefined} step="0.5" inputMode="decimal"
                    value={vals[w.question_id]?.points ?? ""} onChange={(e) => set(w.question_id, "points", e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter" && valid && !busy) { e.preventDefault(); void save(); } }}
                    className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-lg font-semibold" />
                </label>
                <label className="text-sm font-medium text-slate-700">{t("result.paperWritingMax")}
                  <input type="number" min={1} step="0.5" inputMode="decimal" value={vals[w.question_id]?.max ?? String(w.max_points)}
                    onChange={(e) => set(w.question_id, "max", e.target.value)}
                    className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-lg font-semibold" />
                </label>
                <Textarea label={t("result.feedback")} rows={2} value={vals[w.question_id]?.feedback ?? ""} onChange={(e) => set(w.question_id, "feedback", e.target.value)} />
              </div>
            </div>
          ))}
        </div>
        <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-4">
          <Link to={`/results/${cur.id}`} className="text-sm text-indigo-600 hover:underline">{t("writing.openResult")} →</Link>
          <div className="flex gap-2">
            {rows.length > 1 && <Button variant="ghost" onClick={() => go(1)}>{t("writing.skip")}</Button>}
            <Button loading={busy} disabled={!valid} onClick={save}>{t(rows.length > 1 ? "writing.saveNext" : "writing.save")}</Button>
          </div>
        </div>
      </Card>
    </>
  );
}
