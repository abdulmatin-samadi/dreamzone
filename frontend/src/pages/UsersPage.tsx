import { useQueryClient } from "@tanstack/react-query";
import { FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, parseError } from "../api/client";
import type { Role, User } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { useNotify } from "../components/Toast";
import { UserSessionsModal } from "../components/Sessions";
import { Badge, Button, Checkbox, ConfirmDialog, FilterBar, Input, Modal, PageHeader, Pagination, SearchInput, Select, Table, Td } from "../components/ui";
import { LANGUAGES } from "../i18n";
import { useList } from "../lib/hooks";

const ROLES: Role[] = ["ADMIN", "TEACHER", "RECEPTIONIST", "STUDENT"];
const empty = { username: "", first_name: "", last_name: "", phone: "", email: "", role: "TEACHER" as Role, language: "uz", password: "", is_active: true };

export default function UsersPage() {
  const { t } = useTranslation();
  const { user: me } = useAuth();
  const notify = useNotify();
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [role, setRole] = useState("");
  const [page, setPage] = useState(1);
  const list = useList<User>("users", { search, role, page });
  const [editing, setEditing] = useState<User | "new" | null>(null);
  const [sessions, setSessions] = useState<User | null>(null);
  const [form, setForm] = useState(empty);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [del, setDel] = useState<User | null>(null);
  const [pw, setPw] = useState<{ username: string; password: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const refresh = () => void qc.invalidateQueries({ queryKey: ["users"] });

  const open = (u: User | "new") => {
    setErrors({});
    setForm(u === "new" ? empty : { username: u.username, first_name: u.first_name, last_name: u.last_name, phone: u.phone, email: u.email, role: u.role, language: u.language, password: "", is_active: u.is_active ?? true });
    setEditing(u);
  };

  const save = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true); setErrors({});
    const body: Record<string, unknown> = { ...form };
    if (!body.password) delete body.password;
    if (editing !== "new") delete body.role;
    try {
      if (editing === "new") await api.post("/users/", body); else await api.patch(`/users/${(editing as User).id}/`, body);
      notify.ok("common.saved"); setEditing(null); refresh();
    } catch (err) {
      const p = parseError(err);
      setErrors(Object.fromEntries(Object.entries(p.fields).map(([k, v]) => [k, String(v)])));
      notify.fail(err);
    } finally { setBusy(false); }
  };

  const remove = async () => {
    setBusy(true);
    try { await api.delete(`/users/${del!.id}/`); notify.ok("common.deleted"); setDel(null); refresh(); } catch (e) { notify.fail(e); setDel(null); } finally { setBusy(false); }
  };
  const resetPw = async (u: User) => {
    try { const { data } = await api.post<{ username: string; password: string }>(`/users/${u.id}/reset-password/`); setPw(data); } catch (e) { notify.fail(e); }
  };

  return (
    <>
      <PageHeader title={t("nav.users")} actions={<Button onClick={() => open("new")}>+ {t("users.add")}</Button>} />
      <FilterBar>
        <SearchInput value={search} onChange={(v) => { setSearch(v); setPage(1); }} />
        <Select value={role} onChange={(e) => { setRole(e.target.value); setPage(1); }} className="w-44"><option value="">{t("users.allRoles")}</option>{ROLES.map((r) => <option key={r} value={r}>{t(`roles.${r}`)}</option>)}</Select>
      </FilterBar>
      <Table head={[t("common.name"), t("login.username"), t("common.phone"), t("users.role"), t("common.status"), ""]} empty={!list.data?.results.length}>
        {list.data?.results.map((u) => (
          <tr key={u.id} className="hover:bg-slate-50">
            <Td className="font-medium">{u.full_name}</Td><Td>{u.username}</Td><Td>{u.phone}</Td>
            <Td><Badge tone="indigo">{t(`roles.${u.role}`)}</Badge></Td>
            <Td><Badge tone={u.is_active ? "green" : "red"}>{u.is_active ? t("common.active") : t("common.inactive")}</Badge></Td>
            <Td className="whitespace-nowrap text-right">
              <Button size="sm" variant="ghost" onClick={() => open(u)}>{t("common.edit")}</Button>
              <Button size="sm" variant="ghost" onClick={() => resetPw(u)}>{t("students.resetPassword")}</Button>
              <Button size="sm" variant="ghost" onClick={() => setSessions(u)}>{t("sessions.devices")}</Button>
              {u.id !== me!.id && <Button size="sm" variant="ghost" onClick={() => setDel(u)}>{t("common.delete")}</Button>}
            </Td>
          </tr>
        ))}
      </Table>
      <Pagination page={page} count={list.data?.count ?? 0} onPage={setPage} />

      <Modal open={!!editing} onClose={() => setEditing(null)} title={editing === "new" ? t("users.add") : t("common.edit")}
        footer={<><Button variant="secondary" onClick={() => setEditing(null)}>{t("common.cancel")}</Button><Button type="submit" form="user-form" loading={busy}>{t("common.save")}</Button></>}>
        <form id="user-form" onSubmit={save} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Input label={t("common.firstName")} required value={form.first_name} error={errors.first_name} onChange={(e) => setForm({ ...form, first_name: e.target.value })} />
            <Input label={t("common.lastName")} required value={form.last_name} error={errors.last_name} onChange={(e) => setForm({ ...form, last_name: e.target.value })} />
            <Input label={t("login.username")} required value={form.username} error={errors.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
            <Input label={t("common.phone")} value={form.phone} error={errors.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
            <Input label="Email" type="email" value={form.email} error={errors.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
            <Select label={t("users.role")} disabled={editing !== "new"} value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as Role })}>{ROLES.map((r) => <option key={r} value={r}>{t(`roles.${r}`)}</option>)}</Select>
            <Select label={t("users.language")} value={form.language} onChange={(e) => setForm({ ...form, language: e.target.value })}>{LANGUAGES.map((l) => <option key={l.code} value={l.code}>{l.label}</option>)}</Select>
            <Input label={t("login.password")} type="password" required={editing === "new"} value={form.password} error={errors.password} hint={editing !== "new" ? t("users.passwordKeep") : t("profile.passwordHint")} autoComplete="new-password" onChange={(e) => setForm({ ...form, password: e.target.value })} />
          </div>
          <Checkbox label={t("common.active")} checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />
        </form>
      </Modal>
      <UserSessionsModal user={sessions} onClose={() => setSessions(null)} />
      <Modal open={!!pw} onClose={() => setPw(null)} title={t("students.credentials")} footer={<Button onClick={() => setPw(null)}>{t("common.close")}</Button>}>
        <dl className="space-y-2 rounded-lg bg-slate-50 p-4 font-mono text-sm"><div>{pw?.username}</div><div className="text-lg font-semibold">{pw?.password}</div></dl>
        <p className="mt-3 text-xs text-amber-700">{t("students.shownOnce")}</p>
      </Modal>
      <ConfirmDialog open={!!del} danger loading={busy} title={t("common.delete")} message={t("users.deleteConfirm", { name: del?.full_name })} onConfirm={remove} onClose={() => setDel(null)} />
    </>
  );
}
