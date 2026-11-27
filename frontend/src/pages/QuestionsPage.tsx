import { useQueryClient } from "@tanstack/react-query";
import { FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, parseError } from "../api/client";
import type { Level, Option, Passage, QType, Question, Section } from "../api/types";
import { LevelBadge } from "../components/badges";
import { useNotify } from "../components/Toast";
import { Badge, Button, Checkbox, ConfirmDialog, FilterBar, Input, Modal, PageHeader, Pagination, SearchInput, Select, Table, Tabs, Td, Textarea } from "../components/ui";
import { num, useAll, useGet, useList } from "../lib/hooks";

const TYPES: QType[] = ["MCQ", "MSQ", "TF", "FILL", "MATCH", "READING", "LISTENING", "WRITING"];
const SECTIONS: Section[] = ["GRAMMAR", "VOCABULARY", "READING", "LISTENING", "WRITING"];
const CATEGORIES = ["GAP", "GAPTEXT", "READQA", "LISTEN", "WRITING", "MCQ", "TICK", "MISTAKE", "ODD", "WORDFORM", "DIALOGUE", "TFREAD"];
const blank = (n = 4): Option[] => Array.from({ length: n }, (_, i) => ({ text: "", match_text: "", is_correct: i === 0, order: i }));
const defaultOptions = (t: QType): Option[] =>
  t === "WRITING" ? [] : t === "TF" ? [{ text: "True", match_text: "", is_correct: true, order: 0 }, { text: "False", match_text: "", is_correct: false, order: 1 }]
    : t === "FILL" ? [{ text: "", match_text: "", is_correct: true, order: 0 }]
      : t === "MATCH" ? blank(3).map((o) => ({ ...o, is_correct: false })) : blank(4);

interface QForm { question_type: QType; section: Section; category: string; level: string; points: string; text: string; explanation: string; reading_passage: string; passage: string; options: Option[] }
const emptyForm = (): QForm => ({ question_type: "MCQ", section: "GRAMMAR", category: "", level: "", points: "1", text: "", explanation: "", reading_passage: "", passage: "", options: defaultOptions("MCQ") });

function OptionsEditor({ type, options, onChange }: { type: QType; options: Option[]; onChange: (o: Option[]) => void }) {
  const { t } = useTranslation();
  const set = (i: number, patch: Partial<Option>) => onChange(options.map((o, j) => (j === i ? { ...o, ...patch } : o)));
  const setCorrect = (i: number, v: boolean) => onChange(options.map((o, j) => (type === "MSQ" ? (j === i ? { ...o, is_correct: v } : o) : { ...o, is_correct: j === i })));
  const add = () => onChange([...options, { text: "", match_text: "", is_correct: false, order: options.length }]);
  const remove = (i: number) => onChange(options.filter((_, j) => j !== i));

  if (type === "TF") {
    return <div className="flex gap-6">{options.map((o, i) => <label key={i} className="flex items-center gap-2 text-sm"><input type="radio" name="tf" checked={o.is_correct} onChange={() => setCorrect(i, true)} />{o.text}</label>)}</div>;
  }
  return (
    <div className="space-y-2">
      {type === "FILL" && <p className="text-xs text-slate-500">{t("questions.fillHint")}</p>}
      {options.map((o, i) => (
        <div key={i} className="flex items-center gap-2">
          {type !== "FILL" && type !== "MATCH" && <input aria-label={t("questions.correct")} type={type === "MSQ" ? "checkbox" : "radio"} name="correct" checked={o.is_correct} onChange={(e) => setCorrect(i, e.target.checked)} />}
          <input required value={o.text} onChange={(e) => set(i, { text: e.target.value })} placeholder={type === "MATCH" ? t("questions.left") : type === "FILL" ? t("questions.acceptedAnswer") : `${t("questions.option")} ${i + 1}`} className="min-w-0 flex-1 rounded-lg border border-slate-300 px-3 py-1.5 text-sm" />
          {type === "MATCH" && <><span className="text-slate-400">→</span><input required value={o.match_text} onChange={(e) => set(i, { match_text: e.target.value })} placeholder={t("questions.right")} className="min-w-0 flex-1 rounded-lg border border-slate-300 px-3 py-1.5 text-sm" /></>}
          <Button type="button" size="sm" variant="ghost" disabled={options.length <= (type === "FILL" ? 1 : 2)} onClick={() => remove(i)}>✕</Button>
        </div>
      ))}
      <Button type="button" size="sm" variant="secondary" onClick={add}>+ {type === "MATCH" ? t("questions.addPair") : t("questions.addOption")}</Button>
    </div>
  );
}

