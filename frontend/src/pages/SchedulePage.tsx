import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import type { Assignment } from "../api/types";
import { LevelBadge, StateBadge } from "../components/badges";
import { useNotify } from "../components/Toast";
import { Button, FilterBar, PageHeader, Pagination, SearchInput, Select, Table, Td } from "../components/ui";
import { fmtDate, useList } from "../lib/hooks";

export default function SchedulePage() {
  const { t } = useTranslation();
  const notify = useNotify();
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [kind, setKind] = useState("");
  const [page, setPage] = useState(1);
  const list = useList<Assignment>("assignments", { search, examination__kind: kind, ordering: "-created_at", page });

  const remove = async (a: Assignment) => {
    try { await api.delete(`/assignments/${a.id}/`); notify.ok("common.deleted"); void qc.invalidateQueries({ queryKey: ["assignments"] }); } catch (e) { notify.fail(e); }
  };

  return (
    <>
      <PageHeader title={t("nav.schedule")} subtitle={t("schedule.subtitle")} />
      <FilterBar>
        <SearchInput value={search} onChange={(v) => { setSearch(v); setPage(1); }} />
        <Select value={kind} onChange={(e) => { setKind(e.target.value); setPage(1); }} className="w-44"><option value="">{t("results.allTypes")}</option><option value="UPGRADE">{t("kinds.UPGRADE")}</option><option value="PLACEMENT">{t("kinds.PLACEMENT")}</option></Select>
      </FilterBar>
      <Table head={[t("common.student"), t("results.exam"), t("common.level"), t("exams.variant"), t("exams.window"), t("result.status"), ""]} empty={!list.data?.results.length}>
        {list.data?.results.map((a) => (
          <tr key={a.id} className="hover:bg-slate-50">
            <Td className="font-medium">{a.student_name}</Td>
            <Td><Link className="text-indigo-700 hover:underline" to={`/exams/${a.examination}`}>{a.examination_title}</Link></Td>
            <Td><LevelBadge code={a.level_code} />{a.target_level_code && <> → <LevelBadge code={a.target_level_code} /></>}</Td>
            <Td>{a.variant_name}</Td>
            <Td className="whitespace-nowrap text-xs">{a.available_from || a.available_until ? `${fmtDate(a.available_from)} → ${fmtDate(a.available_until)}` : t("schedule.anytime")}</Td>
            <Td><StateBadge state={a.state} /></Td>
            <Td className="text-right">{a.result_id ? <Link to={`/results/${a.result_id}`}><Button size="sm" variant="secondary">{t("myExams.viewResult")}</Button></Link> : !a.attempt_id && <Button size="sm" variant="ghost" onClick={() => remove(a)}>{t("common.remove")}</Button>}</Td>
          </tr>
        ))}
      </Table>
      <Pagination page={page} count={list.data?.count ?? 0} onPage={setPage} />
    </>
  );
}
