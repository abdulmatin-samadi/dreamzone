import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";
import { KindBadge, LevelBadge, OutcomeBadge } from "../components/badges";
import { Card, EmptyState, PageHeader, PageLoader, ProgressBar, StatCard, Table, Td } from "../components/ui";
import { fmtDate, num, useGet } from "../lib/hooks";

interface Avg { avg_score: number | null; avg_max: number | null }
interface Summary extends Avg { results: number; graded: number; passed: number; failed: number; best_score: number | null; best_max: number | null; awaiting: number; writing_pending: number }
interface SectionRow { section: string; score: number; max: number }
interface TimelineRow { id: number; date: string; examination: string; kind: string; score: number; max: number; passed: boolean | null; writing_pending: boolean }
interface MonthRow extends Avg { month: string; results: number; passed: number }
interface StudentRow extends Avg { id: number; name: string; results: number; passed: number; last: string }
interface Stats {
  role: string; summary: Summary; sections: SectionRow[];
  timeline?: TimelineRow[]; level?: { current: string | null; initial: string | null };
  monthly?: MonthRow[]; groups?: (Avg & { id: number; name: string; level: string; students: number; results: number; passed: number; graded: number })[];
  top_students?: StudentRow[]; attention?: StudentRow[];
  exams?: (Avg & { id: number; title: string; kind: string; results: number; passed: number })[];
}

/** "64 / 80 ball" (or "—" when nothing is graded yet). */
function usePts() {
  const { t } = useTranslation();
  return (score: number | null | undefined, max: number | null | undefined) =>
    score === null || score === undefined || !max ? "—" : `${num(score)} / ${num(max)} ${t("exam.points")}`;
}

/** One series of scores over time in points: 0 → the biggest maximum on the axis, 2px line, hover tooltip on every point. */
function TrendChart({ points, label }: { points: { x: string; y: number; max: number; tip: string }[]; label: string }) {
  const { t } = useTranslation();
  const pts = usePts();
  const [hover, setHover] = useState<number | null>(null);
  const top = Math.max(1, ...points.map((p) => p.max));
  const W = 720, H = 240, L = 44, R = 16, T = 14, B = 34;
  const n = points.length;
  const px = (i: number) => (n === 1 ? L + (W - L - R) / 2 : L + (i * (W - L - R)) / (n - 1));
  const py = (v: number) => T + ((top - v) / top) * (H - T - B);
  const line = points.map((p, i) => `${i ? "L" : "M"}${px(i).toFixed(1)} ${py(p.y).toFixed(1)}`).join(" ");
  const area = n > 1 ? `${line} L${px(n - 1).toFixed(1)} ${py(0)} L${px(0).toFixed(1)} ${py(0)} Z` : "";
  const every = Math.max(1, Math.ceil(n / 8));  // x labels: at most ~8
  const h = hover !== null ? points[hover] : null;
  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full text-indigo-600" role="img" aria-label={label}>
        <defs>
          <linearGradient id="trend-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="currentColor" stopOpacity="0.18" /><stop offset="1" stopColor="currentColor" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0, top / 2, top].map((v, k) => (
          <g key={k}>
            <line x1={L} x2={W - R} y1={py(v)} y2={py(v)} className="stroke-slate-200" strokeWidth="1" strokeDasharray={k === 1 ? "4 4" : undefined} />
            <text x={L - 8} y={py(v) + 4} textAnchor="end" className="fill-slate-500" fontSize="12">{num(Math.round(v * 10) / 10)}</text>
          </g>
        ))}
        <g>
          {area && <path d={area} fill="url(#trend-fill)" />}
          {n > 1 && <path d={line} fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />}
          {points.map((p, i) => (
            <g key={i} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} onFocus={() => setHover(i)} onBlur={() => setHover(null)} tabIndex={0} aria-label={`${p.x}: ${pts(p.y, p.max)}`}>
              <circle cx={px(i)} cy={py(p.y)} r="14" fill="transparent" />
              <circle cx={px(i)} cy={py(p.y)} r={hover === i ? 6 : 4.5} fill="currentColor" className="stroke-white" strokeWidth="2" />
            </g>
          ))}
        </g>
        {n > 0 && hover === null && (  // direct label on the latest point only
          <text x={px(n - 1)} y={py(points[n - 1].y) - 12} textAnchor={n > 1 ? "end" : "middle"} className="fill-slate-700" fontSize="13" fontWeight="600">{num(points[n - 1].y)} {t("exam.points")}</text>
        )}
        {hover !== null && <line x1={px(hover)} x2={px(hover)} y1={T} y2={H - B} className="stroke-slate-300" strokeWidth="1" />}
        {points.map((p, i) => (i % every === 0 || i === n - 1) && (
          <text key={i} x={px(i)} y={H - 10} textAnchor={n > 1 && i === 0 ? "start" : n > 1 && i === n - 1 ? "end" : "middle"} className="fill-slate-500" fontSize="12">{p.x}</text>
        ))}
      </svg>
      {h && hover !== null && (
        <div className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs shadow-lg"
          style={{ left: `${(px(hover) / W) * 100}%`, top: `${(py(h.y) / H) * 100 - 3}%` }}>
          <p className="font-semibold text-slate-900">{pts(h.y, h.max)}</p>
          <p className="text-slate-500">{h.tip}</p>
        </div>
      )}
    </div>
  );
}

