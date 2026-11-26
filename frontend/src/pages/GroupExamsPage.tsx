import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";

import { api, download } from "../api/client";
import { LevelBadge, OutcomeBadge } from "../components/badges";
import { Badge, Button, Card, EmptyState, FilterBar, PageHeader, PageLoader, ProgressBar, SearchInput, Select, Table, Td, cx } from "../components/ui";
import { fmtDate } from "../lib/hooks";

type Status = "waiting" | "in_progress" | "finished";
type MemberState = "not_assigned" | "waiting" | "in_progress" | "finished";
interface Member {
  student_id: number; name: string; state: MemberState; result_id: number | null; score: number | null; max: number | null; passed: boolean | null;
  writing_pending: boolean; awaiting: boolean; approval_status: string | null; correct: number | null; incorrect: number | null; unanswered: number | null;
  finished_at: string | null; sections: Record<string, { score: number; max: number }> | null;
}
interface Row {
  exam_id: number; exam_title: string; group_id: number; group_name: string; level: string; teacher: string | null; status: Status;
  students: number; assigned: number; waiting: number; in_progress: number; finished: number; passed: number;
  average: number | null; max: number | null; members: Member[];
}

const num = (v: number) => v.toLocaleString(undefined, { maximumFractionDigits: 1 });
const statusTone: Record<Status, "amber" | "gray" | "green"> = { in_progress: "amber", waiting: "gray", finished: "green" };
const memberTone: Record<MemberState, "amber" | "gray" | "green" | "indigo"> = { in_progress: "amber", waiting: "indigo", finished: "green", not_assigned: "gray" };

function useGroupExams() {
  return useQuery({ queryKey: ["analytics/group-exams"], refetchInterval: 15000, queryFn: async () => (await api.get<Row[]>("/analytics/group-exams/")).data });
}

