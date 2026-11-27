import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api, download, parseError } from "../api/client";
import type { Assignment, Exam, Group, Level, Question, Result, Student, User, Variant } from "../api/types";
import { LoadError } from "../components/NotFound";
import { useAuth } from "../auth/AuthContext";
import { KindBadge, OutcomeBadge, StateBadge } from "../components/badges";
import { useNotify } from "../components/Toast";
import { Badge, BarList, Button, Card, Checkbox, ConfirmDialog, EmptyState, Input, Modal, PageHeader, PageLoader, Pagination, ProgressBar, SearchInput, Select, StatCard, Table, Tabs, Td, Textarea } from "../components/ui";
import { fmtDate, fromLocalInput, num, useAll, useGet, useList } from "../lib/hooks";
import { QuestionModal } from "./QuestionsPage";
import { Marked } from "../lib/marked";

/* ------------------------------------------------------------------ settings */
function SettingsTab({ exam }: { exam: Exam }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const teachers = useAll<User>("users", { role: "TEACHER" }, user!.role === "ADMIN");
  const notify = useNotify();
  const qc = useQueryClient();
  const levels = useGet<Level[]>("levels");
  const variants = useGet<Variant[]>("variants", { examination: exam.id });
  // thresholds are points: show what each variant is worth so the admin picks a sensible mark
  const worth = variants.data?.filter((v) => v.question_count).map((v) => `${v.name}: ${num(v.total_points)}`).join(", ");
  const [f, setF] = useState({ ...exam, teachers: exam.teachers, passing_score: Number(exam.passing_score), high_threshold: exam.high_threshold == null ? "" : Number(exam.high_threshold), speaking_points: String(Number(exam.speaking_points ?? 0)), writing_points: String(Number(exam.writing_points ?? 0)) });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const placement = exam.kind === "PLACEMENT";

  const save = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true); setErrors({});
    try {
      await api.patch(`/examinations/${exam.id}/`, {
        title: f.title, level: f.level, target_level: placement ? null : f.target_level, instructions: f.instructions,
        duration_minutes: f.duration_minutes, passing_score: f.passing_score, high_threshold: placement && f.high_threshold !== "" ? f.high_threshold : null,
        shuffle_questions: f.shuffle_questions, shuffle_options: f.shuffle_options, show_correct_answers: f.show_correct_answers,
        ...(placement ? {} : { speaking_points: f.speaking_points === "" ? 0 : Number(f.speaking_points), writing_points: f.writing_points === "" ? 0 : Number(f.writing_points) }),
        ...(user!.role === "ADMIN" ? { teachers: f.teachers } : {}),
      });
      notify.ok("common.saved"); void qc.invalidateQueries({ queryKey: ["examinations"] });
    } catch (err) { setErrors(Object.fromEntries(Object.entries(parseError(err).fields).map(([k, v]) => [k, String(v)]))); notify.fail(err); } finally { setBusy(false); }
  };

  return (
    <Card>
      <form onSubmit={save} className="space-y-4">
        <Input label={t("exams.name")} required value={f.title} error={errors.title} onChange={(e) => setF({ ...f, title: e.target.value })} />
        <div className="grid gap-4 sm:grid-cols-2">
          <Select label={placement ? t("exam.level") : t("exams.currentLevel")} disabled={exam.locked || placement} value={f.level} onChange={(e) => setF({ ...f, level: Number(e.target.value) })}>{levels.data?.map((l) => <option key={l.id} value={l.id}>{l.code} — {l.name}</option>)}</Select>
          {!placement && <Select label={t("exams.targetLevel")} disabled={exam.locked} value={f.target_level ?? ""} error={errors.target_level} onChange={(e) => setF({ ...f, target_level: Number(e.target.value) })}>{levels.data?.map((l) => <option key={l.id} value={l.id}>{l.code} — {l.name}</option>)}</Select>}
          <Input label={`${t("exam.duration")} (${t("common.minutes")})`} type="number" min={1} required value={f.duration_minutes} onChange={(e) => setF({ ...f, duration_minutes: Number(e.target.value) })} />
          <Input label={`${placement ? t("exams.lowThreshold") : t("exam.passingScore")} (${t("exam.points")})`} type="number" min={0} step="0.5" required value={f.passing_score} error={errors.passing_score}
            hint={[placement ? t("exams.lowThresholdHint") : "", worth ? t("exams.variantWorth", { list: worth }) : t("exams.noQuestionsYet")].filter(Boolean).join(" ")} onChange={(e) => setF({ ...f, passing_score: Number(e.target.value) })} />
          {!placement && <Input label={`${t("exams.speakingPoints")} (${t("exam.points")})`} type="number" min={0} step="0.5" value={f.speaking_points} hint={t("exams.speakingHint")}
            onChange={(e) => setF({ ...f, speaking_points: e.target.value })} />}
          {!placement && <Input label={`${t("exams.writingPoints")} (${t("exam.points")})`} type="number" min={0} step="0.5" value={f.writing_points} hint={t("exams.writingHint")}
            onChange={(e) => setF({ ...f, writing_points: e.target.value })} />}
          {placement && <Input label={`${t("exams.highThreshold")} (${t("exam.points")})`} type="number" min={0} step="0.5" value={f.high_threshold} error={errors.high_threshold} hint={t("exams.highThresholdHint")} onChange={(e) => setF({ ...f, high_threshold: e.target.value === "" ? "" : Number(e.target.value) })} />}
        </div>
        <Textarea label={t("exams.instructions")} value={f.instructions} onChange={(e) => setF({ ...f, instructions: e.target.value })} />
        <div className="flex flex-wrap gap-6">
          <Checkbox label={t("exams.shuffleQuestions")} checked={f.shuffle_questions} onChange={(e) => setF({ ...f, shuffle_questions: e.target.checked })} />
          <Checkbox label={t("exams.shuffleOptions")} checked={f.shuffle_options} onChange={(e) => setF({ ...f, shuffle_options: e.target.checked })} />
        </div>
        {user!.role === "ADMIN" && (
          <div className="rounded-xl border border-sky-200 bg-sky-50/50 p-4">
            <p className="text-sm font-semibold text-slate-800">{t("exams.teachersTitle")}</p>
            <p className="mb-3 text-xs text-slate-500">{t("exams.teachersHint")}</p>
            {teachers.items.length === 0 ? <p className="text-sm text-slate-500">{t("exams.noTeachers")}</p> : (
              <div className="flex flex-wrap gap-x-6 gap-y-2">
                {teachers.items.map((x) => (
                  <Checkbox key={x.id} label={x.full_name} checked={f.teachers.includes(x.id)}
                    onChange={() => setF({ ...f, teachers: f.teachers.includes(x.id) ? f.teachers.filter((i) => i !== x.id) : [...f.teachers, x.id] })} />
                ))}
              </div>
            )}
          </div>
        )}
        {exam.locked && <p className="text-sm text-amber-700">{t("exams.lockedNotice")}</p>}
        <Button type="submit" loading={busy}>{t("common.save")}</Button>
      </form>
    </Card>
  );
}