function Sections({ rows }: { rows: SectionRow[] }) {
  const { t } = useTranslation();
  if (!rows.length) return <EmptyState text={t("stats.noGraded")} />;
  const best = rows[0], worst = rows[rows.length - 1];
  return (
    <>
      <ul className="space-y-4">
        {rows.map((r) => (
          <li key={r.section}>
            <div className="mb-1 flex justify-between text-sm"><span className="text-slate-700">{t(`sections.${r.section}`)}</span>
              <span className="font-medium tabular-nums text-slate-900">{num(r.score)} / {num(r.max)} {t("exam.points")}</span></div>
            <ProgressBar value={(r.score / r.max) * 100} />
          </li>
        ))}
      </ul>
      {rows.length > 1 && (
        <div className="mt-5 grid gap-2 text-sm sm:grid-cols-2">
          <p className="rounded-xl bg-emerald-50 px-3 py-2 text-emerald-800">💪 {t("stats.strong")}: <b>{t(`sections.${best.section}`)}</b></p>
          <p className="rounded-xl bg-amber-50 px-3 py-2 text-amber-800">🎯 {t("stats.weak")}: <b>{t(`sections.${worst.section}`)}</b></p>
        </div>
      )}
    </>
  );
}

function SummaryCards({ s, extra }: { s: Summary; extra?: React.ReactNode }) {
  const { t } = useTranslation();
  const pts = usePts();
  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      {extra}
      <StatCard label={t("stats.results")} value={s.results} hint={s.writing_pending ? t("stats.pendingShort", { n: s.writing_pending }) : undefined} />
      <StatCard label={t("stats.average")} value={pts(s.avg_score, s.avg_max)} />
      <StatCard label={t("stats.passed")} value={`${s.passed} / ${s.graded}`} hint={s.awaiting ? t("stats.awaitingShort", { n: s.awaiting }) : undefined} />
    </div>
  );
}

function StudentStats({ d }: { d: Stats }) {
  const { t } = useTranslation();
  const graded = (d.timeline ?? []).filter((r) => !r.writing_pending);
  const level = d.level;
  return (
    <div className="space-y-6">
      <SummaryCards s={d.summary} extra={<StatCard label={t("stats.currentLevel")} value={level?.current ?? "—"} hint={level?.initial ? t("stats.initialLevel", { level: level.initial }) : undefined} />} />
      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2" title={t("stats.progress")}>
          {graded.length ? <TrendChart label={t("stats.progress")} points={graded.map((r) => ({ x: fmtDate(r.date, false), y: r.score, max: r.max, tip: r.examination }))} />
            : <EmptyState text={t("stats.noGraded")} />}
          {d.summary.best_score !== null && <p className="mt-3 text-sm text-slate-500">{t("stats.bestResult", { score: `${num(d.summary.best_score)} / ${num(d.summary.best_max!)}` })}</p>}
        </Card>
        <Card title={t("stats.sections")}><Sections rows={d.sections} /></Card>
      </div>
      <Card title={t("stats.allResults")}>
        <Table head={[t("common.date"), t("results.exam"), t("result.score"), t("result.status"), ""]} empty={!d.timeline?.length}>
          {[...(d.timeline ?? [])].reverse().map((r) => (
            <tr key={r.id}>
              <Td className="whitespace-nowrap">{fmtDate(r.date)}</Td>
              <Td>{r.examination}<div><KindBadge kind={r.kind} /></div></Td>
              <Td className="whitespace-nowrap tabular-nums">{r.score} / {r.max} {t("exam.points")}</Td>
              <Td><OutcomeBadge r={r} /></Td>
              <Td className="text-right"><Link className="text-sm text-indigo-600 hover:underline" to={`/results/${r.id}`}>{t("stats.open")}</Link></Td>
            </tr>
          ))}
        </Table>
      </Card>
    </div>
  );
}

