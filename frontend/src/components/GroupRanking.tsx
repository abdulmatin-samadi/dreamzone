import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import type { Group } from "../api/types";
import { num } from "../lib/hooks";
import { LevelBadge } from "./badges";
import { Badge, Button, EmptyState, Modal, PageLoader, ProgressBar, cx } from "./ui";

interface Row {
  student_id: number; name: string; level: string | null; exams: number; latest: number | null;
  latest_points: Pts | null; best_points: Pts | null; average_points: Pts | null; growth: number | null; growth_points: number | null; levels_up: number; latest_exam: string | null; rank: number | null; top_grower: boolean;
}

const medal = ["🥇", "🥈", "🥉"];
interface Pts { score: number; max: number }
const pts = (p: Pts | null, unit: string) => (p === null ? "—" : `${num(p.score)} / ${num(p.max)} ${unit}`);
const signed = (v: number) => `${v > 0 ? "▲ +" : v < 0 ? "▼ " : ""}${num(v)}`;

/** The group's students ranked by their latest score; the biggest improvers get a badge. */
export function GroupRanking({ group, onClose }: { group: Group | null; onClose: () => void }) {
  const { t } = useTranslation();
  const q = useQuery({
    queryKey: ["groups", group?.id, "ranking"], enabled: !!group,
    queryFn: async () => (await api.get<{ students: Row[] }>(`/groups/${group!.id}/ranking/`)).data,
  });
  const rows = q.data?.students ?? [];
  const growers = rows.filter((r) => r.top_grower).sort((a, b) => b.levels_up - a.levels_up || (b.growth ?? 0) - (a.growth ?? 0));
  return (
    <Modal open={!!group} onClose={onClose} wide title={group ? t("ranking.title", { name: group.name }) : ""} footer={<Button onClick={onClose}>{t("common.close")}</Button>}>
      {!q.data ? <PageLoader /> : rows.length === 0 ? <EmptyState /> : (
        <>
          {growers.length > 0 && (
            <div className="mb-5 rounded-xl border border-emerald-200 bg-emerald-50 p-4">
              <p className="mb-2 text-sm font-semibold text-emerald-900">🚀 {t("ranking.topGrowers")}</p>
              <div className="flex flex-wrap gap-2">
                {growers.map((g) => (
                  <span key={g.student_id} className="rounded-full bg-white px-3 py-1 text-sm text-emerald-900 shadow-sm ring-1 ring-emerald-200">
                    <b>{g.name}</b>
                    {g.levels_up > 0 && <> · {t("ranking.levelsUp", { n: g.levels_up })}</>}
                    {(g.growth_points ?? 0) > 0 && <> · +{num(g.growth_points!)} {t("exam.points")}</>}
                  </span>
                ))}
              </div>
            </div>
          )}
          <p className="mb-3 text-xs text-slate-500">{t("ranking.hint")}</p>
          <ol className="divide-y divide-slate-100">
            {rows.map((r) => (
              <li key={r.student_id} className={cx("flex flex-wrap items-center gap-x-4 gap-y-2 py-3", r.top_grower && "bg-emerald-50/50")}>
                <span className="w-8 shrink-0 text-center text-lg font-bold text-slate-500">{r.rank ? medal[r.rank - 1] ?? r.rank : "—"}</span>
                <div className="min-w-0 flex-1">
                  <p className="flex flex-wrap items-center gap-2">
                    <Link to={`/students/${r.student_id}`} className="font-medium text-indigo-700 hover:underline">{r.name}</Link>
                    <LevelBadge code={r.level} />
                    {r.top_grower && <Badge tone="green">🚀 {t("ranking.grower")}</Badge>}
                  </p>
                  <p className="mt-0.5 text-xs text-slate-500">
                    {r.exams ? `${t("ranking.exams", { n: r.exams })} · ${t("ranking.best")}: ${pts(r.best_points, t("exam.points"))} · ${t("ranking.average")}: ${pts(r.average_points, t("exam.points"))}` : t("ranking.noExams")}
                  </p>
                </div>
                <div className="w-full sm:w-44">
                  <div className="mb-1 flex items-baseline justify-between text-xs">
                    <span className="text-slate-500">{t("ranking.latest")}</span>
                    <span className="text-base font-bold tabular-nums text-slate-900">{pts(r.latest_points, t("exam.points"))}</span>
                  </div>
                  <ProgressBar value={r.latest ?? 0} tone={(r.latest ?? 0) >= 60 ? "green" : (r.latest ?? 0) >= 40 ? "amber" : "red"} />
                  {r.growth_points !== null && (
                    <p className={cx("mt-1 text-right text-xs font-medium", r.growth_points > 0 ? "text-emerald-700" : r.growth_points < 0 ? "text-red-700" : "text-slate-500")}>
                      {t("ranking.growth")}: {signed(r.growth_points)} {t("exam.points")}
                    </p>
                  )}
                </div>
              </li>
            ))}
          </ol>
        </>
      )}
    </Modal>
  );
}
