import { useQueryClient } from "@tanstack/react-query";
import { FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import type { Group, Level, Student } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { LevelBadge } from "../components/badges";
import { useNotify } from "../components/Toast";
import { Badge, Button, Checkbox, ConfirmDialog, FilterBar, Input, Modal, PageHeader, Pagination, SearchInput, Select, Table, Td, Textarea } from "../components/ui";
import { useAll, useGet, useList } from "../lib/hooks";

interface Creds { username: string; password: string }

function CredentialsModal({ creds, name, onClose }: { creds: Creds | null; name: string; onClose: () => void }) {
  const { t } = useTranslation();
  return (
    <Modal open={!!creds} onClose={onClose} title={t("students.credentials")} footer={<><Button variant="secondary" onClick={() => window.print()}>{t("common.print")}</Button><Button onClick={onClose}>{t("common.close")}</Button></>}>
      <p className="mb-3 text-sm text-slate-600">{t("students.credentialsHint", { name })}</p>
      <dl className="space-y-2 rounded-lg bg-slate-50 p-4 font-mono text-sm">
        <div><dt className="text-xs text-slate-500">{t("login.username")}</dt><dd className="text-lg font-semibold">{creds?.username}</dd></div>
        <div><dt className="text-xs text-slate-500">{t("login.password")}</dt><dd className="text-lg font-semibold">{creds?.password}</dd></div>
      </dl>
      <p className="mt-3 text-xs text-amber-700">{t("students.shownOnce")}</p>
    </Modal>
  );
}

export default function StudentsPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const notify = useNotify();
  const qc = useQueryClient();
  const role = user!.role;
  const canManage = role === "ADMIN" || role === "RECEPTIONIST";
  const canRegister = role === "ADMIN" || role === "TEACHER";  // the front desk does not add students: they register themselves
  const [search, setSearch] = useState("");
  const [level, setLevel] = useState("");
  const [ungrouped, setUngrouped] = useState(false);
  const [grouping, setGrouping] = useState<Student | null>(null);
  const [groupId, setGroupId] = useState("");
  const [page, setPage] = useState(1);
  const list = useList<Student>("students", { search, current_level: level, ungrouped: ungrouped ? 1 : "", page });
  const levels = useGet<Level[]>("levels");
  const groups = useAll<Group>("groups", {}, canRegister);

  const [editing, setEditing] = useState<Student | "new" | null>(null);
  const [form, setForm] = useState({ first_name: "", last_name: "", phone: "", initial_level: "", group: "", notes: "" });
  const [creds, setCreds] = useState<{ c: Creds; name: string } | null>(null);
  const [del, setDel] = useState<Student | null>(null);
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const open = (s: Student | "new") => {
    setErrors({});
    setForm(s === "new" ? { first_name: "", last_name: "", phone: "", initial_level: "", group: "", notes: "" }
      : { first_name: s.first_name, last_name: s.last_name, phone: s.phone, initial_level: String(s.initial_level ?? ""), group: "", notes: s.notes });
    setEditing(s);
  };
  const refresh = () => void qc.invalidateQueries({ queryKey: ["students"] });

  const save = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true); setErrors({});
    try {
      if (editing === "new") {
        const { data } = await api.post<Student & { credentials: Creds }>("/students/", { ...form, initial_level: Number(form.initial_level), group: form.group ? Number(form.group) : null });
        setCreds({ c: data.credentials, name: data.full_name });
        notify.ok("students.registered");
      } else if (editing) {
        await api.patch(`/students/${editing.id}/`, { first_name: form.first_name, last_name: form.last_name, phone: form.phone, notes: form.notes, initial_level: form.initial_level ? Number(form.initial_level) : null });
        notify.ok("common.saved");
      }
      setEditing(null); refresh();
    } catch (err: unknown) {
      const fields = (err as { response?: { data?: { errors?: Record<string, string[]> } } }).response?.data?.errors;
      if (fields) setErrors(Object.fromEntries(Object.entries(fields).map(([k, v]) => [k, String(v)])));
      notify.fail(err);
    } finally { setBusy(false); }
  };

  const [pwFor, setPwFor] = useState<Student | null>(null);   // ask first: a new password replaces the old one
  const resetPw = async () => {
    const s = pwFor!;
    setBusy(true);
    try { const { data } = await api.post<Creds>(`/students/${s.id}/reset-password/`); setCreds({ c: data, name: s.full_name }); setPwFor(null); } catch (e) { notify.fail(e); } finally { setBusy(false); }
  };
  const remove = async () => {
    setBusy(true);
    try { await api.delete(`/students/${del!.id}/`); notify.ok("common.deleted"); setDel(null); refresh(); } catch (e) { notify.fail(e); } finally { setBusy(false); }
  };

  return (
    <>
      <PageHeader title={role === "TEACHER" ? t("nav.myStudents") : t("nav.students")}
        actions={canRegister ? <Button onClick={() => open("new")}>+ {t("students.register")}</Button> : undefined} />
      <FilterBar>
        <SearchInput value={search} onChange={(v) => { setSearch(v); setPage(1); }} placeholder={t("students.searchPlaceholder")} />
        <Select value={level} onChange={(e) => { setLevel(e.target.value); setPage(1); }} className="w-36"><option value="">{t("common.allLevels")}</option>{levels.data?.map((l) => <option key={l.id} value={l.id}>{l.code}</option>)}</Select>
        {canManage && <Checkbox label={t("students.ungrouped")} checked={ungrouped} onChange={(e) => { setUngrouped(e.target.checked); setPage(1); }} />}
      </FilterBar>
      <Table head={[t("common.name"), t("common.phone"), t("login.username"), t("students.currentLevel"), t("students.initialLevel"), t("nav.groups"), ""]} empty={!list.data?.results.length}>
        {list.data?.results.map((s) => (
          <tr key={s.id} className="hover:bg-slate-50">
            <Td><Link to={`/students/${s.id}`} className="font-medium text-indigo-700 hover:underline">{s.full_name}</Link>{!s.is_active && <> <Badge tone="red">{t("common.inactive")}</Badge></>}</Td>
            <Td>{s.phone}</Td><Td><code className="rounded bg-slate-100 px-1.5 py-0.5 text-xs">{s.username}</code></Td><Td><LevelBadge code={s.current_level_code} /></Td><Td><LevelBadge code={s.initial_level_code} /></Td>
            <Td>{s.groups.map((g) => g.name).join(", ") || "—"}</Td>
            <Td className="whitespace-nowrap text-right">
              {role === "TEACHER" && <Button size="sm" variant="secondary" onClick={() => setPwFor(s)}>{t("students.loginAndPassword")}</Button>}
              {canManage && <>
                {role === "ADMIN" && s.current_level && <Button size="sm" variant="secondary" onClick={() => { setGrouping(s); setGroupId(""); }}>{t("students.addToGroup")}</Button>}
                <Button size="sm" variant="ghost" onClick={() => open(s)}>{t("common.edit")}</Button>
                <Button size="sm" variant="ghost" onClick={() => setPwFor(s)}>{t("students.resetPassword")}</Button>
                {role === "ADMIN" && <Button size="sm" variant="ghost" onClick={() => setDel(s)}>{t("common.delete")}</Button>}</>}
            </Td>
          </tr>
        ))}
      </Table>
      <Pagination page={page} count={list.data?.count ?? 0} onPage={setPage} />

      <Modal open={!!editing} onClose={() => setEditing(null)} title={editing === "new" ? t("students.register") : t("common.edit")}
        footer={<><Button variant="secondary" onClick={() => setEditing(null)}>{t("common.cancel")}</Button><Button type="submit" form="student-form" loading={busy}>{t("common.save")}</Button></>}>
        <form id="student-form" onSubmit={save} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Input label={t("common.firstName")} required value={form.first_name} error={errors.first_name} onChange={(e) => setForm({ ...form, first_name: e.target.value })} />
            <Input label={t("common.lastName")} required value={form.last_name} error={errors.last_name} onChange={(e) => setForm({ ...form, last_name: e.target.value })} />
          </div>
          <Input label={t("common.phone")} required value={form.phone} error={errors.phone} placeholder="+998 90 123 45 67" onChange={(e) => setForm({ ...form, phone: e.target.value })} />
          <Select label={t("students.initialLevel")} required={editing === "new"} value={form.initial_level} error={errors.initial_level} onChange={(e) => setForm({ ...form, initial_level: e.target.value })}>
            <option value="">—</option>{levels.data?.filter((l) => l.is_active).map((l) => <option key={l.id} value={l.id}>{l.code} — {l.name}</option>)}
          </Select>
          {editing === "new" && (
            <Select label={role === "TEACHER" ? t("nav.groups") : `${t("nav.groups")} (${t("common.optional")})`} required={role === "TEACHER"} value={form.group} error={errors.group} onChange={(e) => setForm({ ...form, group: e.target.value })}>
              <option value="">—</option>{groups.items.map((g) => <option key={g.id} value={g.id}>{g.name} ({g.level_code})</option>)}
            </Select>
          )}
          <Textarea label={t("common.notes")} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
        </form>
      </Modal>
      <Modal open={!!grouping} onClose={() => setGrouping(null)} title={t("students.addToGroup")}
        footer={<><Button variant="secondary" onClick={() => setGrouping(null)}>{t("common.cancel")}</Button>
          <Button disabled={!groupId} loading={busy} onClick={async () => {
            setBusy(true);
            try { await api.post(`/groups/${groupId}/members/`, { student_id: grouping!.id }); notify.ok("students.addedToGroup"); setGrouping(null); refresh(); void qc.invalidateQueries({ queryKey: ["groups"] }); }
            catch (e) { notify.fail(e); } finally { setBusy(false); }
          }}>{t("common.add")}</Button></>}>
        <p className="mb-3 text-sm text-slate-600">{grouping?.full_name} — {t("students.currentLevel")}: <b>{grouping?.current_level_code}</b></p>
        <Select label={t("nav.groups")} value={groupId} onChange={(e) => setGroupId(e.target.value)}>
          <option value="">—</option>
          {[...groups.items].sort((a, b) => Number(b.level === grouping?.current_level) - Number(a.level === grouping?.current_level)).map((g) => (
            <option key={g.id} value={g.id}>{g.level === grouping?.current_level ? "★ " : ""}{g.name} ({g.level_code}{g.teacher_name ? `, ${g.teacher_name}` : ""})</option>))}
        </Select>
        <p className="mt-2 text-xs text-slate-500">{t("students.groupHint")}</p>
      </Modal>
      <ConfirmDialog open={!!pwFor} loading={busy} title={t("students.loginAndPassword")} message={t("students.newPasswordConfirm", { name: pwFor?.full_name })} confirmLabel={t("students.createPassword")} onConfirm={resetPw} onClose={() => setPwFor(null)} />
      <CredentialsModal creds={creds?.c ?? null} name={creds?.name ?? ""} onClose={() => setCreds(null)} />
      <ConfirmDialog open={!!del} danger loading={busy} title={t("common.delete")} message={t("students.deleteConfirm", { name: del?.full_name })} onConfirm={remove} onClose={() => setDel(null)} />
    </>
  );
}
