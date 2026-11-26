import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import type { Result } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { LevelBadge, OutcomeBadge } from "../components/badges";
import { StoppedAttempts } from "../components/StoppedAttempts";
import { BarList, Button, Card, EmptyState, PageHeader, PageLoader, StatCard, Table, Td } from "../components/ui";
import { fmtDate, num, useGet } from "../lib/hooks";

type Totals = Record<string, number>;
interface Dash {
  totals?: Totals; students_by_level?: { level: string; count: number }[]; pass_fail?: { passed: number; failed: number };
  recent_results?: Result[]; pending_results?: Result[];
  question_bank?: { total: number; by_section: { section: string; count: number }[]; by_type: { question_type: string; count: number }[]; by_level: { level_code: string; count: number }[] };
  schedule?: { id: number; examination: string; student: string; available_from: string | null; available_until: string | null }[];
  groups?: number; current_level?: string | null; current_level_name?: string | null; available?: number; completed?: number;
}

function RecentResults({ rows, title }: { rows: Result[]; title: string }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  return (
    <Card title={title} actions={user!.role === "ADMIN" ? undefined : <Link to="/results" className="text-sm text-indigo-600 hover:underline">{t("common.viewAll")}</Link>}>
      {rows.length === 0 ? <EmptyState /> : (
        <Table head={[t("common.student"), t("results.exam"), t("common.level"), t("result.score"), t("result.status")]}>
          {rows.map((r) => (
            <tr key={r.id}>
              <Td><Link className="font-medium text-indigo-700 hover:underline" to={`/results/${r.id}`}>{r.student_name}</Link></Td>
              <Td>{r.examination_title}</Td><Td><LevelBadge code={r.level_code} /></Td>
              <Td className="whitespace-nowrap tabular-nums">{num(r.total_score)} / {num(r.max_score)} {t("exam.points")}</Td><Td><OutcomeBadge r={r} /></Td>
            </tr>
          ))}
        </Table>
      )}
    </Card>
  );
}