/* ------------------------------------------------------------------ variants */
function QuestionPicker({ open, exclude, onClose, onAdd }: { open: boolean; exclude: number[]; onClose: () => void; onAdd: (ids: number[]) => void }) {
  const { t } = useTranslation();
  const levels = useGet<Level[]>("levels");
  const [f, setF] = useState({ search: "", section: "", level: "", question_type: "" });
  const [picked, setPicked] = useState<number[]>([]);
  const list = useList<Question>("questions", { ...f, is_active: true, page_size: 50 }, open);
  useEffect(() => { if (open) setPicked([]); }, [open]);
  const rows = list.data?.results.filter((q) => !exclude.includes(q.id)) ?? [];
  return (
    <Modal open={open} onClose={onClose} wide title={t("exams.addQuestions")} footer={<><Button variant="secondary" onClick={onClose}>{t("common.cancel")}</Button><Button disabled={!picked.length} onClick={() => onAdd(picked)}>{t("common.add")} ({picked.length})</Button></>}>
      <div className="mb-3 flex flex-wrap gap-2">
        <SearchInput value={f.search} onChange={(v) => setF((s) => ({ ...s, search: v }))} />
        <Select value={f.section} onChange={(e) => setF({ ...f, section: e.target.value })} className="w-40"><option value="">{t("questions.allSections")}</option>{["GRAMMAR", "VOCABULARY", "READING", "LISTENING"].map((s) => <option key={s} value={s}>{t(`sections.${s}`)}</option>)}</Select>
        <Select value={f.level} onChange={(e) => setF({ ...f, level: e.target.value })} className="w-28"><option value="">{t("common.allLevels")}</option>{levels.data?.map((l) => <option key={l.id} value={l.id}>{l.code}</option>)}</Select>
      </div>
      {rows.length === 0 ? <EmptyState /> : (
        <ul className="divide-y divide-slate-100 text-sm">
          {rows.map((q) => (
            <li key={q.id} className="py-2"><label className="flex cursor-pointer items-start gap-3">
              <input type="checkbox" className="mt-1" checked={picked.includes(q.id)} onChange={() => setPicked((p) => p.includes(q.id) ? p.filter((i) => i !== q.id) : [...p, q.id])} />
              <span className="min-w-0 flex-1"><span className="line-clamp-2">{q.text}</span><span className="mt-1 flex gap-2 text-xs text-slate-500"><Badge tone="indigo">{q.level_code}</Badge><span>{t(`sections.${q.section}`)}</span><span>{t(`qtypes.${q.question_type}`)}</span><span>{num(q.points)} {t("exam.points")}</span></span></span>
            </label></li>
          ))}
        </ul>
      )}
    </Modal>
  );
}

function ImportModal({ variant, exam, onClose, onDone }: { variant: Variant | null; exam: Exam; onClose: () => void; onDone: (closeNow: boolean) => void }) {
  const { t } = useTranslation();
  const notify = useNotify();
  const levels = useGet<Level[]>("levels");
  const [file, setFile] = useState<File | null>(null);
  const [section, setSection] = useState("GRAMMAR");
  const [level, setLevel] = useState(String(exam.level));
  const [busy, setBusy] = useState(false);
  type Issue = { row: number; message: string; text?: string };
  const [errs, setErrs] = useState<Issue[]>([]);
  const [audio, setAudio] = useState<File | null>(null);
  const [skipped, setSkipped] = useState<Issue[]>([]);
  const [done, setDone] = useState(0);

  useEffect(() => {
    if (variant) { setFile(null); setAudio(null); setErrs([]); setSkipped([]); setDone(0); }
  }, [variant]);

  const submit = async () => {
    if (!file) return;
    setBusy(true); setErrs([]); setSkipped([]); setDone(0);
    const fd = new FormData();
    fd.append("file", file); fd.append("section", section); fd.append("level", level);
    if (audio) fd.append("audio", audio);
    try {
      const { data } = await api.post<{ created: number; skipped: Issue[] }>(`/variants/${variant!.id}/import/`, fd);
      notify.ok("import.done", { n: data.created });
      onDone(data.skipped.length === 0);
      if (data.skipped.length) { setSkipped(data.skipped); setDone(data.created); }
      setFile(null);
    } catch (e) {
      const list = (e as { response?: { data?: { errors?: { row: number; message: string; text?: string }[] } } }).response?.data?.errors;
      if (Array.isArray(list)) setErrs(list); else notify.fail(e);
    } finally { setBusy(false); }
  };

  return (
    <Modal open={!!variant} onClose={onClose} wide title={`${t("import.title")} — ${t("exams.variant")} ${variant?.name ?? ""}`}
      footer={<><Button variant="secondary" onClick={onClose}>{t("common.cancel")}</Button><Button disabled={!file} loading={busy} onClick={submit}>{t("import.upload")}</Button></>}>
      <p className="text-sm text-slate-600">{t("import.hint")}</p>
      <div className="mt-3 flex flex-wrap gap-3 text-sm">
        <button className="text-indigo-600 hover:underline" onClick={() => download("/variants/import-template/", {}, "questions-template.xlsx")}>⬇ {t("import.template")}</button>
      </div>
      <pre className="mt-3 overflow-x-auto rounded-lg bg-slate-50 p-3 text-xs text-slate-600">{`1. She ___ a student.\nA) is\nB) are\nC) am\nAnswer: A`}</pre>
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <Select label={t("import.defaultSection")} value={section} onChange={(e) => setSection(e.target.value)}>{["GRAMMAR", "VOCABULARY", "READING", "LISTENING"].map((s) => <option key={s} value={s}>{t(`sections.${s}`)}</option>)}</Select>
        <Select label={t("import.defaultLevel")} value={level} onChange={(e) => setLevel(e.target.value)}>{levels.data?.map((l) => <option key={l.id} value={l.id}>{l.code}</option>)}</Select>
      </div>
      <label className="mt-4 flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-sky-300 bg-sky-50/50 px-4 py-8 text-center text-sm text-slate-600 hover:bg-sky-50">
        <span className="font-medium text-indigo-700">{file ? file.name : t("import.choose")}</span>
        <span className="mt-1 text-xs text-slate-500">.xlsx · .csv · .pdf · .txt</span>
        <input type="file" accept=".xlsx,.csv,.pdf,.txt" className="hidden" onChange={(e) => { setFile(e.target.files?.[0] ?? null); setErrs([]); }} />
      </label>
      <label className="mt-3 block text-sm text-slate-600">
        <span className="font-medium text-slate-700">{t("import.audio")}</span>
        <input type="file" accept="audio/*" className="mt-1 block text-sm" onChange={(e) => setAudio(e.target.files?.[0] ?? null)} />
        <span className="text-xs text-slate-500">{t("import.audioHint")}</span>
      </label>
      {skipped.length > 0 && (
        <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900" role="status">
          <p className="mb-2 font-medium">{t("import.partial", { n: done, m: skipped.length })}</p>
          <ul className="max-h-48 list-disc space-y-1 overflow-y-auto pl-5">
            {skipped.map((er, i) => <li key={i}>{er.row ? `#${er.row} ` : ""}{er.text ? `“${er.text}” — ` : ""}{t(`import.err.${er.message}`, { defaultValue: er.message })}</li>)}
          </ul>
        </div>
      )}
      {errs.length > 0 && (
        <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800" role="alert">
          <p className="mb-2 font-medium">{t("import.failed")}</p>
          <ul className="max-h-48 list-disc space-y-1 overflow-y-auto pl-5">
            {errs.map((er, i) => <li key={i}>{er.row ? `#${er.row} ` : ""}{er.text ? `“${er.text}” — ` : ""}{t(`import.err.${er.message}`, { defaultValue: er.message })}</li>)}
          </ul>
        </div>
      )}
    </Modal>
  );
}