/** Admin: which group is sitting / has sat which upgrade exam, and every student's score in points (refreshes every 15 s). */
export default function GroupExamsPage() {
  const { t } = useTranslation();
  const q = useGroupExams();
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  if (!q.data) return <PageLoader />;

  const s = search.trim().toLowerCase();
  const rows = q.data.filter((r) => (!status || r.status === status) && (!s || `${r.group_name} ${r.exam_title} ${r.teacher ?? ""}`.toLowerCase().includes(s)));
  const count = (x: Status) => q.data.filter((r) => r.status === x).length;

  return (
    <>
      <PageHeader title={t("nav.groupExams")} subtitle={t("groupExams.subtitle")} />
      <FilterBar>
        <SearchInput value={search} onChange={setSearch} />
        <Select aria-label={t("common.status")} value={status} onChange={(e) => setStatus(e.target.value)} className="w-56">
          <option value="">{t("common.allStatuses")} ({q.data.length})</option>
          {(["in_progress", "waiting", "finished"] as Status[]).map((x) => <option key={x} value={x}>{t(`groupExams.status.${x}`)} ({count(x)})</option>)}
        </Select>
      </FilterBar>
      {rows.length === 0 ? <Card><EmptyState text={t("groupExams.empty")} /></Card> : (
        <div className="space-y-4">
          {rows.map((r) => {
            const key = `${r.exam_id}-${r.group_id}`;
            const shown = open === key;
            return (
              <Card key={key}>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <Link to={`/group-exams/${r.exam_id}/${r.group_id}`} className="text-base font-semibold text-slate-900 hover:text-indigo-700 hover:underline">{r.group_name}</Link> <LevelBadge code={r.level} />
                    <p className="mt-0.5 text-sm text-slate-600"><Link to={`/group-exams/${r.exam_id}/${r.group_id}`} className="text-indigo-700 hover:underline">{r.exam_title}</Link> · {r.teacher ?? t("groupExams.noTeacher")}</p>
                  </div>
                  <Badge tone={statusTone[r.status]}>{t(`groupExams.status.${r.status}`)}</Badge>
                </div>
                <div className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-5">
                  <Fact label={t("groupExams.assigned")} value={`${r.assigned} / ${r.students}`} />
                  <Fact label={t("groupExams.waiting")} value={r.waiting} />
                  <Fact label={t("groupExams.inProgress")} value={r.in_progress} />
                  <Fact label={t("groupExams.finished")} value={`${r.finished} / ${r.assigned}`} />
                  <Fact label={t("groupExams.average")} value={r.average === null ? "—" : `${num(r.average)} / ${num(r.max!)} ${t("exam.points")}`} />
                </div>
                <ProgressBar className="mt-3" tone="green" value={r.assigned ? (r.finished / r.assigned) * 100 : 0} />
                <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-sm font-medium">
                  <Link to={`/group-exams/${r.exam_id}/${r.group_id}`} className="rounded-lg bg-indigo-600 px-3 py-1.5 text-white hover:bg-indigo-700">{t("groupExams.openResults")} →</Link>
                  <button type="button" className="text-indigo-700 hover:underline" aria-expanded={shown} onClick={() => setOpen(shown ? null : key)}>
                    {shown ? t("groupExams.hideStudents") : t("groupExams.showStudents", { n: r.members.length })}{r.finished > 0 && ` · ${t("groupExams.passedN", { n: r.passed })}`}
                  </button>
                </div>
                {shown && (
                  <ul className="mt-3 divide-y divide-slate-100 rounded-xl border border-slate-200 text-sm">
                    {r.members.map((m) => (
                      <li key={m.student_id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5">
                        <span className={cx("font-medium", m.state === "not_assigned" && "text-slate-400")}>{m.name}</span>
                        <span className="flex flex-wrap items-center gap-2">
                          {m.state === "finished" && m.result_id ? (
                            <>
                              <Link to={`/results/${m.result_id}`} className="font-semibold tabular-nums text-indigo-700 hover:underline">{num(m.score!)} / {num(m.max!)} {t("exam.points")}</Link>
                              <OutcomeBadge r={{ ...m, kind: "UPGRADE", approval_status: m.approval_status ?? undefined }} />
                            </>
                          ) : <Badge tone={memberTone[m.state]}>{t(`groupExams.member.${m.state}`)}</Badge>}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
            );
          })}
        </div>
      )}
    </>
  );
}

const Fact = ({ label, value }: { label: string; value: React.ReactNode }) => (
  <div className="rounded-lg bg-slate-50 px-3 py-2"><p className="text-xs text-slate-500">{label}</p><p className="font-semibold tabular-nums text-slate-900">{value}</p></div>
);

const stateOrder: Record<MemberState, number> = { finished: 0, in_progress: 1, waiting: 2, not_assigned: 3 };

/** One group's sitting of one exam: every student's result (score, right / wrong / skipped, sections, decision). */
export function GroupExamDetailPage() {
  const { t } = useTranslation();
  const { exam, group } = useParams();
  const q = useGroupExams();
  if (!q.data) return <PageLoader />;
  const r = q.data.find((x) => String(x.exam_id) === exam && String(x.group_id) === group);
  if (!r) return <Card><EmptyState text={t("groupExams.notFound")} /></Card>;
  const members = [...r.members].sort((a, b) => stateOrder[a.state] - stateOrder[b.state] || (b.score ?? -1) - (a.score ?? -1) || a.name.localeCompare(b.name));
  const sectionNames = [...new Set(members.flatMap((m) => Object.keys(m.sections ?? {})))];
  return (
    <>
      <PageHeader title={`${r.group_name} — ${r.exam_title}`} subtitle={`${r.level} · ${r.teacher ?? t("groupExams.noTeacher")}`}
        actions={<><Button variant="secondary" onClick={() => void download("/results/export/", { examination: r.exam_id, group: r.group_id, file: "xlsx" }, `${r.group_name} - ${r.exam_title}.xlsx`).catch(() => undefined)}>Excel</Button>
          <Button variant="secondary" onClick={() => void download("/results/export/", { examination: r.exam_id, group: r.group_id, file: "pdf" }, `${r.group_name} - ${r.exam_title}.pdf`).catch(() => undefined)}>PDF</Button>
          <Badge tone={statusTone[r.status]}>{t(`groupExams.status.${r.status}`)}</Badge><Link to={`/exams/${r.exam_id}`} className="text-sm font-medium text-indigo-700 hover:underline">{t("groupExams.openExam")}</Link></>} />
      <div className="mb-6 grid grid-cols-2 gap-3 text-sm sm:grid-cols-5">
        <Fact label={t("groupExams.assigned")} value={`${r.assigned} / ${r.students}`} />
        <Fact label={t("groupExams.waiting")} value={r.waiting} />
        <Fact label={t("groupExams.inProgress")} value={r.in_progress} />
        <Fact label={t("groupExams.finished")} value={`${r.finished} / ${r.assigned}`} />
        <Fact label={t("groupExams.average")} value={r.average === null ? "—" : `${num(r.average)} / ${num(r.max!)} ${t("exam.points")}`} />
      </div>
      <Table head={["#", t("nav.students"), t("result.score"), t("groupExams.answers"), ...sectionNames.map((s) => t(`sections.${s}`)), t("result.status"), t("groupExams.finishedAt"), ""]} empty={!members.length}>
        {members.map((m, i) => (
          <tr key={m.student_id} className="hover:bg-slate-50">
            <Td className="tabular-nums text-slate-500">{i + 1}</Td>
            <Td className={cx("font-medium", m.state === "not_assigned" && "text-slate-400")}>{m.name}</Td>
            {m.state === "finished" && m.score !== null ? (
              <>
                <Td className="min-w-36">
                  <p className="whitespace-nowrap font-semibold tabular-nums">{num(m.score)} / {num(m.max!)} {t("exam.points")}</p>
                  <ProgressBar className="mt-1" value={m.max ? (m.score / m.max) * 100 : 0} tone={m.passed ? "green" : "amber"} />
                </Td>
                <Td className="whitespace-nowrap text-xs">
                  <span className="text-emerald-700">✓ {m.correct}</span> · <span className="text-red-600">✗ {m.incorrect}</span> · <span className="text-slate-500">— {m.unanswered}</span>
                </Td>
                {sectionNames.map((s) => {
                  const x = m.sections?.[s];
                  return <Td key={s} className="whitespace-nowrap tabular-nums text-xs">{x ? `${num(x.score)} / ${num(x.max)}` : "—"}</Td>;
                })}
                <Td><OutcomeBadge r={{ ...m, kind: "UPGRADE", approval_status: m.approval_status ?? undefined }} /></Td>
                <Td className="whitespace-nowrap text-xs text-slate-500">{m.finished_at ? fmtDate(m.finished_at) : "—"}</Td>
                <Td className="text-right">{m.result_id && <Link to={`/results/${m.result_id}`} className="whitespace-nowrap text-sm font-medium text-indigo-700 hover:underline">{t("groupExams.openResult")} →</Link>}</Td>
              </>
            ) : (
              <>
                <Td>—</Td><Td>—</Td>{sectionNames.map((s) => <Td key={s}>—</Td>)}
                <Td><Badge tone={memberTone[m.state]}>{t(`groupExams.member.${m.state}`)}</Badge></Td><Td /><Td />
              </>
            )}
          </tr>
        ))}
      </Table>
    </>
  );
}
