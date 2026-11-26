import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";

import { api } from "../api/client";
import type { Level, LevelChange, Result, Student } from "../api/types";
import { LoadError } from "../components/NotFound";
import { useAuth } from "../auth/AuthContext";
import { ApprovalBadge, KindBadge, LevelBadge, OutcomeBadge } from "../components/badges";
import { useNotify } from "../components/Toast";
import { Button, Card, EmptyState, Modal, PageHeader, PageLoader, Select, StatCard, Table, Td, Textarea } from "../components/ui";
import { fmtDate, num, useGet } from "../lib/hooks";

interface Report { student: Student; results: Result[]; level_history: LevelChange[] }

export default function StudentDetailPage() {
  const { id } = useParams();
  const { t } = useTranslation();
  const { user } = useAuth();
  const notify = useNotify();
  const qc = useQueryClient();
  const levels = useGet<Level[]>("levels");
  const q = useQuery({ queryKey: ["students", id, "report"], queryFn: async () => (await api.get<Report>(`/students/${id}/report/`)).data });
  const [lvlOpen, setLvlOpen] = useState(false);
  const [lvl, setLvl] = useState({ level: "", note: "" });
  const [busy, setBusy] = useState(false);
  if (q.isError) return <LoadError />;
  if (!q.data) return <PageLoader />;
  const { student: s, results, level_history } = q.data;
  const passedCount = results.filter((r) => r.passed).length;
  const avgScore = results.length ? results.reduce((a, r) => a + Number(r.total_score), 0) / results.length : 0;
  const avgMax = results.length ? results.reduce((a, r) => a + Number(r.max_score), 0) / results.length : 0;

  const setLevel = async () => {
    setBusy(true);
    try { await api.post(`/students/${s.id}/set-level/`, lvl); notify.ok("common.saved"); setLvlOpen(false); void qc.invalidateQueries({ queryKey: ["students"] }); }
    catch (e) { notify.fail(e); } finally { setBusy(false); }
  };

  return (
    <>
      <PageHeader title={s.full_name} subtitle={`${s.phone} · ${s.username}`}
        actions={user!.role === "ADMIN" ? <Button variant="secondary" onClick={() => setLvlOpen(true)}>{t("students.changeLevel")}</Button> : undefined} />
      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label={t("students.currentLevel")} value={s.current_level_code ?? "—"} />
        <StatCard label={t("students.attempts")} value={results.length} />
        <StatCard label={t("result.passed")} value={passedCount} />
        <StatCard label={t("results.average")} value={results.length ? `${num(avgScore.toFixed(1))} / ${num(avgMax.toFixed(1))} ${t("exam.points")}` : "—"} />
      </div>
      <div className="space-y-6">
        <Card title={t("students.examHistory")}>
          {results.length === 0 ? <EmptyState /> : (
            <Table head={[t("results.exam"), t("common.level"), t("result.score"), t("result.status"), t("approval.title"), t("common.date")]}>
              {results.map((r) => (
                <tr key={r.id}>
                  <Td><Link className="font-medium text-indigo-700 hover:underline" to={`/results/${r.id}`}>{r.examination_title}</Link><div><KindBadge kind={r.kind} /></div></Td>
                  <Td><LevelBadge code={r.level_code} />{r.target_level_code && <> → <LevelBadge code={r.target_level_code} /></>}</Td>
                  <Td className="whitespace-nowrap tabular-nums">{num(r.total_score)} / {num(r.max_score)} {t("exam.points")}</Td><Td><OutcomeBadge r={r} /></Td><Td><ApprovalBadge status={r.approval_status} /></Td><Td>{fmtDate(r.created_at)}</Td>
                </tr>
              ))}
            </Table>
          )}
        </Card>
        <Card title={t("students.levelHistory")}>
          {level_history.length === 0 ? <EmptyState /> : (
            <ul className="divide-y divide-slate-100 text-sm">
              {level_history.map((h) => (
                <li key={h.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                  <span><LevelBadge code={h.from_level_code} /> → <LevelBadge code={h.to_level_code} /> <span className="ml-2 text-slate-500">{t(`students.reason.${h.reason}`)}</span>{h.note && <span className="ml-2 text-slate-400">— {h.note}</span>}</span>
                  <span className="text-slate-500">{h.changed_by_name ?? t("students.system")} · {fmtDate(h.created_at)}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
      <Modal open={lvlOpen} onClose={() => setLvlOpen(false)} title={t("students.changeLevel")}
        footer={<><Button variant="secondary" onClick={() => setLvlOpen(false)}>{t("common.cancel")}</Button><Button loading={busy} disabled={!lvl.level} onClick={setLevel}>{t("common.save")}</Button></>}>
        <Select label={t("common.level")} value={lvl.level} onChange={(e) => setLvl({ ...lvl, level: e.target.value })}><option value="">—</option>{levels.data?.map((l) => <option key={l.id} value={l.id}>{l.code} — {l.name}</option>)}</Select>
        <Textarea className="mt-3" label={t("approvals.note")} value={lvl.note} onChange={(e) => setLvl({ ...lvl, note: e.target.value })} />
      </Modal>
    </>
  );
}
