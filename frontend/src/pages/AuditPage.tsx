import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Badge, Input, PageHeader, Pagination, SearchInput, Select, Table, Td, Tone } from "../components/ui";
import { fmtDate, useGet, useList } from "../lib/hooks";

interface Entry {
  id: number; actor: number | null; actor_name: string; actor_role: string; action: string; target_type: string;
  target_id: string; target_label: string; detail: Record<string, unknown>; ip: string | null; created_at: string;
}

const tone = (action: string): Tone =>
  /deleted|terminated|rejected|revoked|removed|deactivated/.test(action) ? "red"
    : /password|overridden|released|level_changed|updated/.test(action) ? "amber"
      : /approved|created|resumed|graded|duplicated/.test(action) ? "green" : "gray";

function Detail({ d }: { d: Record<string, unknown> }) {
  const { t } = useTranslation();
  const show = (v: unknown): string => {
    if (v === null || v === undefined || v === "") return "—";
    if (Array.isArray(v)) {
      if (v.length === 2 && v.every((x) => typeof x !== "object")) return `${show(v[0])} → ${show(v[1])}`;
      return v.map((x) => (typeof x === "object" && x ? Object.values(x).join(": ") : String(x))).join(", ");
    }
    if (typeof v === "object") return Object.entries(v as Record<string, unknown>).map(([k, x]) => `${t(`audit.d.${k}`, { defaultValue: k })}: ${show(x)}`).join("; ");
    if (typeof v === "boolean") return v ? "✓" : "✗";
    return String(v);
  };
  const entries = Object.entries(d).filter(([k]) => k !== "id" && k !== "attempt" && k !== "result");
  if (!entries.length) return <span className="text-slate-400">—</span>;
  return (
    <ul className="space-y-0.5 text-xs text-slate-600">
      {entries.map(([k, v]) => <li key={k}><span className="text-slate-400">{t(`audit.d.${k}`, { defaultValue: k })}:</span> {show(v)}</li>)}
    </ul>
  );
}

/** Admin: who did what and when (results changed, tests stopped, students deleted, sign-outs…). */
export default function AuditPage() {
  const { t } = useTranslation();
  const [search, setSearch] = useState("");
  const [action, setAction] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [page, setPage] = useState(1);
  const list = useList<Entry>("audit-log", { search, action, date_from: from, date_to: to, page });
  const actions = useGet<string[]>("audit-actions");
  const label = (a: string) => t(`audit.actions.${a.replace(/\./g, "_")}`, { defaultValue: a });
  const reset = (fn: (v: string) => void) => (v: string) => { fn(v); setPage(1); };

  return (
    <>
      <PageHeader title={t("audit.title")} subtitle={t("audit.subtitle")} />
      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <SearchInput value={search} onChange={reset(setSearch)} placeholder={t("audit.searchPh")} />
        <Select aria-label={t("audit.what")} value={action} onChange={(e) => reset(setAction)(e.target.value)}>
          <option value="">{t("audit.allActions")}</option>
          {actions.data?.map((a) => <option key={a} value={a}>{label(a)}</option>)}
        </Select>
        <Input type="date" aria-label={t("audit.from")} title={t("audit.from")} value={from} onChange={(e) => reset(setFrom)(e.target.value)} />
        <Input type="date" aria-label={t("audit.to")} title={t("audit.to")} value={to} onChange={(e) => reset(setTo)(e.target.value)} />
      </div>
      <Table head={[t("audit.when"), t("audit.who"), t("audit.what"), t("audit.target"), t("audit.details")]} empty={!list.data?.results.length}>
        {list.data?.results.map((e) => (
          <tr key={e.id} className="align-top hover:bg-slate-50">
            <Td className="whitespace-nowrap text-xs text-slate-500">{fmtDate(e.created_at)}{e.ip && <div className="text-slate-400">{e.ip}</div>}</Td>
            <Td className="whitespace-nowrap">
              {e.actor_name ? <><span className="font-medium text-slate-800">{e.actor_name}</span>{e.actor_role && <div className="text-xs text-slate-400">{t(`roles.${e.actor_role}`, { defaultValue: e.actor_role })}</div>}</>
                : <span className="italic text-slate-400">{t("audit.system")}</span>}
            </Td>
            <Td><Badge tone={tone(e.action)}>{label(e.action)}</Badge></Td>
            <Td className="font-medium text-slate-800">{e.target_label || "—"}</Td>
            <Td className="min-w-[14rem]"><Detail d={e.detail} /></Td>
          </tr>
        ))}
      </Table>
      <Pagination page={page} count={list.data?.count ?? 0} onPage={setPage} />
    </>
  );
}
