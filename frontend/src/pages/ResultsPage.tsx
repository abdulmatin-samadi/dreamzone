import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";

import { api, download } from "../api/client";
import type { Level, Result, User } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { ApprovalBadge, KindBadge, LevelBadge, OutcomeBadge } from "../components/badges";
import { useNotify } from "../components/Toast";
import { Button, Card, EmptyState, FilterBar, Modal, PageHeader, Pagination, SearchInput, Select, StatCard, Table, Td, Textarea, Input } from "../components/ui";
import { fmtDate, num, useAll, useGet, useList } from "../lib/hooks";

export function ReviewModal({ result, mode, onClose, onDone }: { result: Result | null; mode: "approve" | "reject"; onClose: () => void; onDone: () => void }) {
  const { t } = useTranslation();
  const notify = useNotify();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    try { await api.post(`/results/${result!.id}/${mode}/`, { note }); notify.ok(mode === "approve" ? "approvals.approved" : "approvals.rejected"); setNote(""); onDone(); }
    catch (e) { notify.fail(e); } finally { setBusy(false); }
  };
  return (
    <Modal open={!!result} onClose={onClose} title={t(`approvals.${mode}Title`)}
      footer={<><Button variant="secondary" onClick={onClose}>{t("common.cancel")}</Button>
        <Button variant={mode === "approve" ? "success" : "danger"} loading={busy} onClick={submit}>{t(`approvals.${mode}`)}</Button></>}>
      {result && <p className="mb-3 text-sm text-slate-600">{t("approvals.summary", { student: result.student_name, from: result.level_code, to: result.target_level_code, score: `${num(result.total_score)} / ${num(result.max_score)}` })}</p>}
      <Textarea label={t("approvals.note")} value={note} onChange={(e) => setNote(e.target.value)} />
    </Modal>
  );
}

/** "1 soat 5 daqiqa" / "12 daqiqa" between start and finish. */
function useSpent() {
  const { t } = useTranslation();
  return (from: string, to: string | null) => {
    if (!to) return "—";
    const m = Math.max(1, Math.round((new Date(to).getTime() - new Date(from).getTime()) / 60000));
    return m >= 60 ? t("history.hm", { h: Math.floor(m / 60), m: m % 60 }) : t("history.m", { m });
  };
}

/** The student's own history: one card per exam with everything about it. */
function StudentHistory({ rows }: { rows: Result[] }) {
  const { t } = useTranslation();
  const spent = useSpent();
  if (!rows.length) return <EmptyState text={t("history.empty")} />;
  return (
    <div className="space-y-4">
      {rows.map((r) => {
        const decided = r.passed !== null && !r.writing_pending;
        const upgrade = r.kind === "UPGRADE";
        const verdict = r.writing_pending ? t("history.writingCheck")
          : r.passed === null ? t("history.awaited")
          : upgrade ? (r.approval_status === "APPROVED" ? t("history.movedUp", { level: r.target_level_code }) : r.passed ? t("result.passed") : t("history.stays", { level: r.level_code }))
          : r.placed_level_code ? t("history.placed", { level: r.placed_level_code }) : t(`offer.status.${r.offer_status}`);
        return (
          <Card key={r.id}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-lg font-semibold text-slate-900">{r.examination_title}</p>
                <div className="mt-1 flex flex-wrap items-center gap-2"><KindBadge kind={r.kind} /><LevelBadge code={r.level_code} />{r.target_level_code && <>→ <LevelBadge code={r.target_level_code} /></>}</div>
              </div>
              <OutcomeBadge r={r} />
            </div>
            <div className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
              <Fact label={t("result.score")} value={<span className="text-lg">{num(r.total_score)} / {num(r.max_score)} {t("exam.points")}</span>} />
              <Fact label={t("history.answers")} value={<><span className="text-emerald-700">✓ {r.correct_count}</span> · <span className="text-red-600">✗ {r.incorrect_count}</span> · <span className="text-slate-500">— {r.unanswered_count}</span></>} />
              <Fact label={t("history.when")} value={fmtDate(r.started_at)} />
              <Fact label={t("history.spent")} value={spent(r.started_at, r.finished_at)} />
              {r.speaking_score !== null && <Fact label={t("sections.SPEAKING")} value={`${num(r.speaking_score)} / ${num(r.speaking_max ?? 0)} ${t("exam.points")}`} />}
            </div>
            <div className={`mt-4 rounded-xl px-4 py-3 text-sm font-medium ${!decided ? "bg-amber-50 text-amber-900" : r.passed ? "bg-emerald-50 text-emerald-900" : "bg-red-50 text-red-800"}`}>
              {verdict}
              {r.attempt_status === "AUTO_SUBMITTED" && <span className="ml-2 font-normal">· {t("result.autoSubmitted")}</span>}
              {decided && r.review_note && <p className="mt-1 font-normal">“{r.review_note}”</p>}
            </div>
            <div className="mt-3 text-right"><Link to={`/results/${r.id}`} className="text-sm font-medium text-indigo-700 hover:underline">{t("groupExams.openResult")} →</Link></div>
          </Card>
        );
      })}
    </div>
  );
}