interface PreviewQ { n: number | null; text: string; type: string; answer: string | null; options: string[]; status: string }
interface PreviewSection { index: number; title: string; category: string; category_label: string; passage: string; questions: PreviewQ[]; answers_given: boolean }

function TextImportModal({ variant, onClose, onDone }: { variant: Variant | null; onClose: () => void; onDone: () => void }) {
  const { t } = useTranslation();
  const notify = useNotify();
  const [text, setText] = useState("");
  const [answers, setAnswers] = useState("");
  const [hlHint, setHlHint] = useState(false);
  const [preview, setPreview] = useState<{ sections: PreviewSection[]; ready: number } | null>(null);
  const [audio, setAudio] = useState<File | null>(null);
  const [busy, setBusy] = useState<"check" | "save" | null>(null);

  useEffect(() => { if (variant) { setText(""); setAnswers(""); setPreview(null); setAudio(null); } }, [variant]);
  const send = async (save: boolean) => {
    setBusy(save ? "save" : "check");
    try {
      const fd = new FormData();
      fd.append("text", text); fd.append("answers", answers); fd.append("save", save ? "true" : "false");
      if (audio) fd.append("audio", audio);
      const { data } = await api.post(`/variants/${variant!.id}/text-import/`, fd);
      if (save) { notify.ok("textImport.saved", { n: data.created }); onDone(); } else setPreview(data);
    } catch (e) { notify.fail(e); } finally { setBusy(null); }
  };

  return (
    <Modal open={!!variant} onClose={onClose} wide title={`${t("textImport.title")} — ${t("exams.variant")} ${variant?.name ?? ""}`}
      footer={<><Button variant="secondary" onClick={onClose}>{t("common.cancel")}</Button>
        <Button variant="secondary" disabled={!text.trim()} loading={busy === "check"} onClick={() => send(false)}>{t("textImport.check")}</Button>
        <Button disabled={!preview || preview.ready === 0} loading={busy === "save"} onClick={() => send(true)}>{t("textImport.save", { n: preview?.ready ?? 0 })}</Button></>}>
      <p className="text-sm text-slate-600">{t("textImport.hint")}</p>
      <div className="mt-3 flex flex-wrap gap-1.5">{["GAP", "GAPTEXT", "READQA", "LISTEN", "WRITING", "MCQ", "TICK", "MISTAKE", "ODD", "WORDFORM", "DIALOGUE", "TFREAD"].map((c) => <Badge key={c} tone="blue">{t(`categories.${c}`)}</Badge>)}</div>
      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <div>
        <div className="mb-1 flex items-center justify-end gap-2">
          {hlHint && <span className="text-xs text-amber-700">{t("textImport.highlightSelect")}</span>}
          <Button size="sm" variant="secondary" title={t("textImport.highlightHint")} onClick={() => {
            const el = document.getElementById("ti-text") as HTMLTextAreaElement | null;
            if (!el || el.selectionStart === el.selectionEnd) { setHlHint(true); return; }
            setHlHint(false);
            const a = el.selectionStart, b = el.selectionEnd;
            setText(text.slice(0, a) + "**" + text.slice(a, b) + "**" + text.slice(b)); setPreview(null);
          }}>🖍 {t("textImport.highlight")}</Button>
        </div>
        <Textarea id="ti-text" rows={14} label={t("textImport.testText")} value={text} onChange={(e) => { setText(e.target.value); setPreview(null); }} placeholder={"1. Complete the sentences.\n2 My sisters ______ both pretty.\n3 Rosie ______ only ten.\n\n2. Tick the correct sentence.\n1 ☐ I like leave early.\n☐ I'd like to leave early."} />
        </div>
        <Textarea rows={14} label={t("textImport.answers")} value={answers} onChange={(e) => { setAnswers(e.target.value); setPreview(null); }} hint={t("textImport.answersHint")} placeholder={"are, is\n\nB\n\n(1-bo'lim, bo'sh qator, 2-bo'lim, ...)"} />
      </div>
      <label className="mt-4 block text-sm text-slate-600">
        <span className="font-medium text-slate-700">🎧 {t("textImport.audio")}</span>
        <input type="file" accept="audio/*" className="mt-1 block text-sm" onChange={(e) => { setAudio(e.target.files?.[0] ?? null); setPreview(null); }} />
        <span className="text-xs text-slate-500">{t("textImport.audioHint")}</span>
      </label>
      {preview && (
        <div className="mt-5 space-y-4">
          <p className="text-sm font-medium text-slate-700">{t("textImport.found", { sections: preview.sections.length, n: preview.ready })}</p>
          {preview.sections.length === 0 && <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">{t("textImport.nothing")}</p>}
          {preview.sections.map((s) => (
            <section key={s.index} className="rounded-xl border border-slate-200">
              <header className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 bg-sky-50/60 px-4 py-2 text-sm">
                <span className="font-semibold">{s.index}. <Marked text={s.title} /></span><Badge tone="indigo">{t(`categories.${s.category}`)}</Badge>
              </header>
              {s.questions.length === 0 ? <p className="px-4 py-3 text-sm text-amber-700">{t("textImport.noQuestions")}</p> : (
                <ul className="divide-y divide-slate-100 text-sm">
                  {s.questions.map((q, i) => (
                    <li key={i} className="flex items-start justify-between gap-3 px-4 py-2">
                      <span className="min-w-0"><span className="text-slate-400">{q.n ?? i + 1}. </span>{q.text}{q.options.length > 0 && <span className="block text-xs text-slate-500">{q.options.join("  ·  ")}</span>}</span>
                      <span className={q.status === "ok" ? "shrink-0 font-semibold text-emerald-700" : "shrink-0 text-xs font-medium text-red-600"}>{q.status === "ok" ? (q.type === "WRITING" ? t("textImport.writingTask") : q.answer) : q.status === "no_audio" ? t("textImport.noAudio") : t("textImport.noAnswer")}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          ))}
        </div>
      )}
    </Modal>
  );
}

function VariantsTab({ exam }: { exam: Exam }) {
  const { t } = useTranslation();
  const notify = useNotify();
  const qc = useQueryClient();
  const variants = useQuery({ queryKey: ["variants", exam.id], queryFn: async () => (await api.get<Variant[]>("/variants/", { params: { examination: exam.id } })).data });
  const [picker, setPicker] = useState<Variant | null>(null);
  const [importing, setImporting] = useState<Variant | null>(null);
  const [pasting, setPasting] = useState<Variant | null>(null);
  const refresh = () => { void qc.invalidateQueries({ queryKey: ["variants"] }); void qc.invalidateQueries({ queryKey: ["examinations"] }); };

  const add = async () => {
    const n = variants.data?.length ?? 0;
    try { await api.post("/variants/", { examination: exam.id, name: String.fromCharCode(65 + n), order: n }); refresh(); } catch (e) { notify.fail(e); }
  };
  const saveQuestions = async (v: Variant, ids: number[]) => {
    try { await api.put(`/variants/${v.id}/questions/`, { question_ids: ids }); refresh(); } catch (e) { notify.fail(e); }
  };
  const remove = async (v: Variant) => { try { await api.delete(`/variants/${v.id}/`); refresh(); } catch (e) { notify.fail(e); } };
  const [copying, setCopying] = useState<number | null>(null);
  const duplicate = async (v: Variant) => {
    setCopying(v.id);
    try {
      const { data } = await api.post<Variant>(`/variants/${v.id}/duplicate/`);
      notify.ok("exams.duplicated", { from: v.name, name: data.name });
      refresh(); void qc.invalidateQueries({ queryKey: ["questions"] });
    } catch (e) { notify.fail(e); } finally { setCopying(null); }
  };
  // edit a question of the variant in the same form as the question bank
  const [editing, setEditing] = useState<Question | null>(null);
  const [opening, setOpening] = useState<number | null>(null);
  const openEditor = async (questionId: number) => {
    setOpening(questionId);
    try { const { data } = await api.get<Question>(`/questions/${questionId}/`); setEditing(data); } catch (e) { notify.fail(e); } finally { setOpening(null); }
  };
  const move = (v: Variant, i: number, d: number) => {
    const ids = v.questions.map((x) => x.question);
    [ids[i], ids[i + d]] = [ids[i + d], ids[i]];
    void saveQuestions(v, ids);
  };

  if (!variants.data) return <PageLoader />;
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between"><p className="text-sm text-slate-500">{t("exams.variantsHint")}</p>{!exam.locked && exam.can_edit && <Button onClick={add}>+ {t("exams.addVariant")}</Button>}</div>
      {variants.data.length === 0 && <Card><EmptyState text={t("exams.noVariants")} /></Card>}
      {variants.data.map((v) => (
        <Card key={v.id} title={<>{`${t("exams.variant")} ${v.name} — ${v.question_count} ${t("exam.questions").toLowerCase()}, ${num(v.total_points)} ${t("exam.points")}`}</>}
          actions={!exam.locked && exam.can_edit && <><Button size="sm" variant="secondary" onClick={() => setPasting(v)}>📋 {t("textImport.button")}</Button><Button size="sm" variant="secondary" onClick={() => setImporting(v)}>⬆ {t("import.title")}</Button><Button size="sm" variant="secondary" onClick={() => setPicker(v)}>+ {t("exams.addQuestions")}</Button>{v.question_count > 0 && <Button size="sm" variant="secondary" loading={copying === v.id} onClick={() => duplicate(v)} title={t("exams.duplicateHint")}>⧉ {t("exams.duplicateVariant")}</Button>}<Button size="sm" variant="ghost" onClick={() => remove(v)}>{t("common.delete")}</Button></>}>
          {v.questions.length === 0 ? <EmptyState text={t("exams.variantEmpty")} /> : (
            <ol className="divide-y divide-slate-100 text-sm">
              {v.questions.map((q, i) => (
                <li key={q.id} className="flex items-center gap-3 py-2">
                  <span className="w-6 text-slate-400">{i + 1}.</span>
                  <span className="min-w-0 flex-1"><span className="line-clamp-1">{q.text}</span><span className="text-xs text-slate-500">{t(`sections.${q.section}`)} · {t(`qtypes.${q.question_type}`)} · {num(q.points)}</span></span>
                  {!exam.locked && exam.can_edit && <span className="flex shrink-0">
                    <Button size="sm" variant="ghost" loading={opening === q.question} onClick={() => openEditor(q.question)} title={t("questions.edit")} aria-label={t("questions.edit")}>✏️ {t("common.edit")}</Button>
                    <Button size="sm" variant="ghost" disabled={i === 0} onClick={() => move(v, i, -1)} aria-label="up">↑</Button>
                    <Button size="sm" variant="ghost" disabled={i === v.questions.length - 1} onClick={() => move(v, i, 1)} aria-label="down">↓</Button>
                    <Button size="sm" variant="ghost" onClick={() => saveQuestions(v, v.questions.filter((x) => x.id !== q.id).map((x) => x.question))}>✕</Button></span>}
                </li>
              ))}
            </ol>
          )}
        </Card>
      ))}
      <QuestionModal editing={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); refresh(); void qc.invalidateQueries({ queryKey: ["questions"] }); }} />
      <TextImportModal variant={pasting} onClose={() => setPasting(null)} onDone={() => { setPasting(null); refresh(); void qc.invalidateQueries({ queryKey: ["questions"] }); }} />
      <ImportModal variant={importing} exam={exam} onClose={() => setImporting(null)} onDone={(closeNow) => { if (closeNow) setImporting(null); refresh(); void qc.invalidateQueries({ queryKey: ["questions"] }); }} />
      <QuestionPicker open={!!picker} exclude={picker?.questions.map((q) => q.question) ?? []} onClose={() => setPicker(null)}
        onAdd={async (ids) => { const v = picker!; setPicker(null); await saveQuestions(v, [...v.questions.map((q) => q.question), ...ids]); }} />
    </div>
  );
}

/* ------------------------------------------------------------------ results */
/** Everyone who sat this exam (the teacher sees their own students), best score first; filter by group. */
function ResultsTab({ exam }: { exam: Exam }) {
  const { t } = useTranslation();
  const groups = useAll<Group>("groups", { is_active: true });
  const [group, setGroup] = useState("");
  const [page, setPage] = useState(1);
  const params = { examination: exam.id, ...(group ? { group } : {}) };
  const list = useList<Result>("results", { ...params, page, ordering: "-total_score" });
  const summary = useGet<{ total: number; decided: number; passed: number; failed: number; awaiting: number; avg_score: number | null; avg_max: number | null }>("analytics/results-summary", params);
  const shown = exam.kind === "UPGRADE" ? groups.items.filter((g) => g.level === exam.level) : groups.items;
  const s = summary.data;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <Select label={t("nav.groups")} className="w-64" value={group} onChange={(e) => { setGroup(e.target.value); setPage(1); }}>
          <option value="">{t("exams.allGroups")}</option>
          {shown.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
        </Select>
      </div>
      {s && (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatCard label={t("exams.sat")} value={s.total} />
          <StatCard label={t("result.passed")} value={`${s.passed} / ${s.decided}`} hint={s.awaiting ? t("stats.awaitingShort", { n: s.awaiting }) : undefined} />
          <StatCard label={t("result.failed")} value={s.failed} />
          <StatCard label={t("results.average")} value={s.avg_score === null ? "—" : `${num(s.avg_score)} / ${num(s.avg_max!)} ${t("exam.points")}`} />
        </div>
      )}
      <Table head={["#", t("common.student"), t("result.score"), t("groupExams.answers"), t("result.status"), t("groupExams.finishedAt"), ""]} empty={!list.data?.results.length}>
        {list.data?.results.map((r, i) => (
          <tr key={r.id} className="hover:bg-slate-50">
            <Td className="tabular-nums text-slate-500">{(page - 1) * 20 + i + 1}</Td>
            <Td className="font-medium">{r.student_name}</Td>
            <Td className="min-w-36">
              <p className="whitespace-nowrap font-semibold tabular-nums">{num(r.total_score)} / {num(r.max_score)} {t("exam.points")}</p>
              <ProgressBar className="mt-1" value={Number(r.max_score) ? (Number(r.total_score) / Number(r.max_score)) * 100 : 0} tone={Number(r.total_score) >= Number(exam.passing_score) ? "green" : "amber"} />
            </Td>
            <Td className="whitespace-nowrap text-xs"><span className="text-emerald-700">✓ {r.correct_count}</span> · <span className="text-red-600">✗ {r.incorrect_count}</span> · <span className="text-slate-500">— {r.unanswered_count}</span></Td>
            <Td><OutcomeBadge r={r} /></Td>
            <Td className="whitespace-nowrap text-xs text-slate-500">{fmtDate(r.created_at)}</Td>
            <Td className="text-right"><Link to={`/results/${r.id}`} className="whitespace-nowrap text-sm font-medium text-indigo-700 hover:underline">{t("groupExams.openResult")} →</Link></Td>
          </tr>
        ))}
      </Table>
      <Pagination page={page} count={list.data?.count ?? 0} onPage={setPage} />
    </div>
  );
}

/* ------------------------------------------------------------------ assign */
interface GroupGrant { group: number; name: string; level: string; teacher: string | null; students: number; assigned: number; given_by: string | null; given_at: string }

/** Admin gives an upgrade exam to groups (the teacher picks students) or straight to students; teachers assign to students. */
function AssignTab({ exam }: { exam: Exam }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  if (exam.status !== "PUBLISHED") return <Card><p className="text-sm text-amber-700">{t("exams.publishFirst")}</p></Card>;
  return (
    <div className="space-y-6">
      {user!.role === "ADMIN" ? <><GiveToGroups exam={exam} /><TeacherAssign exam={exam} direct /></> : <TeacherAssign exam={exam} />}
      <AssignmentList exam={exam} />
    </div>
  );
}

function GiveToGroups({ exam }: { exam: Exam }) {
  const { t } = useTranslation();
  const notify = useNotify();
  const qc = useQueryClient();
  const groups = useAll<Group>("groups", { is_active: true });
  const grants = useGet<GroupGrant[]>(`examinations/${exam.id}/groups`);
  const [picked, setPicked] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const [back, setBack] = useState<GroupGrant | null>(null);
  const [report, setReport] = useState<{ groups_added: number; groups_existing: number; groups_level_mismatch: { name: string; level: string }[]; groups_without_teacher: string[]; students_assigned: number } | null>(null);
  const given = new Set(grants.data?.map((g) => g.group));
  const refresh = () => { void qc.invalidateQueries({ queryKey: [`examinations/${exam.id}/groups`] }); void qc.invalidateQueries({ queryKey: ["examinations"] }); };

  const submit = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`/examinations/${exam.id}/assign/`, { group_ids: picked });
      setReport(data); setPicked([]); notify.ok("exams.givenSummary", { n: data.groups_added }); refresh(); void qc.invalidateQueries({ queryKey: ["assignments"] });
    } catch (e) { notify.fail(e); } finally { setBusy(false); }
  };
  const takeBack = async () => {
    setBusy(true);
    try { await api.post(`/examinations/${exam.id}/revoke-group/`, { group: back!.group }); notify.ok("common.saved"); refresh(); } catch (e) { notify.fail(e); } finally { setBusy(false); setBack(null); }
  };

  const fitting = groups.items.filter((g) => g.level === exam.level);
  return (
    <>
      <Card title={t("exams.giveToGroups")}>
        <p className="mb-4 text-xs text-slate-500">{t("exams.giveHint", { level: exam.level_code })}</p>
        {fitting.length === 0 ? <EmptyState /> : (
          <div className="grid gap-x-6 gap-y-1 sm:grid-cols-2">
            {fitting.map((g) => (
              <Checkbox key={g.id} disabled={given.has(g.id)}
                label={`${g.name} · ${g.teacher_name ?? "—"} · ${g.student_count} ${t("nav.students").toLowerCase()}${given.has(g.id) ? " ✓" : ""}`}
                checked={given.has(g.id) || picked.includes(g.id)}
                onChange={() => setPicked((p) => p.includes(g.id) ? p.filter((i) => i !== g.id) : [...p, g.id])} />
            ))}
          </div>
        )}
        <Button className="mt-4" loading={busy} disabled={!picked.length} onClick={submit}>{t("exams.giveToGroups")}</Button>
        {report && (
          <div className={`mt-4 rounded-xl border p-4 text-sm ${report.groups_added || report.students_assigned ? "border-emerald-200 bg-emerald-50 text-emerald-900" : "border-amber-200 bg-amber-50 text-amber-900"}`} role="status">
            <p className="font-semibold">{t("exams.givenSummary", { n: report.groups_added })}{report.groups_existing > 0 && ` ${t("exams.givenExisting", { n: report.groups_existing })}`} {t("exams.studentsGot", { n: report.students_assigned })}</p>
            {report.groups_level_mismatch.length > 0 && <p className="mt-2">{t("exams.givenMismatch")} {report.groups_level_mismatch.map((m) => `${m.name} (${m.level})`).join(", ")}</p>}
            {report.groups_without_teacher.length > 0 && <p className="mt-2">{t("exams.noTeacherWarn")} {report.groups_without_teacher.join(", ")}</p>}
          </div>
        )}
      </Card>

      <Card title={t("exams.givenGroups")}>
        {!grants.data?.length ? <EmptyState text={t("exams.noGroupsGiven")} /> : (
          <Table head={[t("nav.groups"), t("exams.colTeacher"), t("exams.colAssigned"), t("common.date"), ""]}>
            {grants.data.map((g) => (
              <tr key={g.group}>
                <Td className="font-medium">{g.name}</Td>
                <Td>{g.teacher ?? <span className="text-amber-700">—</span>}</Td>
                <Td className="whitespace-nowrap">{t("exams.assignedOf", { n: g.assigned, total: g.students })}</Td>
                <Td className="whitespace-nowrap text-xs text-slate-500">{fmtDate(g.given_at)}</Td>
                <Td className="text-right"><Button size="sm" variant="ghost" onClick={() => setBack(g)}>{t("exams.takeBack")}</Button></Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
      <ConfirmDialog open={!!back} danger loading={busy} title={t("exams.takeBack")} confirmLabel={t("exams.takeBack")}
        message={t("exams.takeBackConfirm", { group: back?.name })} onConfirm={takeBack} onClose={() => setBack(null)} />
    </>
  );
}

/** Teacher: assigns to students / whole groups. `direct`: the admin assigning straight to students, bypassing the teacher. */
function TeacherAssign({ exam, direct = false }: { exam: Exam; direct?: boolean }) {
  const { t } = useTranslation();
  const notify = useNotify();
  const qc = useQueryClient();
  const allGroups = useAll<Group>("groups", { is_active: true });
  const grants = useGet<GroupGrant[]>(`examinations/${exam.id}/groups`);
  // an exam the admin gave to my groups: only those groups and their students
  const givenIds = grants.data?.map((g) => g.group) ?? [];
  const groups = { items: exam.can_edit ? allGroups.items : allGroups.items.filter((g) => givenIds.includes(g.id)) };
  const variants = useGet<Variant[]>("variants", { examination: exam.id });
  const [search, setSearch] = useState("");
  const [ofGroup, setOfGroup] = useState("");
  const studentGroup = ofGroup || (exam.can_edit ? "" : String(givenIds[0] ?? ""));
  const students = useList<Student>("students", { search, page_size: 8, ...(studentGroup ? { groups: studentGroup } : {}) });
  const [report, setReport] = useState<{ created: number; skipped_existing: number; skipped_level_mismatch: { name: string; level: string | null }[] } | null>(null);
  const levelOf = (s: Student) => s.current_level_code ?? s.initial_level_code;
  const fits = (s: Student) => { const l = s.current_level ?? s.initial_level; return l == null || l === exam.level; };  // no level yet: may sit it
  const [pickedStudents, setPickedStudents] = useState<Student[]>([]);
  const [pickedGroups, setPickedGroups] = useState<number[]>([]);
  const [variant, setVariant] = useState("");
  const [from, setFrom] = useState("");
  const [until, setUntil] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    try {
      setReport(null);
      const { data } = await api.post<{ created: number; skipped_existing: number; skipped_level_mismatch: { name: string; level: string | null }[] }>(`/examinations/${exam.id}/assign/`, {
        ...(direct ? { to: "students" } : {}),
        student_ids: pickedStudents.map((s) => s.id), group_ids: direct ? [] : pickedGroups, variant: variant ? Number(variant) : null,
        available_from: fromLocalInput(from), available_until: fromLocalInput(until),
      });
      setReport(data);
      notify.ok("exams.assignedSummary", { created: data.created, skipped: data.skipped_existing + data.skipped_level_mismatch.length });
      setPickedStudents([]); setPickedGroups([]);
      void qc.invalidateQueries({ queryKey: ["assignments"] }); void qc.invalidateQueries({ queryKey: ["examinations"] });
      void qc.invalidateQueries({ queryKey: [`examinations/${exam.id}/groups`] });
    } catch (e) { notify.fail(e); } finally { setBusy(false); }
  };

  return (
    <>
      {!direct && (grants.data?.length ?? 0) > 0 && (
        <Card title={t("exams.givenGroups")}>
          <ul className="divide-y divide-slate-100 text-sm">
            {grants.data!.map((g) => <li key={g.group} className="flex flex-wrap justify-between gap-2 py-2"><span className="font-medium">{g.name}</span><span className="text-slate-500">{t("exams.assignedOf", { n: g.assigned, total: g.students })}</span></li>)}
          </ul>
        </Card>
      )}
      <Card title={t(direct ? "exams.assignToStudents" : "exams.assign")}>
        <p className="mb-4 text-xs text-slate-500">{direct ? t("exams.assignToStudentsHint", { level: exam.level_code }) : t("exams.assignHint", { level: exam.level_code })}</p>
        <div className={`grid gap-6 ${direct ? "" : "lg:grid-cols-2"}`}>
          {!direct && <div>
            <h4 className="mb-2 text-sm font-medium">{t("nav.groups")}</h4>
            <div className="space-y-1">{groups.items.length === 0 && <EmptyState />}{groups.items.map((g) => <Checkbox key={g.id} label={`${g.name} (${g.level_code}, ${g.student_count} ${t("nav.students").toLowerCase()})`} disabled={g.student_count === 0} checked={pickedGroups.includes(g.id)} onChange={() => setPickedGroups((p) => p.includes(g.id) ? p.filter((i) => i !== g.id) : [...p, g.id])} />)}</div>
          </div>}
          <div>
            <h4 className="mb-2 text-sm font-medium">{t("nav.students")}</h4>
            {!exam.can_edit && groups.items.length > 1 && (
              <Select aria-label={t("exams.studentsOfGroup")} className="mb-2" value={studentGroup} onChange={(e) => setOfGroup(e.target.value)}>
                {groups.items.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
              </Select>
            )}
            <SearchInput value={search} onChange={setSearch} />
            <ul className="mt-2 divide-y divide-slate-100 text-sm">
              {students.data?.results.map((s) => (
                <li key={s.id} className="flex items-center justify-between gap-2 py-1.5">
                  <Checkbox label={`${s.full_name} · ${s.phone}`} disabled={!fits(s)} checked={pickedStudents.some((x) => x.id === s.id)} onChange={() => setPickedStudents((p) => p.some((x) => x.id === s.id) ? p.filter((x) => x.id !== s.id) : [...p, s])} />
                  <Badge tone={fits(s) ? "green" : "gray"}>{levelOf(s) ?? "—"}</Badge>
                </li>
              ))}
            </ul>
            {pickedStudents.length > 0 && <div className="mt-2 flex flex-wrap gap-1">{pickedStudents.map((s) => <Badge key={s.id} tone="indigo">{s.full_name}</Badge>)}</div>}
          </div>
        </div>
        <div className="mt-6 grid gap-4 sm:grid-cols-3">
          <Select label={t("exams.variant")} value={variant} onChange={(e) => setVariant(e.target.value)}><option value="">{t("exams.randomVariant")}</option>{variants.data?.filter((v) => v.question_count).map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}</Select>
          <Input label={t("exam.availableFrom")} type="datetime-local" value={from} onChange={(e) => setFrom(e.target.value)} />
          <Input label={t("exam.availableUntil")} type="datetime-local" value={until} onChange={(e) => setUntil(e.target.value)} />
        </div>
        <Button className="mt-4" loading={busy} disabled={!pickedStudents.length && (direct || !pickedGroups.length)} onClick={submit}>{t("exams.assign")}</Button>
        {report && (
          <div className={`mt-4 rounded-xl border p-4 text-sm ${report.created ? "border-emerald-200 bg-emerald-50 text-emerald-900" : "border-amber-200 bg-amber-50 text-amber-900"}`} role="status">
            <p className="font-semibold">{t("exams.reportCreated", { n: report.created })}{report.skipped_existing > 0 && ` · ${t("exams.reportExisting", { n: report.skipped_existing })}`}</p>
            {report.skipped_level_mismatch.length > 0 && (
              <>
                <p className="mt-2">{t("exams.reportMismatch", { level: exam.level_code })}</p>
                <ul className="mt-1 list-disc pl-5">{report.skipped_level_mismatch.map((m, i) => <li key={i}>{m.name} — {m.level ?? t("exams.noLevel")}</li>)}</ul>
              </>
            )}
          </div>
        )}
      </Card>
    </>
  );
}

/** Who has the exam: the variant can still be changed / the assignment removed until the student starts. */
function AssignmentList({ exam }: { exam: Exam }) {
  const { t } = useTranslation();
  const notify = useNotify();
  const qc = useQueryClient();
  const variants = useGet<Variant[]>("variants", { examination: exam.id });
  const [page, setPage] = useState(1);
  const assignments = useList<Assignment>("assignments", { examination: exam.id, page });
  const patchVariant = async (a: Assignment, v: string) => { try { await api.patch(`/assignments/${a.id}/`, { variant: Number(v) }); void qc.invalidateQueries({ queryKey: ["assignments"] }); notify.ok("common.saved"); } catch (e) { notify.fail(e); } };
  const removeAssignment = async (a: Assignment) => { try { await api.delete(`/assignments/${a.id}/`); void qc.invalidateQueries({ queryKey: ["assignments"] }); } catch (e) { notify.fail(e); } };
  return (
    <div className="space-y-3">
      <h3 className="text-sm font-semibold text-slate-700">{t("exams.studentsAssignedTitle")}</h3>
      <Table head={[t("common.student"), t("exams.variant"), t("nav.groups"), t("exams.window"), t("result.status"), ""]} empty={!assignments.data?.results.length}>
        {assignments.data?.results.map((a) => (
          <tr key={a.id}>
            <Td className="font-medium">{a.student_name}</Td>
            <Td>{a.attempt_id ? a.variant_name : <select value={a.variant} onChange={(e) => patchVariant(a, e.target.value)} className="rounded border border-slate-300 px-2 py-1 text-sm">{variants.data?.filter((v) => v.question_count).map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}</select>}</Td>
            <Td>{a.group_name ?? "—"}</Td>
            <Td className="whitespace-nowrap text-xs">{a.available_from || a.available_until ? `${fmtDate(a.available_from)} → ${fmtDate(a.available_until)}` : "—"}</Td>
            <Td><StateBadge state={a.state} /></Td>
            <Td className="text-right">{!a.attempt_id && <Button size="sm" variant="ghost" onClick={() => removeAssignment(a)}>{t("common.remove")}</Button>}</Td>
          </tr>
        ))}
      </Table>
      {(assignments.data?.count ?? 0) > 20 && <div className="flex justify-end gap-2"><Button size="sm" variant="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>{t("common.previous")}</Button><Button size="sm" variant="secondary" disabled={!assignments.data?.next} onClick={() => setPage(page + 1)}>{t("common.next")}</Button></div>}
    </div>
  );
}

/* ------------------------------------------------------------------ stats */
interface Stats {
  attempts: number; completed: number; decided: number; passed: number; failed: number; awaiting: number; avg_score: number | null; avg_max: number | null;
  distribution: { range: string; count: number }[]; sections: { section: string; score: number; max: number }[]; questions: { question_id: number; text: string; answered: number; correct: number }[];
}
function StatsTab({ exam }: { exam: Exam }) {
  const { t } = useTranslation();
  const s = useGet<Stats>(`analytics/examinations/${exam.id}`);
  if (!s.data) return <PageLoader />;
  const d = s.data;
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label={t("exams.attempts")} value={d.attempts} />
        <StatCard label={t("result.passed")} value={`${d.passed} / ${d.decided}`} hint={d.awaiting ? t("stats.awaitingShort", { n: d.awaiting }) : undefined} />
        <StatCard label={t("result.failed")} value={d.failed} />
        <StatCard label={t("results.average")} value={d.avg_score === null ? "—" : `${num(d.avg_score)} / ${num(d.avg_max!)} ${t("exam.points")}`} />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title={t("exams.distribution")}>{d.distribution.length ? <BarList rows={d.distribution.map((x) => ({ label: `${x.range} ${t("exam.points")}`, value: x.count }))} /> : <EmptyState />}</Card>
        <Card title={t("result.sections")}>{d.sections.length ? <BarList rows={d.sections.map((x) => ({ label: t(`sections.${x.section}`), value: x.score, text: `${num(x.score)} / ${num(x.max)} ${t("exam.points")}`, share: x.max ? x.score / x.max : 0, tone: "amber" }))} /> : <EmptyState />}</Card>
      </div>
      <Card title={t("exams.questionDifficulty")}>
        {d.questions.length === 0 ? <EmptyState /> : <ul className="divide-y divide-slate-100 text-sm">{d.questions.map((q) => <li key={q.question_id} className="flex justify-between gap-4 py-2"><span className="line-clamp-1">{q.text}</span><span className="shrink-0 font-medium tabular-nums">{t("exams.correctOf", { n: q.correct, total: q.answered })}</span></li>)}</ul>}
      </Card>
    </div>
  );
}

export default function ExamEditorPage() {
  const { id } = useParams();
  const { t } = useTranslation();
  const { user } = useAuth();
  const notify = useNotify();
  const qc = useQueryClient();
  const [tab, setTab] = useState<"settings" | "variants" | "assign" | "results" | "stats">("variants");
  const nav = useNavigate();
  const [confirmDel, setConfirmDel] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const q = useQuery({ queryKey: ["examinations", id], queryFn: async () => (await api.get<Exam>(`/examinations/${id}/`)).data });
  const readOnly = q.data ? !q.data.can_edit : false;
  useEffect(() => { if (readOnly) setTab("assign"); }, [readOnly]);  // a teacher with a group-given exam comes here to assign it
  if (q.isError) return <LoadError />;
  if (!q.data) return <PageLoader />;
  const exam = q.data;
  const canAssign = exam.kind === "UPGRADE" || user!.role === "ADMIN";
  const editable = exam.can_edit;  // false: a teacher who got the exam through a group only assigns it

  const toggle = async () => {
    try { await api.post(`/examinations/${exam.id}/${exam.status === "PUBLISHED" ? "unpublish" : "publish"}/`); notify.ok(exam.status === "PUBLISHED" ? "exams.unpublished" : "exams.published"); void qc.invalidateQueries({ queryKey: ["examinations"] }); } catch (e) { notify.fail(e); }
  };

  // only an exam nobody has taken yet can be deleted (the server refuses the rest too)
  const remove = async () => {
    setDeleting(true);
    try {
      await api.delete(`/examinations/${exam.id}/`);
      notify.ok("common.deleted");
      void qc.invalidateQueries({ queryKey: ["examinations"] });
      nav("/exams", { replace: true });
    } catch (e) { notify.fail(e); setDeleting(false); setConfirmDel(false); }
  };

  const items = [{ value: "variants" as const, label: t("exams.variants") }, ...(editable ? [{ value: "settings" as const, label: t("exams.settings") }] : []),
    ...(canAssign && exam.kind === "UPGRADE" ? [{ value: "assign" as const, label: user!.role === "ADMIN" ? t("exams.giveOrAssign") : t("exams.assign") }] : []), { value: "results" as const, label: t("exams.resultsTab") }, { value: "stats" as const, label: t("exams.statistics") }];

  return (
    <>
      <PageHeader title={exam.title} subtitle={`${exam.level_code}${exam.target_level_code ? ` → ${exam.target_level_code}` : ""} · ${exam.duration_minutes} ${t("common.minutes")}`}
        actions={<><KindBadge kind={exam.kind} /><Badge tone={exam.status === "PUBLISHED" ? "green" : "gray"}>{t(`examStatus.${exam.status}`)}</Badge>
          {editable && <Button variant={exam.status === "PUBLISHED" ? "secondary" : "success"} onClick={toggle}>{exam.status === "PUBLISHED" ? t("exams.unpublish") : t("exams.publish")}</Button>}
          {editable && !exam.locked && <Button variant="danger" onClick={() => setConfirmDel(true)}>{t("common.delete")}</Button>}</>} />
      {!editable && <p className="mb-4 rounded-xl border border-sky-200 bg-sky-50 p-3 text-sm text-sky-900">{t("exams.readOnlyNotice")}</p>}
      <Tabs value={tab} onChange={setTab} items={items} />
      {tab === "settings" && <SettingsTab exam={exam} />}
      {tab === "variants" && <VariantsTab exam={exam} />}
      {tab === "assign" && <AssignTab exam={exam} />}
      {tab === "results" && <ResultsTab exam={exam} />}
      {tab === "stats" && <StatsTab exam={exam} />}
      <ConfirmDialog open={confirmDel} danger loading={deleting} title={t("common.delete")} confirmLabel={t("common.delete")}
        message={t("exams.deleteConfirm", { name: exam.title })} onConfirm={remove} onClose={() => setConfirmDel(false)} />
    </>
  );
}