export default function DashboardPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const q = useGet<Dash>("analytics/dashboard");
  if (q.isLoading || !q.data) return <PageLoader />;
  const d = q.data;
  const role = user!.role;

  return (
    <>
      <PageHeader title={t("dashboard.welcome", { name: user!.first_name })} subtitle={t(`dashboard.subtitle.${role}`)}
        actions={role === "RECEPTIONIST" ? <Link to="/placements"><Button>{t("nav.placements")}</Button></Link> : undefined} />

      {role === "STUDENT" && (
        <div className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-3">
            <StatCard label={t("dashboard.currentLevel")} value={d.current_level ?? "—"} hint={d.current_level_name ?? t("dashboard.levelNotSet")} />
            <StatCard label={t("dashboard.availableExams")} value={d.available ?? 0} />
            <StatCard label={t("dashboard.completedExams")} value={d.completed ?? 0} />
          </div>
          {(d.groups ?? 0) === 0 && (
            <Card>
              <div className="flex flex-wrap items-center justify-between gap-4">
                <p className="text-sm text-slate-600">{t("dashboard.joinGroupHint")}</p>
                <Link to="/my-group"><Button variant="secondary">{t("myGroup.joinButton")}</Button></Link>
              </div>
            </Card>
          )}
          <RecentResults rows={d.recent_results ?? []} title={t("dashboard.recentResults")} />
        </div>
      )}

      {role === "RECEPTIONIST" && (
        <div className="space-y-6">
          <StoppedAttempts />
          {(d.totals!.writing_pending ?? 0) > 0 && (
            <Link to="/writing" className="block rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm font-medium text-amber-900 hover:bg-amber-100">
              ✍️ {t("dashboard.writingWaiting", { n: d.totals!.writing_pending })} →
            </Link>
          )}
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
            <StatCard label={t("dashboard.registeredToday")} value={d.totals!.registered_today} />
            <StatCard label={t("dashboard.waiting")} value={d.totals!.waiting} />
            <StatCard label={t("dashboard.inProgress")} value={d.totals!.in_progress} />
            <StatCard label={t("dashboard.pendingOffers")} value={d.totals!.pending_offers} />
            <StatCard label={t("dashboard.awaitingGroup")} value={d.totals!.awaiting_group} />
          </div>
          <RecentResults rows={d.recent_results ?? []} title={t("dashboard.recentResults")} />
        </div>
      )}

      {role === "TEACHER" && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard label={t("nav.myStudents")} value={d.totals!.students} />
            <StatCard label={t("nav.myGroups")} value={d.totals!.groups} />
            <StatCard label={t("nav.exams")} value={d.totals!.examinations} />
            <StatCard label={t("dashboard.pendingApprovals")} value={d.totals!.pending_approvals} />
          </div>
          {(d.totals!.writing_pending ?? 0) > 0 && (
            <Link to="/writing" className="block rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm font-medium text-amber-900 hover:bg-amber-100">
              ✍️ {t("dashboard.writingWaiting", { n: d.totals!.writing_pending })} →
            </Link>
          )}
          <div className="grid gap-6 lg:grid-cols-2">
            <Card title={t("dashboard.passFail")}>
              <BarList rows={[{ label: t("result.passed"), value: d.pass_fail!.passed, tone: "green" }, { label: t("result.failed"), value: d.pass_fail!.failed, tone: "red" }]} />
            </Card>
            <Card title={t("dashboard.upcoming")} actions={<Link to="/schedule" className="text-sm text-indigo-600 hover:underline">{t("common.viewAll")}</Link>}>
              {d.schedule!.length === 0 ? <EmptyState /> : (
                <ul className="divide-y divide-slate-100 text-sm">
                  {d.schedule!.map((s) => <li key={s.id} className="flex justify-between py-2"><span>{s.student} · {s.examination}</span><span className="text-slate-500">{fmtDate(s.available_from)}</span></li>)}
                </ul>
              )}
            </Card>
          </div>
          {d.pending_results!.length > 0 && <RecentResults rows={d.pending_results!} title={t("dashboard.pendingApprovals")} />}
          <RecentResults rows={d.recent_results ?? []} title={t("dashboard.recentResults")} />
        </div>
      )}

      {role === "ADMIN" && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard label={t("dashboard.totalStudents")} value={d.totals!.students} />
            <StatCard label={t("dashboard.totalTeachers")} value={d.totals!.teachers} />
            <StatCard label={t("dashboard.totalExams")} value={d.totals!.examinations} />
            <StatCard label={t("dashboard.totalAttempts")} value={d.totals!.attempts} />
          </div>
          <div className="grid gap-6 lg:grid-cols-3">
            <Card title={t("dashboard.studentsByLevel")}><BarList rows={d.students_by_level!.map((x) => ({ label: x.level, value: x.count }))} /></Card>
            <Card title={t("dashboard.passFail")}>
              <BarList rows={[{ label: t("result.passed"), value: d.pass_fail!.passed, tone: "green" }, { label: t("result.failed"), value: d.pass_fail!.failed, tone: "red" }]} />
              <p className="mt-4 text-xs text-slate-500">{t("dashboard.pendingApprovals")}: {d.totals!.pending_approvals}</p>
            </Card>
            <Card title={`${t("dashboard.questionBank")} (${d.question_bank!.total})`}>
              <BarList rows={d.question_bank!.by_section.map((x) => ({ label: t(`sections.${x.section}`), value: x.count, tone: "amber" }))} />
              <div className="mt-4 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
                {d.question_bank!.by_type.map((x) => <span key={x.question_type}>{t(`qtypes.${x.question_type}`)}: <b>{x.count}</b></span>)}
              </div>
            </Card>
          </div>
          {(d.totals!.writing_pending ?? 0) > 0 && (
            <p className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm font-medium text-amber-900">
              ✍️ {t("dashboard.writingWaitingInfo", { n: d.totals!.writing_pending })}
            </p>
          )}
          <RecentResults rows={d.recent_results ?? []} title={t("dashboard.recentResults")} />
        </div>
      )}
    </>
  );
}