export function QuestionModal({ editing, onClose, onSaved }: { editing: Question | "new" | null; onClose: () => void; onSaved: () => void }) {
  const { t } = useTranslation();
  const notify = useNotify();
  const levels = useGet<Level[]>("levels");
  const passages = useAll<Passage>("passages", {}, !!editing);
  const [form, setForm] = useState<QForm>(emptyForm());
  const [image, setImage] = useState<File | null>(null);
  const [audio, setAudio] = useState<File | null>(null);
  const [clear, setClear] = useState({ image: false, audio: false });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [loadedFor, setLoadedFor] = useState<Question | "new" | null>(null);

  if (editing && loadedFor !== editing) {
    setLoadedFor(editing); setImage(null); setAudio(null); setClear({ image: false, audio: false }); setErrors({});
    setForm(editing === "new" ? emptyForm() : { question_type: editing.question_type, section: editing.section, category: editing.category ?? "", level: String(editing.level), points: String(Number(editing.points)), text: editing.text, explanation: editing.explanation, reading_passage: editing.reading_passage, passage: String(editing.passage ?? ""), options: editing.options.map((o, i) => ({ ...o, order: i })) });
  }
  if (!editing && loadedFor) setLoadedFor(null);
  const existing = editing && editing !== "new" ? editing : null;

  const changeType = (type: QType) => setForm((f) => ({ ...f, question_type: type, options: defaultOptions(type), section: type === "READING" ? "READING" : type === "LISTENING" ? "LISTENING" : type === "WRITING" ? "WRITING" : f.section }));

  const save = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true); setErrors({});
    const fd = new FormData();
    (["question_type", "section", "category", "level", "points", "text", "explanation", "reading_passage", "passage"] as const).forEach((k) => fd.append(k, form[k]));
    fd.append("options", JSON.stringify(form.options.map((o, i) => ({ ...o, order: i }))));
    if (image) fd.append("image", image); else if (clear.image) fd.append("image", "");
    if (audio) fd.append("audio", audio); else if (clear.audio) fd.append("audio", "");
    try {
      if (existing) await api.patch(`/questions/${existing.id}/`, fd); else await api.post("/questions/", fd);
      notify.ok("common.saved"); onSaved();
    } catch (err) { setErrors(Object.fromEntries(Object.entries(parseError(err).fields).map(([k, v]) => [k, String(v)]))); notify.fail(err); } finally { setBusy(false); }
  };

  return (
    <Modal open={!!editing} onClose={onClose} wide title={existing ? t("questions.edit") : t("questions.add")}
      footer={<><Button variant="secondary" onClick={onClose}>{t("common.cancel")}</Button><Button type="submit" form="q-form" loading={busy}>{t("common.save")}</Button></>}>
      <form id="q-form" onSubmit={save} className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-5">
          <Select label={t("questions.type")} value={form.question_type} disabled={!!existing?.in_use} onChange={(e) => changeType(e.target.value as QType)}>{TYPES.map((x) => <option key={x} value={x}>{t(`qtypes.${x}`)}</option>)}</Select>
          <Select label={t("questions.section")} value={form.section} onChange={(e) => setForm({ ...form, section: e.target.value as Section })}>{SECTIONS.map((x) => <option key={x} value={x}>{t(`sections.${x}`)}</option>)}</Select>
          <Select label={t("common.level")} required value={form.level} error={errors.level} onChange={(e) => setForm({ ...form, level: e.target.value })}><option value="">—</option>{levels.data?.map((l) => <option key={l.id} value={l.id}>{l.code}</option>)}</Select>
          <Select label={t("questions.category")} value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}><option value="">—</option>{CATEGORIES.map((c) => <option key={c} value={c}>{t(`categories.${c}`)}</option>)}</Select>
          <Input label={t("exam.points")} type="number" min={0.25} step="0.25" required value={form.points} error={errors.points} onChange={(e) => setForm({ ...form, points: e.target.value })} />
        </div>
        <Textarea label={t("questions.text")} required value={form.text} error={errors.text} onChange={(e) => setForm({ ...form, text: e.target.value })} />
        {(form.question_type === "READING" || form.section === "READING") && (
          <div className="grid gap-4 sm:grid-cols-2">
            <Select label={t("questions.sharedPassage")} value={form.passage} error={errors.passage} onChange={(e) => setForm({ ...form, passage: e.target.value })}><option value="">—</option>{passages.items.map((p) => <option key={p.id} value={p.id}>{p.title} ({p.level_code})</option>)}</Select>
            <Textarea label={t("questions.inlinePassage")} value={form.reading_passage} onChange={(e) => setForm({ ...form, reading_passage: e.target.value })} />
          </div>
        )}
        {form.question_type === "LISTENING" && form.section === "LISTENING" && (
          <Select label={t("questions.sharedPassage")} value={form.passage} onChange={(e) => setForm({ ...form, passage: e.target.value })}><option value="">—</option>{passages.items.filter((p) => p.audio).map((p) => <option key={p.id} value={p.id}>{p.title} ({p.level_code})</option>)}</Select>
        )}
        {form.question_type === "WRITING" ? (
          <p className="rounded-lg bg-sky-50 p-3 text-sm text-slate-700">{t("questions.writingHint")}</p>
        ) : (
        <div>
          <p className="mb-1 text-sm font-medium text-slate-700">{t("questions.options")} {errors.options && <span className="text-xs font-normal text-red-600">— {errors.options}</span>}</p>
          <OptionsEditor type={form.question_type} options={form.options} onChange={(o) => setForm({ ...form, options: o })} />
        </div>)}
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">{t("questions.image")}</label>
            <input type="file" accept="image/*" onChange={(e) => { setImage(e.target.files?.[0] ?? null); setClear((c) => ({ ...c, image: false })); }} className="text-sm" />
            {existing?.image && !clear.image && !image && <p className="mt-1 text-xs text-slate-500">{t("questions.hasFile")} <button type="button" className="text-red-600" onClick={() => setClear({ ...clear, image: true })}>{t("common.remove")}</button></p>}
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">{t("questions.audio")} {form.question_type === "LISTENING" && <span className="text-red-500">*</span>}</label>
            <input type="file" accept="audio/*" onChange={(e) => { setAudio(e.target.files?.[0] ?? null); setClear((c) => ({ ...c, audio: false })); }} className="text-sm" />
            {errors.audio && <p className="mt-1 text-xs text-red-600">{errors.audio}</p>}
            {existing?.audio && !clear.audio && !audio && <p className="mt-1 text-xs text-slate-500">{t("questions.hasFile")} <button type="button" className="text-red-600" onClick={() => setClear({ ...clear, audio: true })}>{t("common.remove")}</button></p>}
          </div>
        </div>
        <Textarea label={`${t("questions.explanation")} (${t("common.optional")})`} value={form.explanation} onChange={(e) => setForm({ ...form, explanation: e.target.value })} />
      </form>
    </Modal>
  );
}

