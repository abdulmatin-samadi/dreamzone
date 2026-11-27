import type { AxiosInstance } from "axios";
import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { parseError } from "../api/client";
import type { Answer, AttemptPayload, AttemptQuestion } from "../api/types";
import { ThemeToggle } from "./ThemeToggle";
import { useNotify } from "./Toast";
import { Button, Modal, PageLoader, ProgressBar, cx } from "./ui";

const isAnswered = (q: AttemptQuestion, a?: Answer | null) => {
  if (!a) return false;
  if (q.type === "FILL" || q.type === "WRITING") return !!a.text?.trim();
  if (q.type === "MATCH") return Object.values(a.pairs ?? {}).some(Boolean);
  return !!a.option_ids?.length;
};

/* ------------------------------------------------------------------ page model */
interface Page { key: string; qs: AttemptQuestion[]; numbers: number[]; passage: AttemptQuestion["passage"] }
const MAX_GROUP = 10;

/** Questions sharing a reading text are shown together (text left, questions right); consecutive
 * questions of the same exercise type are shown as one numbered group ("Questions 10-14"). */
function buildPages(questions: AttemptQuestion[]): Page[] {
  const pages: Page[] = [];
  questions.forEach((q, i) => {
    const last = pages[pages.length - 1];
    const lastQ = last?.qs[last.qs.length - 1];
    const samePassage = !!q.passage?.id && lastQ?.passage?.id === q.passage.id;
    const sameGroup = !q.passage && !lastQ?.passage && !!q.category && lastQ?.category === q.category && lastQ?.instruction === q.instruction && last.qs.length < MAX_GROUP;
    if (last && (samePassage || sameGroup)) { last.qs.push(q); last.numbers.push(i + 1); }
    else pages.push({ key: String(q.id), qs: [q], numbers: [i + 1], passage: q.passage });
  });
  return pages;
}

const FONT = ["text-xl", "text-2xl", "text-3xl"];  // questions are read on a big screen: start large, A+ goes larger
const BLANK = /_{2,}|\.{4,}/;  // a blank inside a sentence: the answer box goes right there

/* ------------------------------------------------------------------ inputs */
/** Answers get no help from the browser, the phone keyboard or extensions: no red spelling lines,
 * no autocorrect, no word suggestions, no automatic capitals, no grammar checkers. */
const NO_ASSIST = {
  spellCheck: false, autoCorrect: "off", autoCapitalize: "off", autoComplete: "off",
  "data-gramm": "false", "data-gramm_editor": "false", "data-enable-grammarly": "false",
  writingsuggestions: "false",
} as const;

function FillBox({ value, onChange, className, placeholder }: { value: string; onChange: (v: string) => void; className?: string; placeholder?: string }) {
  const { t } = useTranslation();
  return (
    <input value={value} maxLength={500} onChange={(e) => onChange(e.target.value)} placeholder={placeholder ?? (t("exam.typeAnswer") as string)} {...NO_ASSIST}
      className={cx("rounded-xl border-2 border-sky-300 bg-white px-3 py-2 text-[1em] text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200", className)} />
  );
}

