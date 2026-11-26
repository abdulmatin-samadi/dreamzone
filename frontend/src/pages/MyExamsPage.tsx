import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import type { MyAssignment } from "../api/types";
import { KindBadge, LevelBadge, StateBadge } from "../components/badges";
import { Button, Card, EmptyState, PageHeader, PageLoader } from "../components/ui";
import { fmtDate } from "../lib/hooks";

export default function MyExamsPage() {
  const { t } = useTranslation();
  const q = useQuery({ queryKey: ["my-assignments"], queryFn: async () => (await api.get<MyAssignment[]>("/my/assignments/")).data });
  if (q.isLoading) return <PageLoader />;
  const items = q.data ?? [];
  return (
    <>
      <PageHeader title={t("nav.myExams")} subtitle={t("myExams.subtitle")} />
      {items.length === 0 && <Card><EmptyState text={t("myExams.none")} /></Card>}
      <div className="grid gap-4 md:grid-cols-2">
        {items.map((a) => (
          <Card key={a.id}>
            <div className="flex items-start justify-between gap-3">
              <div>
                <h3 className="font-semibold text-slate-900">{a.examination_title}</h3>
                <div className="mt-2 flex flex-wrap items-center gap-2"><KindBadge kind={a.examination_kind} /><LevelBadge code={a.level_code} />{a.target_level_code && <>→ <LevelBadge code={a.target_level_code} /></>}</div>
              </div>
              <StateBadge state={a.state} />
            </div>
            <p className="mt-3 text-sm text-slate-500">{a.duration_minutes} {t("common.minutes")} · {a.question_count} {t("exam.questions").toLowerCase()}</p>
            {a.available_until && <p className="text-xs text-slate-400">{t("exam.availableUntil")}: {fmtDate(a.available_until)}</p>}
            <div className="mt-4">
              {(a.state === "available" || a.state === "in_progress") && (
                <Link to={`/exam/${a.id}`}><Button>{a.state === "in_progress" ? t("exam.continue") : t("exam.viewInstructions")}</Button></Link>
              )}
              {a.state === "completed" && a.result_id && <Link to={`/results/${a.result_id}`}><Button variant="secondary">{t("myExams.viewResult")}</Button></Link>}
            </div>
          </Card>
        ))}
      </div>
    </>
  );
}