function PassageModal({ editing, onClose, onSaved }: { editing: Passage | "new" | null; onClose: () => void; onSaved: () => void }) {
  const { t } = useTranslation();
  const notify = useNotify();
  const levels = useGet<Level[]>("levels");
  const [f, setF] = useState({ title: "", text: "", level: "" });
  const [audio, setAudio] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [loadedFor, setLoadedFor] = useState<Passage | "new" | null>(null);
  if (editing && loadedFor !== editing) { setLoadedFor(editing); setAudio(null); setErrors({}); setF(editing === "new" ? { title: "", text: "", level: "" } : { title: editing.title, text: editing.text, level: String(editing.level) }); }
  if (!editing && loadedFor) setLoadedFor(null);

  const save = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true); setErrors({});
    const fd = new FormData();
    fd.append("title", f.title); fd.append("text", f.text); fd.append("level", f.level);
    if (audio) fd.append("audio", audio);
    try {
      if (editing && editing !== "new") await api.patch(`/passages/${editing.id}/`, fd); else await api.post("/passages/", fd);
      notify.ok("common.saved"); onSaved();
    } catch (err) { setErrors(Object.fromEntries(Object.entries(parseError(err).fields).map(([k, v]) => [k, String(v)]))); notify.fail(err); } finally { setBusy(false); }
  };
  return (
    <Modal open={!!editing} onClose={onClose} wide title={t("questions.passage")} footer={<><Button variant="secondary" onClick={onClose}>{t("common.cancel")}</Button><Button type="submit" form="p-form" loading={busy}>{t("common.save")}</Button></>}>
      <form id="p-form" onSubmit={save} className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-3"><Input className="sm:col-span-2" label={t("questions.passageTitle")} required value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} />
          <Select label={t("common.level")} required value={f.level} onChange={(e) => setF({ ...f, level: e.target.value })}><option value="">—</option>{levels.data?.map((l) => <option key={l.id} value={l.id}>{l.code}</option>)}</Select></div>
        <Textarea rows={8} label={t("questions.passageText")} value={f.text} error={errors.non_field_errors} onChange={(e) => setF({ ...f, text: e.target.value })} />
        <div><label className="mb-1 block text-sm font-medium text-slate-700">{t("questions.audio")}</label><input type="file" accept="audio/*" onChange={(e) => setAudio(e.target.files?.[0] ?? null)} className="text-sm" />
          {editing && editing !== "new" && editing.audio && <p className="mt-1 text-xs text-slate-500">{t("questions.hasFile")}</p>}</div>
      </form>
    </Modal>
  );
}

