import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api, parseError } from "../api/client";
import type { Group, Level, Student, User } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { LevelBadge } from "../components/badges";
import { GroupRanking } from "../components/GroupRanking";
import { useNotify } from "../components/Toast";
import { Badge, Button, Checkbox, ConfirmDialog, EmptyState, Input, Modal, PageHeader, Pagination, SearchInput, Select, Table, Td } from "../components/ui";
import { useAll, useGet, useList } from "../lib/hooks";

function MembersModal({ group, admin, onClose }: { group: Group | null; admin: boolean; onClose: () => void }) {  // admin = may add / remove (admin or the group's teacher)
  const { t } = useTranslation();
  const { user } = useAuth();
  const notify = useNotify();
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const members = useQuery({ queryKey: ["groups", group?.id, "members"], enabled: !!group, queryFn: async () => (await api.get<Student[]>(`/groups/${group!.id}/members/`)).data });
  const found = useList<Student>("students", { search, page_size: 6, available: user!.role === "TEACHER" ? 1 : "" }, admin && search.length >= 2);
  const refresh = () => { void qc.invalidateQueries({ queryKey: ["groups"] }); void qc.invalidateQueries({ queryKey: ["students"] }); };
  const act = async (method: "post" | "delete", s: Student) => {
    try { await api.request({ method, url: `/groups/${group!.id}/members/`, data: { student_id: s.id } }); refresh(); } catch (e) { notify.fail(e); }
  };
  return (
    <Modal open={!!group} onClose={onClose} title={group ? `${group.name} — ${t("groups.members")}` : ""} wide footer={<Button onClick={onClose}>{t("common.close")}</Button>}>
      {admin && (
        <div className="mb-4">
          <SearchInput value={search} onChange={setSearch} placeholder={t("groups.addStudent")} />
          {user!.role === "TEACHER" && <p className="mt-1 text-xs text-slate-500">{t("groups.teacherHint")}</p>}
          {search.length >= 2 && (
            <ul className="mt-2 divide-y divide-slate-100 rounded-lg border border-slate-200 text-sm">
              {found.data?.results.length === 0 && <li className="px-3 py-2 text-slate-500">{t("common.noData")}</li>}
              {found.data?.results.map((s) => <li key={s.id} className="flex items-center justify-between px-3 py-2"><span>{s.full_name} <span className="text-slate-400">{s.phone}</span></span><Button size="sm" onClick={() => act("post", s)}>{t("common.add")}</Button></li>)}
            </ul>
          )}
        </div>
      )}
      {members.data?.length ? (
        <ul className="divide-y divide-slate-100 text-sm">
          {members.data.map((s) => (
            <li key={s.id} className="flex items-center justify-between py-2">
              <span><Link className="font-medium text-indigo-700 hover:underline" to={`/students/${s.id}`}>{s.full_name}</Link> <LevelBadge code={s.current_level_code} /></span>
              {admin && <Button size="sm" variant="ghost" onClick={() => act("delete", s)}>{t("common.remove")}</Button>}
            </li>
          ))}
        </ul>
      ) : <EmptyState />}
    </Modal>
  );
}

