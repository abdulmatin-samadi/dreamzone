import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { ResultDetail, ReviewItem, WritingItem } from "../api/types";
import { ApprovalBadge, OutcomeBadge } from "./badges";
import { Badge, Button, Card, ProgressBar, Textarea, cx } from "./ui";

const fmt = (v: string | number | null) => v === null ? "—" : Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 });

function AnswerText({ v }: { v: ReviewItem["student_answer"] | ReviewItem["correct_answer"] }) {
  const { t } = useTranslation();
  if (v == null || (Array.isArray(v) && v.length === 0)) return <span className="italic text-slate-400">{t("result.noAnswer")}</span>;
  if (typeof v === "string") return <>{v}</>;
  return <>{(v as (string | { left: string; right: string })[]).map((x) => (typeof x === "string" ? x : `${x.left} → ${x.right || "—"}`)).join(" · ")}</>;
}

/** Written answers: the student sees "being checked" or the score; reception (guests) or the teacher (upgrades) types the points. */
function WritingBlock({ items, onGrade, busy, whoChecks }: { items: WritingItem[]; onGrade?: (grades: { question_id: number; points: number; feedback: string; max: number }[]) => void; busy?: boolean; whoChecks?: string }) {
  const { t } = useTranslation();
  // like speaking: the reviewer types the points and what the writing is out of; it can be corrected until the decision
  const start = () => Object.fromEntries(items.map((i) => [i.question_id, {
    points: i.points == null || i.needs_review ? "" : String(i.points), feedback: i.feedback ?? "", max: String(i.max_points) }]));
  const [vals, setVals] = useState<Record<number, { points: string; feedback: string; max: string }>>(start);
  const set = (id: number, k: "points" | "feedback" | "max", v: string) => setVals((s) => ({ ...s, [id]: { ...s[id], [k]: v } }));
  const gradable = items.filter((i) => i.text);
  const ready = gradable.filter((i) => vals[i.question_id]?.points !== "");
  const valid = ready.every((i) => { const v = vals[i.question_id]; const p = Number(v.points), m = Number(v.max); return m > 0 && p >= 0 && p <= m; });
  return (
    <Card title={`✍️ ${t("result.writing")}`}>
      <div className="space-y-5">
        {items.map((w) => {
          const v = vals[w.question_id];
          return (
            <div key={w.question_id} className="rounded-xl border border-slate-200 p-4">
              <p className="text-sm font-semibold text-slate-800">{w.prompt}</p>
              <p className="mt-3 whitespace-pre-wrap rounded-lg bg-slate-50 p-3 text-sm leading-6 text-slate-800">{w.text || <span className="italic text-slate-400">{t("result.noAnswer")}</span>}</p>
              <p className="mt-1 text-xs text-slate-500">{t("exam.wordCount", { n: w.words })}</p>
              <div className="mt-3 text-sm">
                {w.needs_review
                  ? <Badge tone="amber">{t(onGrade ? "result.paperWritingPending" : whoChecks ?? "result.checking")}</Badge>
                  : w.text && <><Badge tone="green">{fmt(w.points ?? 0)} / {fmt(w.max_points)} {t("exam.points")}</Badge>{!onGrade && w.feedback && <p className="mt-2 text-slate-600">“{w.feedback}”</p>}</>}
              </div>
              {onGrade && w.text && (
                <div className="mt-3 grid gap-3 sm:grid-cols-[10rem_10rem_1fr]">
                  <label className="text-sm font-medium text-slate-700">{t("result.points")} (0–{fmt(Number(v.max) || 0)})
                    <input type="number" min={0} max={Number(v.max) || undefined} step="0.5" value={v.points} onChange={(e) => set(w.question_id, "points", e.target.value)}
                      className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
                  </label>
                  <label className="text-sm font-medium text-slate-700">{t("result.paperWritingMax")}
                    <input type="number" min={1} step="0.5" value={v.max} onChange={(e) => set(w.question_id, "max", e.target.value)}
                      className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
                  </label>
                  <Textarea label={t("result.feedback")} rows={2} value={v.feedback} onChange={(e) => set(w.question_id, "feedback", e.target.value)} />
                </div>
              )}
            </div>
          );
        })}
      </div>
      {onGrade && gradable.length > 0 && (
        <div className="mt-4">
          <Button loading={busy} disabled={!ready.length || !valid}
            onClick={() => onGrade(ready.map((i) => ({ question_id: i.question_id, points: Number(vals[i.question_id].points), feedback: vals[i.question_id].feedback, max: Number(vals[i.question_id].max) })))}>
            {t(gradable.some((i) => i.needs_review) ? "result.savePaperWriting" : "result.updatePaperWriting")}
          </Button>
          <p className="mt-2 text-xs text-slate-500">{t("result.speakingHint")}</p>
        </div>
      )}
    </Card>
  );
}