export default function QuestionsPage() {
  const { t } = useTranslation();
  const notify = useNotify();
  const qc = useQueryClient();
  const levels = useGet<Level[]>("levels");
  const [tab, setTab] = useState<"questions" | "passages">("questions");
  const [f, setF] = useState({ search: "", section: "", question_type: "", category: "", level: "", mine: "" });
  const [page, setPage] = useState(1);
  const list = useList<Question>("questions", { ...f, page }, tab === "questions");
  const plist = useList<Passage>("passages", { page }, tab === "passages");
  const [editing, setEditing] = useState<Question | "new" | null>(null);
  const [pEditing, setPEditing] = useState<Passage | "new" | null>(null);
  const [del, setDel] = useState<{ kind: "questions" | "passages"; id: number } | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof f, v: string) => { setF({ ...f, [k]: v }); setPage(1); };
  const refresh = () => { void qc.invalidateQueries({ queryKey: ["questions"] }); void qc.invalidateQueries({ queryKey: ["passages"] }); };

  const remove = async () => {
    setBusy(true);
    try { await api.delete(`/${del!.kind}/${del!.id}/`); notify.ok("common.deleted"); refresh(); } catch (e) { notify.fail(e); } finally { setBusy(false); setDel(null); }
  };

  return (
    <>
      <PageHeader title={t("nav.questions")} actions={tab === "questions" ? <Button onClick={() => setEditing("new")}>+ {t("questions.add")}</Button> : <Button onClick={() => setPEditing("new")}>+ {t("questions.addPassage")}</Button>} />
      <Tabs value={tab} onChange={(v) => { setTab(v); setPage(1); }} items={[{ value: "questions", label: t("nav.questions") }, { value: "passages", label: t("questions.passages") }]} />
      {tab === "questions" ? (
        <>
          <FilterBar>
            <SearchInput value={f.search} onChange={(v) => set("search", v)} />
            <Select value={f.section} onChange={(e) => set("section", e.target.value)} className="w-40"><option value="">{t("questions.allSections")}</option>{SECTIONS.map((s) => <option key={s} value={s}>{t(`sections.${s}`)}</option>)}</Select>
            <Select value={f.question_type} onChange={(e) => set("question_type", e.target.value)} className="w-52"><option value="">{t("questions.allTypes")}</option>{TYPES.map((s) => <option key={s} value={s}>{t(`qtypes.${s}`)}</option>)}</Select>
            <Select value={f.category} onChange={(e) => set("category", e.target.value)} className="w-56"><option value="">{t("questions.allCategories")}</option>{CATEGORIES.map((c) => <option key={c} value={c}>{t(`categories.${c}`)}</option>)}</Select>
            <Select value={f.level} onChange={(e) => set("level", e.target.value)} className="w-28"><option value="">{t("common.allLevels")}</option>{levels.data?.map((l) => <option key={l.id} value={l.id}>{l.code}</option>)}</Select>
            <Checkbox label={t("questions.mine")} checked={f.mine === "1"} onChange={(e) => set("mine", e.target.checked ? "1" : "")} />
          </FilterBar>
          <Table head={[t("questions.text"), t("questions.type"), t("questions.section"), t("common.level"), t("exam.points"), t("questions.author"), ""]} empty={!list.data?.results.length}>
            {list.data?.results.map((q) => (
              <tr key={q.id} className="hover:bg-slate-50">
                <Td className="max-w-md"><span className="line-clamp-2">{q.text}</span>{q.in_use && <Badge tone="amber">{t("questions.inUse")}</Badge>}</Td>
                <Td>{q.category ? t(`categories.${q.category}`) : t(`qtypes.${q.question_type}`)}</Td><Td>{t(`sections.${q.section}`)}</Td><Td><LevelBadge code={q.level_code} /></Td><Td>{num(q.points)}</Td><Td>{q.created_by_name ?? "—"}</Td>
                <Td className="whitespace-nowrap text-right"><Button size="sm" variant="ghost" onClick={() => setEditing(q)}>{t("common.edit")}</Button><Button size="sm" variant="ghost" onClick={() => setDel({ kind: "questions", id: q.id })}>{t("common.delete")}</Button></Td>
              </tr>
            ))}
          </Table>
          <Pagination page={page} count={list.data?.count ?? 0} onPage={setPage} />
        </>
      ) : (
        <>
          <Table head={[t("questions.passageTitle"), t("common.level"), t("questions.audio"), t("nav.questions"), ""]} empty={!plist.data?.results.length}>
            {plist.data?.results.map((p) => (
              <tr key={p.id}><Td className="font-medium">{p.title}</Td><Td><LevelBadge code={p.level_code} /></Td><Td>{p.audio ? "🔊" : "—"}</Td><Td>{p.question_count}</Td>
                <Td className="whitespace-nowrap text-right"><Button size="sm" variant="ghost" onClick={() => setPEditing(p)}>{t("common.edit")}</Button><Button size="sm" variant="ghost" onClick={() => setDel({ kind: "passages", id: p.id })}>{t("common.delete")}</Button></Td></tr>
            ))}
          </Table>
          <Pagination page={page} count={plist.data?.count ?? 0} onPage={setPage} />
        </>
      )}
      <QuestionModal editing={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); refresh(); }} />
      <PassageModal editing={pEditing} onClose={() => setPEditing(null)} onSaved={() => { setPEditing(null); refresh(); }} />
      <ConfirmDialog open={!!del} danger loading={busy} title={t("common.delete")} message={t("common.deleteConfirm")} onConfirm={remove} onClose={() => setDel(null)} />
    </>
  );
}
