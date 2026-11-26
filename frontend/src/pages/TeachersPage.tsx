import { useQueryClient } from "@tanstack/react-query";
import { FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api, parseError } from "../api/client";
import { LevelBadge } from "../components/badges";
import { useNotify } from "../components/Toast";
import { Badge, Button, Card, EmptyState, FilterBar, Input, Modal, PageHeader, Pagination, SearchInput, Select, StatCard, Table, Td } from "../components/ui";
import { useList } from "../lib/hooks";

interface Teacher {
  id: number; teacher_id: number; username: string; first_name: string; last_name: string; full_name: string; phone: string;
  email: string; is_active: boolean; groups_count: number; students_count: number; exams_count: number;
  groups: { id: number; name: string; level: string; students: number }[];
  exams: { id: number; title: string; status: string; level: string; target: string | null }[];
}

const empty = { first_name: "", last_name: "", phone: "", email: "", username: "", password: "" };

export default function TeachersPage() {
  const { t } = useTranslation();
  const notify = useNotify();
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [active, setActive] = useState("");
  const [page, setPage] = useState(1);
  const list = useList<Teacher>("teachers", { search, is_active: active, page });
  const [editing, setEditing] = useState<Teacher | "new" | null>(null);
  const [form, setForm] = useState(empty);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [view, setView] = useState<Teacher | null>(null);
  const [pw, setPw] = useState<{ username: string; password: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const refresh = () => { void qc.invalidateQueries({ queryKey: ["teachers"] }); void qc.invalidateQueries({ queryKey: ["users"] }); };

  const open = (x: Teacher | "new") => {
    setErrors({});
    setForm(x === "new" ? empty : { first_name: x.first_name, last_name: x.last_name, phone: x.phone, email: x.email, username: x.username, password: "" });
    setEditing(x);
  };

  const save = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true); setErrors({});
    const body: Record<string, unknown> = { ...form };
    if (!body.password) delete body.password;
    try {
      if (editing === "new") await api.post("/users/", { ...body, role: "TEACHER", language: "uz" });
      else await api.patch(`/users/${(editing as Teacher).id}/`, body);
      notify.ok("common.saved"); setEditing(null); refresh();
    } catch (err) {
      setErrors(Object.fromEntries(Object.entries(parseError(err).fields).map(([k, v]) => [k, String(v)]))); notify.fail(err);
    } finally { setBusy(false); }
  };

  const toggleActive = async (x: Teacher) => {
    try { await api.patch(`/users/${x.id}/`, { is_active: !x.is_active }); notify.ok("common.saved"); refresh(); } catch (e) { notify.fail(e); }
  };
  const resetPw = async (x: Teacher) => {
    try { const { data } = await api.post<{ username: string; password: string }>(`/users/${x.id}/reset-password/`); setPw(data); } catch (e) { notify.fail(e); }
  };

  const rows = list.data?.results ?? [];
  return (
    <>
      <PageHeader title={t("nav.teachers")} subtitle={t("teachers.subtitle")} actions={<Button onClick={() => open("new")}>+ {t("teachers.add")}</Button>} />
      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label={t("nav.teachers")} value={list.data?.count ?? 0} />
        <StatCard label={t("nav.groups")} value={rows.reduce((a, x) => a + x.groups_count, 0)} />
        <StatCard label={t("nav.students")} value={rows.reduce((a, x) => a + x.students_count, 0)} />
        <StatCard label={t("nav.exams")} value={rows.reduce((a, x) => a + x.exams_count, 0)} />
      </div>
      <FilterBar>
        <SearchInput value={search} onChange={(v) => { setSearch(v); setPage(1); }} />
        <Select value={active} onChange={(e) => { setActive(e.target.value); setPage(1); }} className="w-44"><option value="">{t("common.allStatuses")}</option><option value="true">{t("common.active")}</option><option value="false">{t("common.inactive")}</option></Select>
      </FilterBar>
      <Table head={[t("common.name"), t("common.phone"), t("login.username"), t("nav.groups"), t("nav.students"), t("nav.exams"), t("common.status"), ""]} empty={!rows.length}>
        {rows.map((x) => (
          <tr key={x.id} className="hover:bg-slate-50">
            <Td><button className="font-medium text-indigo-700 hover:underline" onClick={() => setView(x)}>{x.full_name}</button></Td>
            <Td>{x.phone || "—"}</Td><Td>{x.username}</Td><Td>{x.groups_count}</Td><Td>{x.students_count}</Td><Td>{x.exams_count}</Td>
            <Td><Badge tone={x.is_active ? "green" : "red"}>{x.is_active ? t("common.active") : t("common.inactive")}</Badge></Td>
            <Td className="whitespace-nowrap text-right">
              <Button size="sm" variant="ghost" onClick={() => open(x)}>{t("common.edit")}</Button>
              <Button size="sm" variant="ghost" onClick={() => resetPw(x)}>{t("students.resetPassword")}</Button>
              <Button size="sm" variant="ghost" onClick={() => toggleActive(x)}>{x.is_active ? t("teachers.deactivate") : t("teachers.activate")}</Button>
            </Td>
          </tr>
        ))}
      </Table>
      <Pagination page={page} count={list.data?.count ?? 0} onPage={setPage} />

      <Modal open={!!view} onClose={() => setView(null)} wide title={view?.full_name ?? ""} footer={<Button onClick={() => setView(null)}>{t("common.close")}</Button>}>
        {view && (
          <div className="grid gap-5 md:grid-cols-2">
            <Card title={`${t("nav.groups")} (${view.groups_count})`}>
              {view.groups.length === 0 ? <EmptyState /> : <ul className="divide-y divide-slate-100 text-sm">{view.groups.map((g) => <li key={g.id} className="flex items-center justify-between py-2"><span>{g.name} <LevelBadge code={g.level} /></span><span className="text-slate-500">{g.students} {t("nav.students").toLowerCase()}</span></li>)}</ul>}
              <Link to="/groups" className="mt-3 block text-sm text-indigo-600 hover:underline">{t("nav.groups")} →</Link>
            </Card>
            <Card title={`${t("nav.exams")} (${view.exams_count})`}>
              {view.exams.length === 0 ? <EmptyState /> : <ul className="divide-y divide-slate-100 text-sm">{view.exams.map((e) => <li key={e.id} className="flex items-center justify-between py-2"><Link className="text-indigo-700 hover:underline" to={`/exams/${e.id}`}>{e.title}</Link><span><LevelBadge code={e.level} />{e.target && <> → <LevelBadge code={e.target} /></>} <Badge tone={e.status === "PUBLISHED" ? "green" : "gray"}>{t(`examStatus.${e.status}`)}</Badge></span></li>)}</ul>}
            </Card>
          </div>
        )}
      </Modal>

      <Modal open={!!editing} onClose={() => setEditing(null)} title={editing === "new" ? t("teachers.add") : t("common.edit")}
        footer={<><Button variant="secondary" onClick={() => setEditing(null)}>{t("common.cancel")}</Button><Button type="submit" form="teacher-form" loading={busy}>{t("common.save")}</Button></>}>
        <form id="teacher-form" onSubmit={save} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Input label={t("common.firstName")} required value={form.first_name} error={errors.first_name} onChange={(e) => setForm({ ...form, first_name: e.target.value })} />
            <Input label={t("common.lastName")} required value={form.last_name} error={errors.last_name} onChange={(e) => setForm({ ...form, last_name: e.target.value })} />
            <Input label={t("common.phone")} value={form.phone} error={errors.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
            <Input label="Email" type="email" value={form.email} error={errors.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
            <Input label={t("login.username")} required value={form.username} error={errors.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
            <Input label={t("login.password")} type="password" required={editing === "new"} autoComplete="new-password" value={form.password} error={errors.password}
              hint={editing !== "new" ? t("users.passwordKeep") : t("profile.passwordHint")} onChange={(e) => setForm({ ...form, password: e.target.value })} />
          </div>
        </form>
      </Modal>
      <Modal open={!!pw} onClose={() => setPw(null)} title={t("students.credentials")} footer={<Button onClick={() => setPw(null)}>{t("common.close")}</Button>}>
        <dl className="space-y-2 rounded-lg bg-slate-50 p-4 font-mono text-sm"><div>{pw?.username}</div><div className="text-lg font-semibold">{pw?.password}</div></dl>
        <p className="mt-3 text-xs text-amber-700">{t("students.shownOnce")}</p>
      </Modal>
    </>
  );
}