function StudentList({ rows, empty }: { rows: StudentRow[]; empty: string }) {
  const { t } = useTranslation();
  const pts = usePts();
  if (!rows.length) return <EmptyState text={empty} />;
  return (
    <ul className="divide-y divide-slate-100">
      {rows.map((s) => (
        <li key={s.id} className="flex items-center justify-between gap-3 py-2.5 text-sm">
          <Link to={`/students/${s.id}`} className="min-w-0 truncate font-medium text-indigo-700 hover:underline">{s.name}</Link>
          <span className="shrink-0 text-slate-500">{t("stats.resultsN", { n: s.results })} · <b className="text-slate-900">{pts(s.avg_score, s.avg_max)}</b></span>
        </li>
      ))}
    </ul>
  );
}

function StaffStats({ d }: { d: Stats }) {
  const { t } = useTranslation();
  const pts = usePts();
  const months = d.monthly ?? [];
  return (
    <div className="space-y-6">
      <SummaryCards s={d.summary} extra={<StatCard label={t("stats.writingPending")} value={d.summary.writing_pending} />} />
      {d.summary.writing_pending > 0 && (d.role === "TEACHER" ? (
        <Link to="/writing" className="block rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm font-medium text-amber-900 hover:bg-amber-100">
          ✍️ {t("stats.pendingNote", { n: d.summary.writing_pending })} →
        </Link>
      ) : (
        <p className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm font-medium text-amber-900">✍️ {t("stats.pendingNote", { n: d.summary.writing_pending })}</p>
      ))}
      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2" title={t("stats.monthly")}>
          {months.length ? <TrendChart label={t("stats.monthly")} points={months.map((m) => ({ x: m.month, y: m.avg_score ?? 0, max: m.avg_max ?? 0, tip: t("stats.monthTip", { n: m.results, passed: m.passed }) }))} />
            : <EmptyState text={t("stats.noGraded")} />}
        </Card>
        <Card title={t("stats.sectionsClass")}><Sections rows={d.sections} /></Card>
      </div>
      <Card title={t("stats.groups")}>
        <Table head={[t("common.name"), t("common.level"), t("stats.students"), t("stats.results"), t("stats.average"), t("stats.passed")]} empty={!d.groups?.length}>
          {d.groups?.map((g) => (
            <tr key={g.id}>
              <Td className="font-medium">{g.name}</Td><Td><LevelBadge code={g.level} /></Td><Td>{g.students}</Td><Td>{g.results}</Td>
              <Td className="whitespace-nowrap">{pts(g.avg_score, g.avg_max)}</Td><Td>{g.graded ? `${g.passed} / ${g.graded}` : "—"}</Td>
            </tr>
          ))}
        </Table>
      </Card>
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title={`🏆 ${t("stats.topStudents")}`}><StudentList rows={d.top_students ?? []} empty={t("stats.noGraded")} /></Card>
        <Card title={`🎯 ${t("stats.attention")}`}><StudentList rows={d.attention ?? []} empty={t("stats.attentionNone")} /></Card>
      </div>
      <Card title={t("stats.exams")}>
        <Table head={[t("results.exam"), t("stats.results"), t("stats.average"), t("stats.passed")]} empty={!d.exams?.length}>
          {d.exams?.map((e) => (
            <tr key={e.id}>
              <Td>{e.title}<div><KindBadge kind={e.kind} /></div></Td><Td>{e.results}</Td><Td className="whitespace-nowrap">{pts(e.avg_score, e.avg_max)}</Td><Td>{e.passed} / {e.results}</Td>
            </tr>
          ))}
        </Table>
      </Card>
    </div>
  );
}

export default function StatsPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const q = useGet<Stats>("analytics/stats");
  const student = user!.role === "STUDENT";
  return (
    <>
      <PageHeader title={t("stats.title")} subtitle={t(student ? "stats.subtitleStudent" : "stats.subtitleStaff")} />
      {q.isLoading || !q.data ? <PageLoader /> : student ? <StudentStats d={q.data} /> : <StaffStats d={q.data} />}
    </>
  );
}