type Part = "speaking" | "writing";
const PART_KEYS: Record<Part, { title: string; pending: string; max: string; save: string; update: string }> = {
  speaking: { title: "🗣 sections.SPEAKING", pending: "result.speakingPending", max: "result.speakingMax", save: "result.saveSpeaking", update: "result.updateSpeaking" },
  writing: { title: "✍️ sections.WRITING", pending: "result.paperWritingPending", max: "result.paperWritingMax", save: "result.savePaperWriting", update: "result.updatePaperWriting" },
};

/** Speaking / writing on paper: the teacher / admin types the points (added to the total). */
function ManualPartBlock({ part, result, onSave, busy, staff }: { part: Part; result: ResultDetail; onSave?: (points: number, feedback: string, max?: number) => void; busy?: boolean; staff?: boolean }) {
  const { t } = useTranslation();
  const k = PART_KEYS[part];
  const examPoints = part === "speaking" ? result.speaking_points : result.writing_points;
  const score = part === "speaking" ? result.speaking_score : result.writing_score;
  const max = part === "speaking" ? result.speaking_max : result.writing_max;
  const given = part === "speaking" ? result.speaking_feedback : result.writing_feedback;
  const by = part === "speaking" ? result.speaking_by_name : result.writing_by_name;
  // the exam sets the maximum; when it has none, the reviewer types it here
  const fixed = Number(examPoints) > 0;
  const [maxIn, setMaxIn] = useState(max ? String(Number(max)) : "10");
  const top = fixed ? Number(examPoints) : Number(maxIn);
  const [points, setPoints] = useState(score == null ? "" : String(Number(score)));
  const [feedback, setFeedback] = useState(given ?? "");
  const valid = top > 0 && points !== "" && Number(points) >= 0 && Number(points) <= top;
  const [icon, titleKey] = k.title.split(" ");
  return (
    <Card title={`${icon} ${t(titleKey)}`}>
      {score != null ? (
        <div className="mb-3 text-sm">
          <Badge tone="green">{fmt(score)} / {fmt(top)} {t("exam.points")}</Badge>
          {staff && by && <span className="ml-2 text-slate-500">{t("result.speakingBy", { name: by })}</span>}
          {given && <p className="mt-2 text-slate-600">“{given}”</p>}
        </div>
      ) : <p className="mb-3"><Badge tone="amber">{t(k.pending)}</Badge></p>}
      {onSave && (
        <div className={cx("grid gap-3", fixed ? "sm:grid-cols-[10rem_1fr]" : "sm:grid-cols-[10rem_10rem_1fr]")}>
          <label className="text-sm font-medium text-slate-700">{t("result.points")} (0–{fmt(top || 0)})
            <input type="number" min={0} max={top} step="0.5" value={points} onChange={(e) => setPoints(e.target.value)}
              className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
          </label>
          {!fixed && (
            <label className="text-sm font-medium text-slate-700">{t(k.max)}
              <input type="number" min={1} step="0.5" value={maxIn} onChange={(e) => setMaxIn(e.target.value)}
                className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
            </label>
          )}
          <Textarea label={t("result.feedback")} rows={2} value={feedback} onChange={(e) => setFeedback(e.target.value)} />
          <div className="sm:col-span-2">
            <Button loading={busy} disabled={!valid} onClick={() => onSave(Number(points), feedback, fixed ? undefined : top)}>{t(score == null ? k.save : k.update)}</Button>
            <p className="mt-2 text-xs text-slate-500">{t("result.speakingHint")}</p>
          </div>
        </div>
      )}
    </Card>
  );
}