function QuestionInput({ q, answer, onChange }: { q: AttemptQuestion; answer: Answer | undefined; onChange: (a: Answer) => void }) {
  const { t } = useTranslation();
  if (q.type === "WRITING") {
    const text = answer?.text ?? "";
    const words = text.trim() ? text.trim().split(/\s+/).length : 0;
    return (
      <div>
        <textarea value={text} onChange={(e) => onChange({ text: e.target.value })} rows={q.points <= 2 ? 3 : 12} maxLength={10000} {...NO_ASSIST} placeholder={t("exam.writeHere") as string}
          className="w-full rounded-xl border-2 border-sky-300 bg-white p-4 text-base leading-7 text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200" />
        <p className="mt-1 text-right text-sm text-slate-500">{t("exam.wordCount", { n: words })}</p>
      </div>
    );
  }
  if (q.type === "FILL") return <FillBox value={answer?.text ?? ""} onChange={(v) => onChange({ text: v })} className={q.category === "READQA" || q.category === "MISTAKE" ? "w-full max-w-2xl" : "w-full sm:w-80"} />;
  if (q.type === "MATCH") {
    return (
      <ul className="space-y-3">
        {q.options.map((o) => (
          <li key={o.id} className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <span className="min-w-0 flex-1 rounded-lg bg-white px-3 py-2 text-sm font-medium shadow-sm">{o.text}</span>
            <select value={answer?.pairs?.[String(o.id)] ?? ""} className="flex-1 rounded-xl border-2 border-sky-300 bg-white px-3 py-2 text-sm"
              onChange={(e) => onChange({ pairs: { ...(answer?.pairs ?? {}), [String(o.id)]: e.target.value } })}>
              <option value="">{t("exam.chooseMatch")}</option>
              {q.choices?.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </li>
        ))}
      </ul>
    );
  }
  const multi = q.type === "MSQ";
  const selected = answer?.option_ids ?? [];
  const toggle = (id: number, on: boolean) => onChange({ option_ids: multi ? (on ? selected.filter((i) => i !== id) : [...selected, id]) : [id] });
  // Buttons only for true/false-like answers and one-word "odd one out" rows; sentences are always a list,
  // so every question of a group looks the same.
  const isTfWords = q.options.length > 0 && q.options.every((o) => /^(true|false|not given|no information|yes|no)$/i.test(o.text.trim()));
  const chips = !multi && q.options.length <= 8 && (isTfWords || q.category === "ODD" || q.type === "TF");

  if (chips) {  // TRUE / FALSE / NO INFORMATION, A / B ...
    return (
      <div className="flex flex-wrap gap-2" role="radiogroup">
        {q.options.map((o) => {
          const on = selected.includes(o.id);
          return (
            <button key={o.id} type="button" role="radio" aria-checked={on} onClick={() => toggle(o.id, on)}
              className={cx("rounded-xl border-2 px-5 py-2.5 text-sm font-bold tracking-wide transition", isTfWords && "uppercase",
                on ? "border-blue-600 bg-blue-600 text-on-accent shadow" : "border-slate-300 bg-white text-slate-800 hover:border-blue-400 hover:bg-sky-50")}>
              {o.text}
            </button>
          );
        })}
      </div>
    );
  }
  return (
    <ul className="space-y-2" role={multi ? "group" : "radiogroup"}>
      {multi && <li className="text-xs text-slate-500">{t("exam.selectAll")}</li>}
      {q.options.map((o) => {
        const on = selected.includes(o.id);
        return (
          <li key={o.id}>
            <label className={cx("flex cursor-pointer items-start gap-3 rounded-xl border-2 px-4 py-3 text-[0.95em] transition-colors", on ? "border-blue-500 bg-white shadow-sm" : "border-transparent bg-white/70 hover:bg-white")}>
              <input type={multi ? "checkbox" : "radio"} name={`q-${q.id}`} checked={on} className="mt-1 h-5 w-5 shrink-0 text-blue-600" onChange={() => toggle(o.id, on)} />
              <span>{o.text}</span>
            </label>
          </li>
        );
      })}
    </ul>
  );
}

/** Reading text. ``[[n]]`` markers become numbered input boxes inside the paragraph. */
function PassagePanel({ passage, gaps, numberOf, answers, onFill, fontClass }: {
  passage: NonNullable<AttemptQuestion["passage"]>; gaps: Map<number, AttemptQuestion>; numberOf: (q: AttemptQuestion) => number;
  answers: Record<number, Answer>; onFill: (q: AttemptQuestion, v: string) => void; fontClass: string;
}) {
  // a short first paragraph ("SLEEP AND MEMORY") is the heading of the text
  const [head, ...rest] = passage.text.split("\n\n");
  const heading = rest.length && head.length <= 70 && (!/[.!?:]$/.test(head) || !/[a-z]/.test(head)) ? head : "";  // an ALL-CAPS title may end with "?"
  const body = heading ? rest.join("\n\n") : passage.text;
  const renderLine = (line: string, li: number) => {
    if (/^[A-Z][A-Z\s'\u2019,.-]{2,60}$/.test(line) && (line.match(/[A-Z]/g) ?? []).length >= 3) return <h3 key={li} className="mb-1 mt-3 text-sm font-extrabold uppercase tracking-widest text-blue-700">{line}</h3>;
    const sp = line.match(/^([A-Z][A-Za-z]{0,10}):\s+(.*)$/);  // "Freya: ..." -> bold speaker
    const content = sp ? sp[2] : line;
    const parts = content.split(/\[\[(\d+)\]\]/);
    return (
      <p key={li} className={cx("leading-[2.1] text-slate-800", sp && "mb-1")}>
        {sp && <b className="mr-2 text-blue-700">{sp[1]}:</b>}
        {parts.map((part, i) => {
          if (i % 2 === 0) return <Fragment key={i}>{part}</Fragment>;
          const q = gaps.get(Number(part));
          if (!q) return <span key={i} className="rounded bg-slate-200 px-2">…</span>;
          return (
            <span key={i} className="mx-1 inline-flex items-center gap-1.5 align-middle">
              <span className="flex h-6 min-w-6 items-center justify-center rounded-md bg-blue-600 px-1 text-xs font-bold text-on-accent">{numberOf(q)}</span>
              <FillBox value={answers[q.id]?.text ?? ""} onChange={(v) => onFill(q, v)} className="w-44 py-1.5" placeholder="…" />
            </span>
          );
        })}
      </p>
    );
  };
  return (
    <article className={cx("rounded-2xl border border-amber-100 bg-amber-50/40 p-6 shadow-sm sm:p-8", fontClass)}>
      {heading && <h2 className="mb-4 text-center text-[1.35em] font-extrabold uppercase tracking-wide text-slate-900">{heading}</h2>}
      {body.split("\n\n").map((para, pi) => (
        <div key={pi} className={pi > 0 ? "mt-4" : ""}>{para.split("\n").map(renderLine)}</div>
      ))}
    </article>
  );
}

/* ------------------------------------------------------------------ runner */
export const fullscreenSupported = () => {
  const el = document.documentElement as HTMLElement & { webkitRequestFullscreen?: () => void };
  return !!(el.requestFullscreen || el.webkitRequestFullscreen);
};
export const inFullscreen = () => !!(document.fullscreenElement || (document as Document & { webkitFullscreenElement?: Element }).webkitFullscreenElement);
export async function enterFullscreen(): Promise<boolean> {
  const el = document.documentElement as HTMLElement & { webkitRequestFullscreen?: () => void };
  try { if (el.requestFullscreen) await el.requestFullscreen(); else el.webkitRequestFullscreen?.(); } catch { /* refused: the runner shows the return overlay */ }
  lockEscape();
  return inFullscreen();
}
/** Chrome/Edge: with the keyboard locked a short Esc press no longer leaves fullscreen (holding it for ~2 s still does). */
function lockEscape() {
  const kb = (navigator as Navigator & { keyboard?: { lock?: (keys: string[]) => Promise<void> } }).keyboard;
  if (inFullscreen()) void kb?.lock?.(["Escape"]).catch(() => undefined);
}
async function leaveFullscreen() {
  try { if (inFullscreen()) await document.exitFullscreen(); } catch { /* already out */ }
}

export function ExamRunner({ api, attemptId, onFinished, onStopped }: { api: AxiosInstance; attemptId: number; onFinished: (resultId: number) => void; onStopped: () => void }) {
  const { t } = useTranslation();
  const notify = useNotify();
  const [data, setData] = useState<AttemptPayload | null>(null);
  const [answers, setAnswers] = useState<Record<number, Answer>>({});
  const [pageIdx, setPageIdx] = useState(0);
  const [font, setFont] = useState(0);
  const [offset, setOffset] = useState(0);
  const [now, setNow] = useState(Date.now());
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [confirm, setConfirm] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const dirty = useRef<Set<number>>(new Set());
  const answersRef = useRef(answers);
  const submittingRef = useRef(false);
  answersRef.current = answers;
  const scrollRef = useRef<HTMLDivElement>(null);
  const toTop = () => scrollRef.current?.scrollTo({ top: 0, behavior: "smooth" });

  // ---- fullscreen exam mode. The browser only reports; the server owns the 10 s deadline and the termination.
  const [refused, setRefused] = useState(false);   // this device refused fullscreen: fall back to the visibility/focus rule
  const refusedRef = useRef(false);
  const supported = fullscreenSupported() && !refused;
  const limit = useRef(10);
  const [violationEnd, setViolationEnd] = useState<number | null>(null);
  const [left, setLeft] = useState(0);
  const endedRef = useRef(false);
  const [otherDevice, setOtherDevice] = useState(false);  // the test is open on another device: one test = one device
  const blockOtherDevice = (e: unknown) => {
    if (parseError(e).code !== "attempt_other_device") return false;
    endedRef.current = true; setOtherDevice(true); void leaveFullscreen();
    return true;
  };
  const mountedRef = useRef(false);
  const violationRef = useRef<number | null>(null);
  violationRef.current = violationEnd;

  const report = useCallback(async (ok: boolean, reason: string) => {
    if (endedRef.current) return;
    try {
      const { data: r } = await api.post<{ status: string; violation_seconds_left: number | null; result_id: number | null }>(`/attempts/${attemptId}/fullscreen/`, { ok, reason });
      if (endedRef.current) return;
      if (r.status === "PENDING_TEACHER_APPROVAL") { endedRef.current = true; onStopped(); return; }
      if (r.status !== "IN_PROGRESS" && r.result_id) { endedRef.current = true; onFinished(r.result_id); return; }
      setViolationEnd(r.violation_seconds_left == null ? null : Date.now() + r.violation_seconds_left * 1000);
    } catch (e) { blockOtherDevice(e); /* offline: the local countdown keeps running, the server decides anyway */ }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, attemptId]);

  const check = useCallback(() => {
    if (endedRef.current) return;
    // Without a Fullscreen API (iPhone) the test must at least stay visible and focused.
    // "Not focused" also catches a second app in split view or a floating window.
    const hidden = document.hidden, fs = !supported || refusedRef.current || inFullscreen(), focused = document.hasFocus();
    if (inFullscreen()) lockEscape();
    const ok = fs && !hidden && focused;
    if (!ok && violationRef.current == null) setViolationEnd(Date.now() + limit.current * 1000);
    void report(ok, hidden ? "hidden" : !focused ? "blur" : "fullscreen");
  }, [supported, report]);

  useEffect(() => {
    const ev = ["fullscreenchange", "webkitfullscreenchange", "visibilitychange"];
    ev.forEach((e) => document.addEventListener(e, check));
    window.addEventListener("blur", check);
    window.addEventListener("focus", check);
    const hb = setInterval(check, 5000);
    return () => { ev.forEach((e) => document.removeEventListener(e, check)); window.removeEventListener("blur", check); window.removeEventListener("focus", check); clearInterval(hb); };
  }, [check]);

  // when the countdown reaches zero keep asking the server until it confirms the termination
  useEffect(() => {
    if (violationEnd == null) return;
    const h = setInterval(() => {
      const s = Math.max(0, Math.ceil((violationEnd - Date.now()) / 1000));
      setLeft(s);
      if (s === 0) check();
    }, 250);
    setLeft(Math.max(0, Math.ceil((violationEnd - Date.now()) / 1000)));
    return () => clearInterval(h);
  }, [violationEnd, check]);

  // leave fullscreen again when the exam screen goes away; block the browser "back" button
  useEffect(() => {
    endedRef.current = false;   // (React StrictMode runs the cleanup once right after mounting)
    history.pushState(null, "", location.href);
    const back = () => history.pushState(null, "", location.href);
    window.addEventListener("popstate", back);
    mountedRef.current = true;
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") e.preventDefault(); };
    window.addEventListener("keydown", esc);
    return () => {
      endedRef.current = true; mountedRef.current = false; window.removeEventListener("popstate", back); window.removeEventListener("keydown", esc);
      (navigator as Navigator & { keyboard?: { unlock?: () => void } }).keyboard?.unlock?.();
      // StrictMode unmounts and remounts at once: only leave fullscreen when the exam screen is really gone
      setTimeout(() => { if (!mountedRef.current) void leaveFullscreen(); }, 100);
    };
  }, []);

  const tryFullscreen = async () => {
    if (!fullscreenSupported() || refusedRef.current) return;
    if (!(await enterFullscreen())) { refusedRef.current = true; setRefused(true); }
  };
  const returnToFullscreen = async () => { await tryFullscreen(); setTimeout(check, 150); };

  // ---- load (also used after a refresh: same attempt, remaining time computed on the server)
  useEffect(() => {
    api.get<AttemptPayload>(`/attempts/${attemptId}/`).then(({ data }) => {
      if (data.status === "PENDING_TEACHER_APPROVAL") { endedRef.current = true; return onStopped(); }
      if (data.status !== "IN_PROGRESS" && data.result_id) return onFinished(data.result_id);
      limit.current = data.violation_limit_seconds ?? 10;
      if (data.violation_seconds_left != null) setViolationEnd(Date.now() + data.violation_seconds_left * 1000);
      setData(data);
      setOffset(new Date(data.server_now).getTime() - Date.now());
      setAnswers(Object.fromEntries(data.questions.filter((q) => q.answer).map((q) => [q.id, q.answer as Answer])));
    }).catch((e) => { if (!blockOtherDevice(e)) notify.fail(e); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, attemptId]);

  useEffect(() => { const h = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(h); }, []);
  // first check once the exam is on screen (a page refresh always drops fullscreen)
  const dataReady = !!data;
  useEffect(() => {
    if (!dataReady) return;
    // the click that opened the exam may still allow fullscreen (reception, page reload fallback)
    void (supported && !inFullscreen() ? tryFullscreen() : Promise.resolve()).then(check);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataReady, check, supported]);

  const flush = useCallback(async () => {
    const ids = [...dirty.current];
    if (!ids.length || submittingRef.current) return;
    dirty.current = new Set();
    setSaveState("saving");
    try {
      await api.put(`/attempts/${attemptId}/answers/`, { answers: ids.map((id) => ({ question_id: id, answer: answersRef.current[id] })) });
      setSaveState(dirty.current.size ? "saving" : "saved");
    } catch (e) {
      ids.forEach((i) => dirty.current.add(i));
      setSaveState("error");
      const code = parseError(e).code;
      if (blockOtherDevice(e)) return;
      if (code === "time_expired" || code === "attempt_already_finished") void finish(true);
      if (code === "attempt_pending_approval" && !endedRef.current) { endedRef.current = true; onStopped(); }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, attemptId]);

  // debounced autosave + periodic retry
  useEffect(() => { if (dirty.current.size) { const h = setTimeout(flush, 700); return () => clearTimeout(h); } }, [answers, flush]);
  useEffect(() => { const h = setInterval(flush, 8000); return () => clearInterval(h); }, [flush]);

  const finish = useCallback(async (auto = false) => {
    if (submittingRef.current) return;
    submittingRef.current = true;
    setSubmitting(true);
    try {
      const payload = Object.entries(answersRef.current).map(([id, answer]) => ({ question_id: Number(id), answer }));
      const { data: r } = await api.post<{ result_id: number }>(`/attempts/${attemptId}/submit/`, payload.length ? { answers: payload } : {});
      endedRef.current = true;
      onFinished(r.result_id);
    } catch (e) {
      submittingRef.current = false;
      setSubmitting(false);
      if (blockOtherDevice(e)) return;
      notify.fail(e);
      if (auto) setTimeout(() => void finish(true), 3000); // keep trying: the server also auto-submits on its own
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, attemptId, onFinished]);

  const remaining = data ? Math.max(0, Math.floor((new Date(data.deadline_at).getTime() - (now + offset)) / 1000)) : 0;
  useEffect(() => { if (data && remaining === 0) void finish(true); }, [data, remaining, finish]);

  useEffect(() => {
    const h = (e: BeforeUnloadEvent) => { if (!submittingRef.current) { e.preventDefault(); e.returnValue = ""; } };
    window.addEventListener("beforeunload", h);
    return () => window.removeEventListener("beforeunload", h);
  }, []);

  if (otherDevice) return (
    <div className="flex min-h-full items-center justify-center p-6">
      <div className="max-w-md rounded-2xl border border-amber-300 bg-white p-8 text-center shadow-lg">
        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-amber-100 text-3xl">🔒</div>
        <h1 className="text-xl font-bold text-slate-900">{t("exam.otherDeviceTitle")}</h1>
        <p className="mt-2 text-sm text-slate-600">{t("errors.attempt_other_device")}</p>
        <Button className="mt-6" variant="secondary" onClick={() => location.reload()}>{t("exam.tryAgain")}</Button>
      </div>
    </div>
  );
  if (!data) return <PageLoader />;
  const pages = buildPages(data.questions);
  const page = pages[Math.min(pageIdx, pages.length - 1)];
  const numberOf = (q: AttemptQuestion) => data.questions.findIndex((x) => x.id === q.id) + 1;
  const answeredCount = data.questions.filter((x) => isAnswered(x, answers[x.id])).length;
  const unanswered = data.questions.length - answeredCount;
  const mm = String(Math.floor(remaining / 60)).padStart(2, "0"), ss = String(remaining % 60).padStart(2, "0");
  const total = data.duration_minutes * 60;

  const setAnswerFor = (qid: number, a: Answer) => {
    dirty.current.add(qid);
    setAnswers((s) => ({ ...s, [qid]: a }));
  };

  // gaps written inside the passage vs. questions listed next to it
  const passageAudio = page.passage?.audio ?? null;
  const audioOnly = !!page.passage && !page.passage.text.trim();   // listening exercise: the passage is just the audio track
  const gapQs = new Map<number, AttemptQuestion>();
  if (page.passage) page.qs.forEach((q) => { if (q.gap_no && page.passage!.text.includes(`[[${q.gap_no}]]`)) gapQs.set(q.gap_no, q); });
  const listed = page.qs.filter((q) => !(q.gap_no && gapQs.get(q.gap_no) === q));
  const first = page.numbers[0], last = page.numbers[page.numbers.length - 1];
  const cat = page.qs[0].category;
  const heading = page.qs[0].instruction ? page.qs[0].instruction
    : cat === "TFREAD" && page.qs[0].options.length
    ? page.qs[0].options.map((o) => o.text[0] + o.text.slice(1).toLowerCase()).join(" / ")
    : cat ? (t(`exGroups.${cat}`) as string) : (t(`sections.${page.qs[0].section}`) as string);
  const fontClass = FONT[font];

  return (
    <div ref={scrollRef} className="fixed inset-0 z-[60] overflow-y-auto overscroll-contain bg-slate-50">
    <div className="mx-auto max-w-[96rem] p-4 pb-40 sm:p-6 sm:pb-32">
      <header className="sticky top-0 z-20 -mx-4 mb-5 border-b border-slate-200 bg-white/95 px-4 py-3 backdrop-blur sm:-mx-6 sm:px-6">
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0 flex-1">
            <h1 className="truncate text-lg font-semibold">{data.examination}</h1>
            <p className="text-xs text-slate-500">{t("exam.answered", { n: answeredCount, total: data.questions.length })} ·{" "}
              <span className={saveState === "error" ? "text-red-600" : ""}>{t(`exam.save.${saveState}`)}</span></p>
          </div>
          <ThemeToggle className="border border-slate-200 text-slate-600 hover:bg-slate-100" />
          <div className={cx("shrink-0 rounded-lg px-3 py-1.5 font-mono text-lg font-semibold tabular-nums sm:text-xl", remaining < 300 ? "bg-red-100 text-red-700" : "bg-slate-100 text-slate-800")} aria-label={t("exam.timeLeft")}>{mm}:{ss}</div>
        </div>
        <ProgressBar className="mt-3" value={(remaining / total) * 100} tone={remaining < 300 ? "red" : "indigo"} />
      </header>

      {listed.length === 0 && (
        <h2 className="mb-4 border-b-2 border-sky-200 pb-2 text-xl font-bold text-slate-900">
          {first === last ? t("exam.questionHeading", { n: first, title: heading }) : t("exam.questionsHeading", { a: first, b: last, title: heading })}
        </h2>
      )}
      {passageAudio && (
        <div className="sticky top-24 z-10 mb-4 rounded-2xl border border-sky-200 bg-white p-4 shadow-sm">
          <p className="mb-2 text-sm font-semibold text-blue-700">🎧 {t("exam.listen")}</p>
          <audio key={passageAudio} controls controlsList="nodownload" src={passageAudio} className="w-full" />
        </div>
      )}
      <div key={page.key} className={cx("dz-fade grid items-start gap-6", page.passage && !audioOnly && listed.length > 0 && "lg:grid-cols-2")}>
        {page.passage && !audioOnly && (
          <div className={cx(listed.length > 0 && "lg:sticky lg:top-28 lg:max-h-[calc(100vh-9rem)] lg:overflow-y-auto lg:rounded-2xl")}>
            <PassagePanel passage={page.passage} gaps={gapQs} numberOf={numberOf} answers={answers} fontClass={fontClass}
              onFill={(q, v) => setAnswerFor(q.id, { text: v })} />
          </div>
        )}

        {listed.length > 0 && (
          <section className={fontClass}>
            <h2 className="mb-4 border-b-2 border-sky-200 pb-2 text-xl font-bold text-slate-900">
              {first === last ? t("exam.questionHeading", { n: first, title: heading }) : t("exam.questionsHeading", { a: first, b: last, title: heading })}
            </h2>
            <div className="space-y-4">
              {listed.map((q) => (
                <div key={q.id} className={cx("rounded-2xl bg-sky-50 p-5 shadow-sm ring-1 ring-sky-100 sm:p-10", listed.length === 1 && "flex min-h-[45vh] flex-col justify-center")}>
                  {q.type === "FILL" && BLANK.test(q.text) ? (
                    <div className="flex gap-3">
                      <span className="mt-2 flex h-6 min-w-6 shrink-0 items-center justify-center rounded-md bg-blue-100 px-1 text-xs font-bold text-blue-700">{numberOf(q)}</span>
                      <p className="font-semibold leading-[2.6] text-slate-900">
                        {(() => {
                          const [before, ...after] = q.text.split(BLANK);
                          return (<>
                            {before}
                            <FillBox value={answers[q.id]?.text ?? ""} onChange={(v) => setAnswerFor(q.id, { text: v })} className="mx-2 w-64 max-w-full py-1.5 align-middle font-normal" placeholder="…" />
                            {after.join(" ")}
                          </>);
                        })()}
                      </p>
                    </div>
                  ) : (
                  <div className="mb-3 flex gap-3">
                    <span className="mt-1 flex h-6 min-w-6 shrink-0 items-center justify-center rounded-md bg-blue-100 px-1 text-xs font-bold text-blue-700">{numberOf(q)}</span>
                    <p className="whitespace-pre-wrap font-semibold text-slate-900">{q.text}</p>
                  </div>)}
                  {q.audio && q.audio !== passageAudio && <audio key={q.audio} controls controlsList="nodownload" src={q.audio} className="mb-3 w-full" />}
                  {q.image && <img src={q.image} alt="" className="mb-3 max-h-64 rounded-lg" />}
                  {!(q.type === "FILL" && BLANK.test(q.text)) && (
                    <div className="pl-0 sm:pl-9"><QuestionInput q={q} answer={answers[q.id]} onChange={(a) => setAnswerFor(q.id, a)} /></div>)}
                </div>
              ))}
            </div>
          </section>
        )}
      </div>

      <div className="mt-6 flex items-center justify-between gap-3">
        <Button variant="secondary" disabled={pageIdx === 0} onClick={() => { setPageIdx(pageIdx - 1); toTop(); }}>{t("common.previous")}</Button>
        <span className="text-sm text-slate-500">{pageIdx + 1} / {pages.length}</span>
        <Button disabled={pageIdx >= pages.length - 1} onClick={() => { setPageIdx(pageIdx + 1); toTop(); }}>{t("common.next")}</Button>
      </div>

      {/* bottom bar: question numbers, font size and submit — always in reach, out of the questions' way */}
      <div className="fixed inset-x-0 bottom-0 z-30 border-t border-slate-200 bg-white/95 shadow-[0_-4px_16px_rgba(15,23,42,0.08)] backdrop-blur">
        <div className="mx-auto flex max-w-[96rem] items-center gap-3 px-4 py-2 sm:px-6">
          <nav className="max-h-[3.75rem] min-w-0 flex-1 overflow-y-auto py-1" aria-label={t("exam.navigator")}>
            <div className="flex flex-wrap gap-1">
              {data.questions.map((x, i) => {
                const pi = pages.findIndex((p) => p.qs.some((y) => y.id === x.id));
                return (
                  <button key={x.id} onClick={() => { setPageIdx(pi); toTop(); }} aria-label={`${i + 1}`}
                    className={cx("h-6 min-w-6 rounded px-1 text-[11px] font-semibold tabular-nums", pi === pageIdx && "ring-2 ring-blue-500 ring-offset-1",
                      isAnswered(x, answers[x.id]) ? "bg-blue-600 text-on-accent" : "bg-slate-100 text-slate-600 hover:bg-slate-200")}>{i + 1}</button>
                );
              })}
            </div>
          </nav>
          <button onClick={() => setFont((font + 1) % FONT.length)} aria-label={t("exam.fontSize")} title={t("exam.fontSize")}
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border-2 border-slate-800 bg-white text-base font-extrabold text-slate-900 hover:bg-slate-50">A+</button>
          <button onClick={() => { void flush(); setConfirm(true); }}
            className="shrink-0 rounded-xl bg-gradient-to-r from-red-500 to-red-600 px-4 py-2.5 text-sm font-bold text-on-accent shadow-lg shadow-red-300/50 transition hover:from-red-600 hover:to-[#b91c1c] focus:outline-none focus-visible:ring-4 focus-visible:ring-red-300 sm:px-6 sm:text-base">
            ✓ {t("exam.submitTest")}
          </button>
        </div>
      </div>

      <Modal open={confirm} onClose={() => setConfirm(false)} title={t("exam.submitTitle")}
        footer={<><Button variant="secondary" onClick={() => setConfirm(false)}>{t("exam.keepGoing")}</Button>
          <Button variant="success" loading={submitting} onClick={() => finish(false)}>{t("exam.submitNow")}</Button></>}>
        <p className="text-sm text-slate-600">{unanswered > 0 ? t("exam.unansweredWarn", { n: unanswered }) : t("exam.allAnswered")}</p>
        <p className="mt-2 text-sm font-medium text-red-600">{t("exam.noRetake")}</p>
      </Modal>

      {violationEnd != null && (
        <div role="alertdialog" aria-modal="true" className="fixed inset-0 z-[80] flex items-center justify-center bg-[#0b1b38]/90 p-4 backdrop-blur-sm">
          <div className="w-full max-w-lg rounded-3xl bg-white p-8 text-center shadow-2xl">
            <p className="text-sm font-bold uppercase tracking-widest text-red-600">{t("exam.fs.title")}</p>
            <div className={cx("mx-auto my-5 flex h-36 w-36 items-center justify-center rounded-full border-8 text-6xl font-extrabold tabular-nums", left <= 3 ? "animate-pulse border-red-500 text-red-600" : "border-amber-400 text-amber-600")}>{left}</div>
            <p className="text-slate-700">{t(supported ? "exam.fs.body" : "exam.fs.bodyNoFs", { n: limit.current })}</p>
            <Button size="lg" className="mt-6 w-full" onClick={returnToFullscreen}>{t(supported ? "exam.fs.return" : "exam.fs.returnNoFs")}</Button>
            <p className="mt-3 text-xs text-slate-500">{t("exam.fs.saved")}</p>
          </div>
        </div>
      )}
    </div>
    </div>
  );
}