const Fact = ({ label, value }: { label: string; value: React.ReactNode }) => (
  <div className="rounded-lg bg-slate-50 px-3 py-2"><p className="text-xs text-slate-500">{label}</p><p className="font-semibold tabular-nums text-slate-900">{value}</p></div>
);

export default function ResultsPage({ mode = "all" }: { mode?: "all" | "approvals" }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const qc = useQueryClient();
  const staff = user!.role === "ADMIN" || user!.role === "TEACHER";
  const [qp] = useSearchParams();
  const [f, setF] = useState({ search: "", level: "", teacher: "", kind: "", passed: "", approval_status: mode === "approvals" ? "PENDING" : "", writing_pending: qp.get("writing") === "1" ? "true" : "", date_from: "", date_to: "" });
  const [page, setPage] = useState(1);
  const [review, setReview] = useState<{ r: Result; mode: "approve" | "reject" } | null>(null);
  const set = (k: keyof typeof f, v: string) => { setF((s) => ({ ...s, [k]: v })); setPage(1); };

  const params = { ...f, page };
  const list = useList<Result>("results", params);
  const levels = useGet<Level[]>("levels");
  const teachers = useAll<User>("users", { role: "TEACHER" }, user!.role === "ADMIN");
  const summary = useGet<{ total: number; decided: number; passed: number; failed: number; awaiting: number; avg_score: number | null; avg_max: number | null }>("analytics/results-summary", f, staff && mode === "all");

  const exportAs = async (file: "xlsx" | "pdf") => {
    try { await download("/results/export/", { ...f, file }, `results.${file}`); } catch (e) { void e; }
  };

  return (
    <>
      <PageHeader title={mode === "approvals" ? t("nav.approvals") : user!.role === "STUDENT" || user!.role === "TEACHER" ? t("nav.history") : t("nav.results")}
        actions={staff && mode === "all" ? <><Button variant="secondary" onClick={() => exportAs("xlsx")}>Excel</Button><Button variant="secondary" onClick={() => exportAs("pdf")}>PDF</Button></> : undefined} />

      {summary.data && (
        <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatCard label={t("results.total")} value={summary.data.total} />
          <StatCard label={t("result.passed")} value={`${summary.data.passed} / ${summary.data.decided}`} hint={summary.data.awaiting ? t("stats.awaitingShort", { n: summary.data.awaiting }) : undefined} />
          <StatCard label={t("result.failed")} value={summary.data.failed} />
          <StatCard label={t("results.average")} value={summary.data.avg_score === null ? "—" : `${num(summary.data.avg_score)} / ${num(summary.data.avg_max!)} ${t("exam.points")}`} />
        </div>
      )}

      {user!.role !== "STUDENT" && (
        <FilterBar>
          <SearchInput value={f.search} onChange={(v) => set("search", v)} />
          <Select value={f.level} onChange={(e) => set("level", e.target.value)} className="w-32"><option value="">{t("common.allLevels")}</option>{levels.data?.map((l) => <option key={l.id} value={l.id}>{l.code}</option>)}</Select>
          {user!.role === "ADMIN" && <Select value={f.teacher} onChange={(e) => set("teacher", e.target.value)} className="w-44"><option value="">{t("results.allTeachers")}</option>{teachers.items.map((x) => <option key={x.id} value={x.id}>{x.full_name}</option>)}</Select>}
          <Select value={f.kind} onChange={(e) => set("kind", e.target.value)} className="w-40"><option value="">{t("results.allTypes")}</option><option value="PLACEMENT">{t("kinds.PLACEMENT")}</option><option value="UPGRADE">{t("kinds.UPGRADE")}</option></Select>
          <Select value={f.passed} onChange={(e) => set("passed", e.target.value)} className="w-36"><option value="">{t("results.allOutcomes")}</option><option value="true">{t("result.passed")}</option><option value="false">{t("result.failed")}</option></Select>
          <Select value={f.writing_pending} onChange={(e) => set("writing_pending", e.target.value)} className="w-52"><option value="">{t("results.anyWriting")}</option><option value="true">{t("results.writingWaiting")}</option></Select>
          {mode === "all" && <Select value={f.approval_status} onChange={(e) => set("approval_status", e.target.value)} className="w-44"><option value="">{t("results.allApprovals")}</option>{["PENDING", "APPROVED", "REJECTED"].map((s) => <option key={s} value={s}>{t(`approval.${s}`)}</option>)}</Select>}
          <Input type="date" value={f.date_from} onChange={(e) => set("date_from", e.target.value)} aria-label={t("results.from")} />
          <Input type="date" value={f.date_to} onChange={(e) => set("date_to", e.target.value)} aria-label={t("results.to")} />
        </FilterBar>
      )}

      {user!.role === "STUDENT" ? <StudentHistory rows={list.data?.results ?? []} /> : (
      <Table head={[t("common.student"), t("results.exam"), t("common.level"), t("result.score"), t("result.status"), t("approval.title"), t("common.date"), ""]} empty={!list.data?.results.length}>
        {list.data?.results.map((r) => (
          <tr key={r.id} className="hover:bg-slate-50">
            <Td><Link className="font-medium text-indigo-700 hover:underline" to={`/results/${r.id}`}>{r.student_name}</Link><div className="text-xs text-slate-400">{r.student_phone}</div></Td>
            <Td>{r.examination_title}<div><KindBadge kind={r.kind} /></div></Td>
            <Td><LevelBadge code={r.level_code} />{r.target_level_code && <> → <LevelBadge code={r.target_level_code} /></>}</Td>
            <Td className="whitespace-nowrap tabular-nums">{num(r.total_score)} / {num(r.max_score)} {t("exam.points")}</Td>
            <Td><OutcomeBadge r={r} /></Td>
            <Td><ApprovalBadge status={r.approval_status} /></Td>
            <Td className="whitespace-nowrap">{fmtDate(r.created_at)}</Td>
            <Td className="whitespace-nowrap text-right">
              {staff && r.approval_status === "PENDING" && <>
                <Button size="sm" variant="success" className="mr-2" onClick={() => setReview({ r, mode: "approve" })}>{t("approvals.approve")}</Button>
                <Button size="sm" variant="danger" onClick={() => setReview({ r, mode: "reject" })}>{t("approvals.reject")}</Button></>}
            </Td>
          </tr>
        ))}
      </Table>
      )}
      <Pagination page={page} count={list.data?.count ?? 0} onPage={setPage} />
      <ReviewModal result={review?.r ?? null} mode={review?.mode ?? "approve"} onClose={() => setReview(null)}
        onDone={() => { setReview(null); void qc.invalidateQueries({ queryKey: ["results"] }); void qc.invalidateQueries({ queryKey: ["analytics/dashboard"] }); }} />
    </>
  );
}
