import { useQueryClient } from "@tanstack/react-query";
import { FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";

import { api, parseError } from "../api/client";
import type { Exam, Level } from "../api/types";
import { useNotify } from "../components/Toast";
import { Badge, Button, Checkbox, ConfirmDialog, Input, Modal, PageHeader, PageLoader, Table, Td, Textarea } from "../components/ui";
import { useAll, useGet } from "../lib/hooks";

export default function LevelsPage() {
  const { t } = useTranslation();
  const notify = useNotify();
  const nav = useNavigate();
  const qc = useQueryClient();
  const levels = useGet<Level[]>("levels");
  const placement = useAll<Exam>("examinations", { kind: "PLACEMENT" });
  const [editing, setEditing] = useState<Level | "new" | null>(null);
  const [form, setForm] = useState({ code: "", name: "", description: "", order: 1, is_active: true });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [del, setDel] = useState<Level | null>(null);
  const [busy, setBusy] = useState(false);
  const refresh = () => { void qc.invalidateQueries({ queryKey: ["levels"] }); void qc.invalidateQueries({ queryKey: ["examinations"] }); };

  if (!levels.data) return <PageLoader />;

  const open = (l: Level | "new") => {
    setErrors({});
    setForm(l === "new" ? { code: "", name: "", description: "", order: (levels.data!.at(-1)?.order ?? 0) + 1, is_active: true } : { code: l.code, name: l.name, description: l.description, order: l.order, is_active: l.is_active });
    setEditing(l);
  };
  const save = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true); setErrors({});
    try {
      if (editing === "new") await api.post("/levels/", form); else await api.patch(`/levels/${(editing as Level).id}/`, form);
      notify.ok("common.saved"); setEditing(null); refresh();
    } catch (err) { setErrors(Object.fromEntries(Object.entries(parseError(err).fields).map(([k, v]) => [k, String(v)]))); notify.fail(err); } finally { setBusy(false); }
  };
  const remove = async () => {
    setBusy(true);
    try { await api.delete(`/levels/${del!.id}/`); notify.ok("common.deleted"); refresh(); } catch (e) { notify.fail(e); } finally { setBusy(false); setDel(null); }
  };
  const createPlacement = async (l: Level) => {
    try {
      const { data } = await api.post<Exam>("/examinations/", { kind: "PLACEMENT", title: `${l.code} Placement Test`, level: l.id, duration_minutes: 40, passing_score: 50, high_threshold: 85 });
      nav(`/exams/${data.id}`);
    } catch (e) { notify.fail(e); }
  };

  return (
    <>
      <PageHeader title={t("nav.levels")} subtitle={t("levels.subtitle")} actions={<Button onClick={() => open("new")}>+ {t("levels.add")}</Button>} />
      <Table head={["#", t("levels.code"), t("common.name"), t("nav.students"), t("levels.placement"), t("common.status"), ""]}>
        {levels.data.map((l) => {
          const ex = placement.items.find((e) => e.level === l.id);
          return (
            <tr key={l.id}>
              <Td>{l.order}</Td><Td><Badge tone="indigo">{l.code}</Badge></Td><Td className="font-medium">{l.name}</Td><Td>{l.student_count}</Td>
              <Td>{ex ? <Link to={`/exams/${ex.id}`} className="text-indigo-700 hover:underline">{ex.status === "PUBLISHED" ? t("levels.configure") : `${t("levels.configure")} (${t("examStatus.DRAFT")})`}</Link>
                : <Button size="sm" variant="secondary" onClick={() => createPlacement(l)}>{t("levels.createPlacement")}</Button>}</Td>
              <Td><Badge tone={l.is_active ? "green" : "gray"}>{l.is_active ? t("common.active") : t("common.inactive")}</Badge></Td>
              <Td className="whitespace-nowrap text-right"><Button size="sm" variant="ghost" onClick={() => open(l)}>{t("common.edit")}</Button><Button size="sm" variant="ghost" onClick={() => setDel(l)}>{t("common.delete")}</Button></Td>
            </tr>
          );
        })}
      </Table>
      <Modal open={!!editing} onClose={() => setEditing(null)} title={editing === "new" ? t("levels.add") : t("common.edit")}
        footer={<><Button variant="secondary" onClick={() => setEditing(null)}>{t("common.cancel")}</Button><Button type="submit" form="level-form" loading={busy}>{t("common.save")}</Button></>}>
        <form id="level-form" onSubmit={save} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-3">
            <Input label={t("levels.code")} required value={form.code} error={errors.code} onChange={(e) => setForm({ ...form, code: e.target.value })} />
            <Input label={t("common.name")} required className="sm:col-span-2" value={form.name} error={errors.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </div>
          <Input label={t("levels.order")} type="number" min={1} required value={form.order} error={errors.order} onChange={(e) => setForm({ ...form, order: Number(e.target.value) })} />
          <Textarea label={t("common.description")} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          <Checkbox label={t("common.active")} checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />
        </form>
      </Modal>
      <ConfirmDialog open={!!del} danger loading={busy} title={t("common.delete")} message={t("levels.deleteConfirm", { name: del?.code })} onConfirm={remove} onClose={() => setDel(null)} />
    </>
  );
}
