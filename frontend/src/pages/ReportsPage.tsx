import { useState } from "react";
import { useTranslation } from "react-i18next";

import { download } from "../api/client";
import { useNotify } from "../components/Toast";
import { Button, Card, EmptyState, Input, PageHeader, PageLoader, ProgressBar, Table, Td, cx } from "../components/ui";
import { useGet } from "../lib/hooks";

type Key = "new_students" | "guests" | "placement_tests" | "placement_avg" | "placed" | "joined_group" | "placed_and_joined" | "upgrade_tests" | "upgrade_approved" | "upgrade_rejected";
type Totals = Record<Key, number> & { placement_avg_max?: number };
interface LevelRow { level: string; name: string; placement_tests: number; placed: number; joined_group: number; upgraded_to: number }
interface Report { month: string; title: string; totals: Totals; previous: Totals; by_level: LevelRow[]; by_day: { day: number; placement_tests: number }[] }

const HEADLINE: Key[] = ["placement_tests", "placed", "joined_group", "new_students"];
const DETAIL: Key[] = ["guests", "placement_avg", "placed_and_joined", "upgrade_tests", "upgrade_approved", "upgrade_rejected"];
const thisMonth = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`; };

function Delta({ cur, prev, bad, compact }: { cur: number; prev: number; bad?: boolean; compact?: boolean }) {
  const { t } = useTranslation();
  const d = Math.round((cur - prev) * 10) / 10;
  if (!d) return compact ? null : <span className="text-xs text-slate-400">{t("reports.same")}</span>;
  const good = bad ? d < 0 : d > 0;
  return (
    <span className={cx("whitespace-nowrap text-xs font-medium", good ? "text-emerald-700" : "text-red-700")} title={compact ? t("reports.vsPrev") : undefined}>
      {d > 0 ? "▲ +" : "▼ "}{d}{!compact && <span className="font-normal text-slate-400"> {t("reports.vsPrev")}</span>}
    </span>
  );
}

/** Placement tests per day: one series, one hue, thin bars, hover tooltip. */
function DayBars({ rows }: { rows: Report["by_day"] }) {
  const { t } = useTranslation();
  const [hover, setHover] = useState<number | null>(null);
  const W = 720, H = 180, L = 32, R = 8, T = 12, B = 24;
  const max = Math.max(1, ...rows.map((r) => r.placement_tests));
  const top = Math.max(2, Math.ceil(max / 2) * 2);
  const step = (W - L - R) / rows.length;
  const bw = Math.max(4, Math.min(16, step - 4));
  const y = (v: number) => T + (1 - v / top) * (H - T - B);
  const h = hover !== null ? rows[hover] : null;
  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full text-blue-600" role="img" aria-label={t("reports.byDay")}>
        {[0, top / 2, top].map((v) => (
          <g key={v}>
            <line x1={L} x2={W - R} y1={y(v)} y2={y(v)} className="stroke-slate-200" strokeWidth="1" />
            <text x={L - 6} y={y(v) + 4} textAnchor="end" fontSize="11" className="fill-slate-500">{v}</text>
          </g>
        ))}
        {rows.map((r, i) => {
          const cx0 = L + i * step + step / 2;
          const top0 = y(r.placement_tests), base = y(0);
          const hgt = base - top0;
          const rad = Math.min(4, hgt / 2, bw / 2);
          return (
            <g key={r.day} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
              <rect x={cx0 - step / 2} y={T} width={step} height={H - T - B} fill="transparent" />
              {r.placement_tests > 0 && (
                <path fill="currentColor" opacity={hover === null || hover === i ? 1 : 0.45}
                  d={`M${cx0 - bw / 2} ${base} V${top0 + rad} Q${cx0 - bw / 2} ${top0} ${cx0 - bw / 2 + rad} ${top0} H${cx0 + bw / 2 - rad} Q${cx0 + bw / 2} ${top0} ${cx0 + bw / 2} ${top0 + rad} V${base} Z`} />
              )}
              {(r.day === 1 || r.day % 5 === 0) && <text x={cx0} y={H - 6} textAnchor="middle" fontSize="11" className="fill-slate-500">{r.day}</text>}
            </g>
          );
        })}
      </svg>
      {h && (
        <div className="pointer-events-none absolute top-0 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs shadow-md"
          style={{ left: `${((L + hover! * step + step / 2) / W) * 100}%`, transform: "translateX(-50%)" }}>
          <span className="text-slate-500">{t("reports.day", { d: h.day })}</span> · <span className="font-semibold text-slate-900">{h.placement_tests}</span>
        </div>
      )}
    </div>
  );
}

/** Month by month: placement tests, which level people got, how many joined a group. Excel / PDF download. */
export default function ReportsPage() {
  const { t } = useTranslation();
  const notify = useNotify();
  const [month, setMonth] = useState(thisMonth());
  const q = useGet<Report>("analytics/monthly", { month });
  const [busy, setBusy] = useState<string | null>(null);
  const file = async (kind: "xlsx" | "pdf") => {
    setBusy(kind);
    try { await download("/analytics/monthly/", { month, file: kind }, `hisobot-${month}.${kind}`); } catch (e) { notify.fail(e); } finally { setBusy(null); }
  };
  const r = q.data;
  const conv = r && r.totals.placed ? Math.round((r.totals.placed_and_joined / r.totals.placed) * 100) : null;
  const anyDay = r?.by_day.some((d) => d.placement_tests > 0);

  return (
    <>
      <PageHeader title={t("reports.title")} subtitle={t("reports.subtitle")}
        actions={<div className="flex flex-wrap items-end gap-2">
          <Input type="month" aria-label={t("reports.month")} value={month} max={thisMonth()} onChange={(e) => e.target.value && setMonth(e.target.value)} />
          <Button variant="secondary" loading={busy === "xlsx"} disabled={!r} onClick={() => file("xlsx")}>⬇ Excel</Button>
          <Button variant="secondary" loading={busy === "pdf"} disabled={!r} onClick={() => file("pdf")}>⬇ PDF</Button>
        </div>} />
      {!r ? <PageLoader /> : (
        <div className="space-y-6">
          <h2 className="text-lg font-semibold text-slate-800">{r.title}</h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {HEADLINE.map((k) => (
              <div key={k} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                <p className="text-sm text-slate-500">{t(`reports.labels.${k}`)}</p>
                <p className="mt-1 text-3xl font-bold tabular-nums text-slate-900">{r.totals[k]}</p>
                <Delta cur={r.totals[k]} prev={r.previous[k]} />
              </div>
            ))}
          </div>
          <div className="grid gap-6 lg:grid-cols-3">
            <Card title={t("reports.byDay")} className="lg:col-span-2">
              {anyDay ? <DayBars rows={r.by_day} /> : <EmptyState text={t("reports.empty")} />}
            </Card>
            <Card title={t("reports.conversion")}>
              {conv === null ? <EmptyState text={t("reports.empty")} /> : (
                <>
                  <p className="text-4xl font-bold tabular-nums text-slate-900">{conv}%</p>
                  <p className="mt-1 text-sm text-slate-500">{t("reports.conversionHint", { joined: r.totals.placed_and_joined, placed: r.totals.placed })}</p>
                  <ProgressBar className="mt-4" value={conv} tone="green" />
                </>
              )}
              <p className="mt-6 border-t border-slate-100 pt-4 text-xs text-slate-400">▲▼ — {t("reports.vsPrev")}</p>
              <dl className="mt-2 space-y-2 text-sm">
                {DETAIL.map((k) => (
                  <div key={k} className="flex items-baseline justify-between gap-3">
                    <dt className="text-slate-500">{t(`reports.labels.${k}`)}</dt>
                    <dd className="shrink-0 text-right"><span className="font-semibold tabular-nums text-slate-900">{r.totals[k]}{k === "placement_avg" && r.totals.placement_avg_max ? ` / ${r.totals.placement_avg_max} ${t("exam.points")}` : ""}</span>{" "}
                      <Delta compact cur={r.totals[k]} prev={r.previous[k]} bad={k === "upgrade_rejected"} /></dd>
                  </div>
                ))}
              </dl>
            </Card>
          </div>
          <Card title={t("reports.byLevel")}>
            {r.by_level.length === 0 ? <EmptyState text={t("reports.empty")} /> : (
              <Table head={[t("reports.cols.level"), t("reports.cols.placement_tests"), t("reports.cols.placed"), t("reports.cols.joined_group"), t("reports.cols.upgraded_to")]}>
                {r.by_level.map((l) => (
                  <tr key={l.level} className="hover:bg-slate-50">
                    <Td className="font-medium">{l.level} <span className="font-normal text-slate-400">{l.name !== l.level ? l.name : ""}</span></Td>
                    <Td className="tabular-nums">{l.placement_tests}</Td><Td className="tabular-nums">{l.placed}</Td>
                    <Td className="tabular-nums">{l.joined_group}</Td><Td className="tabular-nums">{l.upgraded_to}</Td>
                  </tr>
                ))}
              </Table>
            )}
          </Card>
        </div>
      )}
    </>
  );
}