export function ResultView({ result, onOffer, offerBusy, onGrade, gradeBusy, staff, onSpeaking, onPaperWriting }: {
  result: ResultDetail; onOffer?: (accept: boolean) => void; offerBusy?: boolean; staff?: boolean;  // staff = a teacher / admin / desk looks at someone else's result
  onGrade?: (grades: { question_id: number; points: number; feedback: string }[]) => void; gradeBusy?: boolean;
  onSpeaking?: (points: number, feedback: string, max?: number) => void;
  onPaperWriting?: (points: number, feedback: string, max?: number) => void;
}) {
  const { t } = useTranslation();
  const upgrade = result.kind === "UPGRADE";
  const pending = result.offer_status === "PENDING" && !!result.recommended_level_code;
  const noPoints = result.total_score === null;  // a student: points and right / wrong counts are not shown

  return (
    <div className="space-y-5">
      <Card>
        <div className="flex flex-col items-center gap-6 sm:flex-row">
          {noPoints ? (
            <div className={cx("flex h-32 w-32 shrink-0 items-center justify-center rounded-full border-8 text-5xl font-bold",
              result.passed === null || result.writing_pending ? "border-amber-300 text-amber-500" : result.passed ? "border-emerald-400 text-emerald-600" : "border-red-300 text-red-500")}>
              {result.passed === null || result.writing_pending ? "…" : result.passed ? "✓" : "✗"}
            </div>
          ) : (
            <div className={cx("flex h-32 w-32 shrink-0 flex-col items-center justify-center rounded-full border-8", result.passed ? "border-emerald-400 text-emerald-700" : "border-red-300 text-red-600")}>
              <span className="text-3xl font-bold tabular-nums">{fmt(result.total_score)}</span>
              <span className="text-xs">/ {fmt(result.max_score)} {t("exam.points")}</span>
            </div>
          )}
          <div className="flex-1 text-center sm:text-left">
            <h2 className="text-xl font-semibold">{result.examination_title}</h2>
            <p className="mt-1 text-sm text-slate-500">
              {result.student_name} · {result.level_code}{result.target_level_code ? ` → ${result.target_level_code}` : ""}
            </p>
            <div className="mt-3 flex flex-wrap justify-center gap-2 sm:justify-start">
              <OutcomeBadge r={result} />
              {!noPoints && <>
                <Badge tone="green">{t("result.correct")}: {result.correct_count}</Badge>
                <Badge tone="red">{t("result.incorrect")}: {result.incorrect_count}</Badge>
                <Badge>{t("result.unanswered")}: {result.unanswered_count}</Badge>
              </>}
              {result.attempt_status === "AUTO_SUBMITTED" && <Badge tone="amber">{t("result.autoSubmitted")}</Badge>}
            </div>
          </div>
        </div>
      </Card>

      {result.writing_pending && (
        <Card className="border-amber-200 bg-amber-50"><p className="text-sm text-amber-900">{t("result.writingPendingNote")}</p></Card>
      )}

      {(staff || !noPoints) && result.section_scores && <Card title={t("result.sections")}>
        <ul className="space-y-4">
          {Object.entries(result.section_scores).map(([name, s]) => (
            <li key={name}>
              <div className="mb-1 flex justify-between text-sm">
                <span className="font-medium">{t(`sections.${name}`)}</span>
                <span className="tabular-nums text-slate-600">{fmt(s.score)} / {fmt(s.max)} {t("exam.points")}</span>
              </div>
              <ProgressBar value={s.percentage} tone={s.percentage >= Number(60) ? "green" : "amber"} />
            </li>
          ))}
        </ul>
      </Card>}

      {/* the student sees the points, sections and written answers only once the result is announced */}
      {(staff || !noPoints) && result.writing?.length > 0 && <WritingBlock key={result.writing.map((w) => `${w.points}/${w.max_points}`).join()} items={result.writing} onGrade={onGrade} busy={gradeBusy}
        whoChecks={staff ? (upgrade ? "result.checkingTeacher" : "result.checkingDesk") : undefined} />}

      {result.kind === "UPGRADE" && (Number(result.speaking_points) > 0 || result.speaking_score !== null || !!onSpeaking) && (
        <ManualPartBlock part="speaking" key={`s${result.speaking_score}`} result={result} onSave={onSpeaking} busy={gradeBusy} staff={staff} />
      )}
      {result.kind === "UPGRADE" && (Number(result.writing_points) > 0 || result.writing_score != null) && (
        <ManualPartBlock part="writing" key={`w${result.writing_score}`} result={result} onSave={onPaperWriting} busy={gradeBusy} staff={staff} />
      )}

      {/* placement recommendation / level offer: staff see it about the student, never "your result" */}
      {pending && staff && (
        <Card className="border-indigo-200 bg-indigo-50">
          <p className="text-base text-slate-800">
            {t(result.recommendation === "LOWER" ? "offer.staffLower" : "offer.staffHigher", { name: result.student_name, level: result.level_code, target: result.recommended_level_code, score: `${fmt(result.total_score)} / ${fmt(result.max_score)}` })}
          </p>
          {onOffer ? (
            <>
              <p className="mt-2 text-sm text-slate-600">{t("offer.staffQuestion")}</p>
              <div className="mt-4 flex flex-wrap gap-3">
                <Button loading={offerBusy} onClick={() => onOffer(true)}>{t("offer.staffYes", { target: result.recommended_level_code })}</Button>
                <Button variant="secondary" disabled={offerBusy} onClick={() => onOffer(false)}>
                  {t("offer.staffNo", { placed: result.recommendation === "LOWER" ? result.recommended_level_code : result.level_code })}
                </Button>
              </div>
            </>
          ) : <p className="mt-2 text-sm text-slate-600">{t("offer.staffWaiting")}</p>}
        </Card>
      )}
      {pending && !staff && onOffer && (
        <Card className="border-indigo-200 bg-indigo-50">
          <p className="whitespace-pre-line text-base text-slate-800">
            {t(result.recommendation === "LOWER" ? "offer.lowerMessage" : "offer.higherMessage", { level: result.level_code, target: result.recommended_level_code })}
          </p>
          <div className="mt-4 flex flex-wrap gap-3">
            <Button size="lg" loading={offerBusy} onClick={() => onOffer(true)}>{t("offer.yes", { target: result.recommended_level_code })}</Button>
            <Button size="lg" variant="secondary" disabled={offerBusy} onClick={() => onOffer(false)}>{t("offer.no")}</Button>
          </div>
        </Card>
      )}
      {!upgrade && !pending && !result.writing_pending && (
        <Card>
          {result.placed_level_code
            ? <p className="text-base">{t("result.placedAt")}: <Badge tone="indigo">{result.placed_level_code}</Badge></p>
            : <p className="text-sm text-slate-500">{t(`offer.status.${result.offer_status}`)}</p>}
          {result.offer_status === "ACCEPTED" && <p className="mt-2 text-sm text-slate-500">{t("offer.status.ACCEPTED")}</p>}
        </Card>
      )}

      {upgrade && !result.writing_pending && (
        <Card title={t("result.upgradeStatus")}>
          {result.approval_status === "NOT_REQUIRED"  // an older result decided by the score alone
            ? <p className={cx("text-sm", result.passed ? "text-emerald-700" : "text-red-600")}>{result.passed ? t("result.passed") : t("result.upgradeFailed")}</p>
            : (
              <div className="space-y-2 text-sm">
                <div className="flex flex-wrap items-center gap-2"><ApprovalBadge status={result.approval_status} />
                  {result.approval_status === "PENDING" && <span className="text-slate-600">{staff
                    ? t("result.awaitingStaff", { suggestion: t(result.passed ? "result.passed" : "result.failed").toLowerCase(), pass: `${fmt(result.passing_score)} / ${fmt(result.max_score)} ${t("exam.points")}` })
                    : t("result.awaitingApproval")}</span>}
                  {result.approval_status === "APPROVED" && <span className="text-slate-600">{t("result.upgradeApproved", { level: result.target_level_code })}</span>}
                  {result.approval_status === "REJECTED" && <span className="text-slate-600">{t("result.upgradeRejected")}</span>}
                </div>
                {staff && result.reviewed_by_name && <p className="text-slate-500">{t("result.reviewedBy")}: {result.reviewed_by_name}</p>}
                {result.review_note && <p className="text-slate-500">“{result.review_note}”</p>}
              </div>
            )}
        </Card>
      )}

      {result.answers && (
        <Card title={t("result.review")}>
          <ol className="space-y-4">
            {result.answers.map((a, i) => (
              <li key={a.question_id} className={cx("rounded-lg border p-4 text-sm", a.is_correct ? "border-emerald-200 bg-emerald-50/50" : "border-red-200 bg-red-50/50")}>
                <p className="font-medium">{i + 1}. {a.text}</p>
                <p className="mt-2"><span className="text-slate-500">{t(staff ? "result.studentAnswer" : "result.yourAnswer")}: </span><AnswerText v={a.student_answer} /></p>
                {!a.is_correct && <p><span className="text-slate-500">{t("result.correctAnswer")}: </span><AnswerText v={a.correct_answer} /></p>}
                {a.explanation && <p className="mt-1 text-slate-500">{a.explanation}</p>}
                <p className="mt-1 text-xs text-slate-400">{a.points_awarded}/{a.points}</p>
              </li>
            ))}
          </ol>
        </Card>
      )}
    </div>
  );
}