export default function GroupsPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const admin = user!.role === "ADMIN";
  const teacherRole = user!.role === "TEACHER";
  const showCode = admin || teacherRole;  // the join code is handed out by the teacher / admin only, not by the front desk
  const notify = useNotify();
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [levelFilter, setLevelFilter] = useState("");
  const list = useList<Group>("groups", { search, page, level: levelFilter });
  const levels = useGet<Level[]>("levels");
  const teachers = useAll<User>("users", { role: "TEACHER" }, admin);
  const [editing, setEditing] = useState<Group | "new" | null>(null);
  const [form, setForm] = useState({ name: "", level: "", teacher: "", schedule: "", is_active: true });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [members, setMembers] = useState<Group | null>(null);
  const [ranking, setRanking] = useState<Group | null>(null);
  const [del, setDel] = useState<Group | null>(null);
  const [regen, setRegen] = useState<Group | null>(null);
  const canRegen = (_g: Group) => admin || teacherRole;  // a teacher only lists their own groups; the server checks it too
  const copy = async (code: string) => {
    try { await navigator.clipboard.writeText(code); notify.ok("groups.codeCopied"); } catch { /* clipboard blocked: the code is on screen */ }
  };
  const regenerate = async () => {
    setBusy(true);
    try { await api.post(`/groups/${regen!.id}/regenerate-code/`); notify.ok("groups.codeRenewed"); refresh(); } catch (e) { notify.fail(e); } finally { setBusy(false); setRegen(null); }
  };
  const [busy, setBusy] = useState(false);
  const refresh = () => void qc.invalidateQueries({ queryKey: ["groups"] });

  const open = (g: Group | "new") => {
    setErrors({});
    setForm(g === "new" ? { name: "", level: "", teacher: "", schedule: "", is_active: true } : { name: g.name, level: String(g.level), teacher: String(g.teacher ?? ""), schedule: g.schedule, is_active: g.is_active });
    setEditing(g);
  };
  const save = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true); setErrors({});
    const body = { name: form.name, level: Number(form.level), teacher: form.teacher ? Number(form.teacher) : null, schedule: form.schedule.trim(), is_active: form.is_active };
    try {
      if (editing === "new") await api.post("/groups/", body); else await api.patch(`/groups/${(editing as Group).id}/`, body);
      notify.ok("common.saved"); setEditing(null); refresh();
    } catch (err) { setErrors(Object.fromEntries(Object.entries(parseError(err).fields).map(([k, v]) => [k, String(v)]))); notify.fail(err); } finally { setBusy(false); }
  };
  const remove = async () => {
    setBusy(true);
    try { await api.delete(`/groups/${del!.id}/`); notify.ok("common.deleted"); refresh(); } catch (e) { notify.fail(e); } finally { setBusy(false); setDel(null); }
  };

  return (
    <>
      <PageHeader title={teacherRole ? t("nav.myGroups") : t("nav.groups")} actions={admin ? <Button onClick={() => open("new")}>+ {t("groups.add")}</Button> : undefined} />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="min-w-0 flex-1 sm:max-w-md"><SearchInput value={search} onChange={(v) => { setSearch(v); setPage(1); }} placeholder={t("groups.searchHint")} /></div>
        <Select aria-label={t("common.level")} value={levelFilter} onChange={(e) => { setLevelFilter(e.target.value); setPage(1); }}>
          <option value="">{t("common.allLevels")}</option>{levels.data?.map((l) => <option key={l.id} value={l.id}>{l.code}</option>)}
        </Select>
      </div>
      <Table head={[t("common.name"), ...(showCode ? [t("groups.code")] : []), t("common.level"), t("groups.schedule"), t("groups.teacher"), t("nav.students"), t("common.status"), ""]} empty={!list.data?.results.length}>
        {list.data?.results.map((g) => (
          <tr key={g.id} className="hover:bg-slate-50">
            <Td className="font-medium">{g.name}</Td>
            {showCode && <Td className="whitespace-nowrap">
              {g.join_code ? <span className="inline-flex items-center gap-1">
                <code className="rounded-lg bg-indigo-50 px-2 py-1 font-mono text-sm font-bold tracking-widest text-indigo-700">{g.join_code}</code>
                <button type="button" onClick={() => copy(g.join_code!)} title={t("groups.copyCode")} aria-label={t("groups.copyCode")} className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-800">⧉</button>
                {canRegen(g) && <button type="button" onClick={() => setRegen(g)} title={t("groups.newCode")} aria-label={t("groups.newCode")} className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-800">↻</button>}
              </span> : "—"}
            </Td>}<Td><LevelBadge code={g.level_code} /></Td><Td className="whitespace-nowrap">{g.schedule || "—"}</Td><Td>{g.teacher_name ?? "—"}</Td><Td>{g.student_count}</Td>
            <Td><Badge tone={g.is_active ? "green" : "gray"}>{g.is_active ? t("common.active") : t("common.inactive")}</Badge></Td>
            <Td className="whitespace-nowrap text-right">
              <Button size="sm" variant="ghost" onClick={() => setRanking(g)} title={t("ranking.button")} aria-label={t("ranking.button")}>🏆</Button>
              <Button size="sm" variant="ghost" onClick={() => setMembers(g)}>{t("groups.members")}</Button>
              {admin && <><Button size="sm" variant="ghost" onClick={() => open(g)}>{t("common.edit")}</Button><Button size="sm" variant="ghost" onClick={() => setDel(g)}>{t("common.delete")}</Button></>}
            </Td>
          </tr>
        ))}
      </Table>
      <Pagination page={page} count={list.data?.count ?? 0} onPage={setPage} />
      <GroupRanking group={ranking} onClose={() => setRanking(null)} />
      <MembersModal group={members} admin={admin || teacherRole} onClose={() => setMembers(null)} />
      <Modal open={!!editing} onClose={() => setEditing(null)} title={editing === "new" ? t("groups.add") : t("common.edit")}
        footer={<><Button variant="secondary" onClick={() => setEditing(null)}>{t("common.cancel")}</Button><Button type="submit" form="group-form" loading={busy}>{t("common.save")}</Button></>}>
        <form id="group-form" onSubmit={save} className="space-y-4">
          <Input label={t("common.name")} required value={form.name} error={errors.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <Select label={t("common.level")} required value={form.level} error={errors.level} onChange={(e) => setForm({ ...form, level: e.target.value })}><option value="">—</option>{levels.data?.map((l) => <option key={l.id} value={l.id}>{l.code} — {l.name}</option>)}</Select>
          <Select label={t("groups.teacher")} value={form.teacher} onChange={(e) => setForm({ ...form, teacher: e.target.value })}><option value="">—</option>{teachers.items.map((x) => <option key={x.id} value={x.teacher_id ?? ""}>{x.full_name} ({x.username})</option>)}</Select>
          <Input label={t("groups.schedule")} placeholder={t("groups.schedulePh") as string} value={form.schedule} onChange={(e) => setForm({ ...form, schedule: e.target.value })} />
          <Checkbox label={t("common.active")} checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />
        </form>
      </Modal>
      <ConfirmDialog open={!!regen} loading={busy} title={t("groups.newCode")} message={t("groups.newCodeConfirm", { name: regen?.name, code: regen?.join_code })} confirmLabel={t("groups.newCode")} onConfirm={regenerate} onClose={() => setRegen(null)} />
      <ConfirmDialog open={!!del} danger loading={busy} title={t("common.delete")} message={t("groups.deleteConfirm", { name: del?.name })} onConfirm={remove} onClose={() => setDel(null)} />
    </>
  );
}
