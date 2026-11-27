import { useQueryClient } from "@tanstack/react-query";
import { FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";

import { api, parseError } from "../api/client";
import type { Exam, Level } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { KindBadge, LevelBadge } from "../components/badges";
import { useNotify } from "../components/Toast";
import { Badge, Button, ConfirmDialog, FilterBar, Input, Modal, PageHeader, Pagination, SearchInput, Select, Table, Td } from "../components/ui";
import { fmtDate, num, useGet, useList } from "../lib/hooks";

export default function ExamsPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const admin = user!.role === "ADMIN";
  const notify = useNotify();
  const nav = useNavigate();
  const qc = useQueryClient();
  const [f, setF] = useState({ search: "", kind: "", status: "", level: "" });
  const [page, setPage] = useState(1);
  const list = useList<Exam>("examinations", { ...f, page });
  const levels = useGet<Level[]>("levels");
  const [create, setCreate] = useState(false);
  const [form, setForm] = useState({ kind: "UPGRADE", title: "", level: "", target_level: "", duration_minutes: 60, passing_score: "", high_threshold: "", speaking_points: "", writing_points: "" });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [del, setDel] = useState<Exam | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof f, v: string) => { setF({ ...f, [k]: v }); setPage(1); };
  const refresh = () => void qc.invalidateQueries({ queryKey: ["examinations"] });

  const submit = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true); setErrors({});
    try {
      const placement = form.kind === "PLACEMENT";
      const { data } = await api.post<Exam>("/examinations/", {
        kind: form.kind, title: form.title, level: Number(form.level), duration_minutes: form.duration_minutes, passing_score: Number(form.passing_score),
        ...(placement ? { target_level: null, high_threshold: Number(form.high_threshold) } : { target_level: Number(form.target_level), speaking_points: Number(form.speaking_points || 0), writing_points: Number(form.writing_points || 0) }),
      });
      notify.ok("exams.created"); nav(`/exams/${data.id}`);
    } catch (err) { setErrors(Object.fromEntries(Object.entries(parseError(err).fields).map(([k, v]) => [k, String(v)]))); notify.fail(err); } finally { setBusy(false); }
  };
  const toggle = async (x: Exam) => {
    try { await api.post(`/examinations/${x.id}/${x.status === "PUBLISHED" ? "unpublish" : "publish"}/`); notify.ok(x.status === "PUBLISHED" ? "exams.unpublished" : "exams.published"); refresh(); } catch (e) { notify.fail(e); }
  };
  const remove = async () => {
    setBusy(true);
    try { await api.delete(`/examinations/${del!.id}/`); notify.ok("common.deleted"); refresh(); } catch (e) { notify.fail(e); } finally { setBusy(false); setDel(null); }
  };

  return (
    <>
      <PageHeader title={t("nav.exams")} actions={<Button onClick={() => { setErrors({}); setCreate(true); }}>+ {t("exams.create")}</Button>} />
      <FilterBar>
        <SearchInput value={f.search} onChange={(v) => set("search", v)} />
        {admin && <Select value={f.kind} onChange={(e) => set("kind", e.target.value)} className="w-44"><option value="">{t("results.allTypes")}</option><option value="PLACEMENT">{t("kinds.PLACEMENT")}</option><option value="UPGRADE">{t("kinds.UPGRADE")}</option></Select>}
        <Select value={f.level} onChange={(e) => set("level", e.target.value)} className="w-32"><option value="">{t("common.allLevels")}</option>{levels.data?.map((l) => <option key={l.id} value={l.id}>{l.code}</option>)}</Select>
        <Select value={f.status} onChange={(e) => set("status", e.target.value)} className="w-40"><option value="">{t("common.allStatuses")}</option><option value="DRAFT">{t("examStatus.DRAFT")}</option><option value="PUBLISHED">{t("examStatus.PUBLISHED")}</option></Select>
      </FilterBar>
      <Table head={[t("exams.title"), t("common.level"), t("exam.duration"), t("exam.passingScore"), t("exams.variants"), t("common.status"), t("common.date"), ""]} empty={!list.data?.results.length}>
        {list.data?.results.map((x) => (
          <tr key={x.id} className="hover:bg-slate-50">
            <Td><Link to={`/exams/${x.id}`} className="font-medium text-indigo-700 hover:underline">{x.title}</Link><div><KindBadge kind={x.kind} /></div></Td>
            <Td><LevelBadge code={x.level_code} />{x.target_level_code && <> → <LevelBadge code={x.target_level_code} /></>}</Td>
            <Td>{x.duration_minutes} {t("common.minutes")}</Td><Td className="whitespace-nowrap">{num(x.passing_score)} {t("exam.points")}</Td><Td>{x.variant_count}</Td>
            <Td><Badge tone={x.status === "PUBLISHED" ? "green" : "gray"}>{t(`examStatus.${x.status}`)}</Badge></Td>
            <Td className="whitespace-nowrap">{fmtDate(x.created_at, false)}</Td>
            <Td className="whitespace-nowrap text-right">
              {x.can_edit ? <>
                <Button size="sm" variant="ghost" onClick={() => toggle(x)}>{x.status === "PUBLISHED" ? t("exams.unpublish") : t("exams.publish")}</Button>
                {!x.locked && <Button size="sm" variant="ghost" onClick={() => setDel(x)}>{t("common.delete")}</Button>}
              </> : <Badge tone="indigo">{t("exams.givenByAdmin")}</Badge>}
            </Td>
          </tr>
        ))}
      </Table>
      <Pagination page={page} count={list.data?.count ?? 0} onPage={setPage} />

      <Modal open={create} onClose={() => setCreate(false)} title={t("exams.create")}
        footer={<><Button variant="secondary" onClick={() => setCreate(false)}>{t("common.cancel")}</Button><Button type="submit" form="exam-form" loading={busy}>{t("common.create")}</Button></>}>
        <form id="exam-form" onSubmit={submit} className="space-y-4">
          <Select label={t("exams.type")} value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
            <option value="UPGRADE">{t("kinds.UPGRADE")}</option>
            {admin && <option value="PLACEMENT">{t("kinds.PLACEMENT")}</option>}
          </Select>
          <p className="-mt-2 text-xs text-slate-500">{t(form.kind === "PLACEMENT" ? "exams.typePlacementHint" : "exams.typeUpgradeHint")}</p>
          <Input label={t("exams.name")} required value={form.title} error={errors.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
          <div className="grid gap-4 sm:grid-cols-2">
            <Select label={form.kind === "PLACEMENT" ? t("placements.level") : t("exams.currentLevel")} required value={form.level} error={errors.level} onChange={(e) => setForm({ ...form, level: e.target.value })}><option value="">—</option>{levels.data?.map((l) => <option key={l.id} value={l.id}>{l.code} — {l.name}</option>)}</Select>
            {form.kind === "UPGRADE" && <Select label={t("exams.targetLevel")} required value={form.target_level} error={errors.target_level} onChange={(e) => setForm({ ...form, target_level: e.target.value })}><option value="">—</option>{levels.data?.map((l) => <option key={l.id} value={l.id}>{l.code} — {l.name}</option>)}</Select>}
            <Input label={`${t("exam.duration")} (${t("common.minutes")})`} type="number" min={1} required value={form.duration_minutes} onChange={(e) => setForm({ ...form, duration_minutes: Number(e.target.value) })} />
            <Input label={`${form.kind === "PLACEMENT" ? t("exams.lowThreshold") : t("exam.passingScore")} (${t("exam.points")})`} type="number" min={0} step="0.5" required value={form.passing_score} error={errors.passing_score} hint={`${form.kind === "PLACEMENT" ? t("exams.lowThresholdHint") + " " : ""}${t("exams.pointsExample")}`} onChange={(e) => setForm({ ...form, passing_score: e.target.value })} />
            {form.kind === "UPGRADE" && <>
              <Input label={`${t("exams.speakingPoints")} (${t("exam.points")})`} type="number" min={0} step="0.5" value={form.speaking_points} error={errors.speaking_points} placeholder="0"
                onChange={(e) => setForm({ ...form, speaking_points: e.target.value })} />
              <Input label={`${t("exams.writingPoints")} (${t("exam.points")})`} type="number" min={0} step="0.5" value={form.writing_points} error={errors.writing_points} placeholder="0"
                onChange={(e) => setForm({ ...form, writing_points: e.target.value })} />
              <p className="-mt-2 text-xs text-slate-500 sm:col-span-2">{t("exams.manualPartsHint")}</p>
            </>}
            {form.kind === "PLACEMENT" && <Input label={`${t("exams.highThreshold")} (${t("exam.points")})`} type="number" min={0} step="0.5" required value={form.high_threshold} error={errors.high_threshold} hint={t("exams.highThresholdHint")} onChange={(e) => setForm({ ...form, high_threshold: e.target.value })} />}
          </div>
        </form>
      </Modal>
      <ConfirmDialog open={!!del} danger loading={busy} title={t("common.delete")} message={t("exams.deleteConfirm", { name: del?.title })} onConfirm={remove} onClose={() => setDel(null)} />
    </>
  );
}
