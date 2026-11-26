import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { ResultDetail, ReviewItem, WritingItem } from "../api/types";
import { ApprovalBadge, OutcomeBadge } from "./badges";
import { Badge, Button, Card, ProgressBar, Textarea, cx } from "./ui";

const fmt = (v: string | number) => Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 });

function AnswerText({ v }: { v: ReviewItem["student_answer"] | ReviewItem["correct_answer"] }) {
  const { t } = useTranslation();
  if (v == null || (Array.isArray(v) && v.length === 0)) return <span className="italic text-slate-400">{t("result.noAnswer")}</span>;
  if (typeof v === "string") return <>{v}</>;
  return <>{(v as (string | { left: string; right: string })[]).map((x) => (typeof x === "string" ? x : `${x.left} → ${x.right || "—"}`)).join(" · ")}</>;
}

/** Written answers: the student sees "being checked" or the score; reception (guests) or the teacher (upgrades) types the points. */
function WritingBlock({ items, onGrade, busy, whoChecks }: { items: WritingItem[]; onGrade?: (grades: { question_id: number; points: number; feedback: string }[]) => void; busy?: boolean; whoChecks?: string }) {
  const { t } = useTranslation();
  const [vals, setVals] = useState<Record<number, { points: string; feedback: string }>>({});
  const set = (id: number, k: "points" | "feedback", v: string) => setVals((s) => ({ ...s, [id]: { points: s[id]?.points ?? "", feedback: s[id]?.feedback ?? "", [k]: v } }));
  const ready = items.filter((i) => i.needs_review && vals[i.question_id]?.points !== undefined && vals[i.question_id]?.points !== "");
  const valid = ready.every((i) => { const p = Number(vals[i.question_id].points); return p >= 0 && p <= i.max_points; });
  return (
    <Card title={t("result.writing")}>
      <div className="space-y-5">
        {items.map((w) => (
          <div key={w.question_id} className="rounded-xl border border-slate-200 p-4">
            <p className="text-sm font-semibold text-slate-800">{w.prompt}</p>
            <p className="mt-3 whitespace-pre-wrap rounded-lg bg-slate-50 p-3 text-sm leading-6 text-slate-800">{w.text || <span className="italic text-slate-400">{t("result.noAnswer")}</span>}</p>
            <p className="mt-1 text-xs text-slate-500">{t("exam.wordCount", { n: w.words })}</p>
            {w.needs_review ? (
              onGrade ? (
                <div className="mt-3 grid gap-3 sm:grid-cols-[10rem_1fr]">
                  <label className="text-sm font-medium text-slate-700">{t("result.points")} (0–{w.max_points})
                    <input type="number" min={0} max={w.max_points} step="0.5" value={vals[w.question_id]?.points ?? ""} onChange={(e) => set(w.question_id, "points", e.target.value)}
                      className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
                  </label>
                  <Textarea label={t("result.feedback")} rows={2} value={vals[w.question_id]?.feedback ?? ""} onChange={(e) => set(w.question_id, "feedback", e.target.value)} />
                </div>
              ) : <Badge tone="amber">{t(whoChecks ?? "result.checking")}</Badge>
            ) : (
              <div className="mt-3 text-sm"><Badge tone="green">{fmt(w.points ?? 0)} / {fmt(w.max_points)}</Badge>{w.feedback && <p className="mt-2 text-slate-600">“{w.feedback}”</p>}</div>
            )}
          </div>
        ))}
      </div>
      {onGrade && items.some((i) => i.needs_review) && (
        <Button className="mt-4" loading={busy} disabled={!ready.length || !valid}
          onClick={() => onGrade(ready.map((i) => ({ question_id: i.question_id, points: Number(vals[i.question_id].points), feedback: vals[i.question_id].feedback ?? "" })))}>
          {t("result.saveScores")}
        </Button>
      )}
    </Card>
  );
}

/** Speaking: the teacher / admin types the points (added to the total); the student sees the score once given. */
function SpeakingBlock({ result, onSave, busy, staff }: { result: ResultDetail; onSave?: (points: number, feedback: string, max?: number) => void; busy?: boolean; staff?: boolean }) {
  const { t } = useTranslation();
  // the exam sets the speaking maximum; when it has none, the reviewer types it here
  const fixed = Number(result.speaking_points) > 0;
  const [maxIn, setMaxIn] = useState(result.speaking_max ? String(Number(result.speaking_max)) : "10");
  const top = fixed ? Number(result.speaking_points) : Number(maxIn);
  const [points, setPoints] = useState(result.speaking_score === null ? "" : String(Number(result.speaking_score)));
  const [feedback, setFeedback] = useState(result.speaking_feedback ?? "");
  const valid = top > 0 && points !== "" && Number(points) >= 0 && Number(points) <= top;
  return (
    <Card title={`🗣 ${t("sections.SPEAKING")}`}>
      {result.speaking_score !== null ? (
        <div className="mb-3 text-sm">
          <Badge tone="green">{fmt(result.speaking_score)} / {fmt(top)} {t("exam.points")}</Badge>
          {staff && result.speaking_by_name && <span className="ml-2 text-slate-500">{t("result.speakingBy", { name: result.speaking_by_name })}</span>}
          {result.speaking_feedback && <p className="mt-2 text-slate-600">“{result.speaking_feedback}”</p>}
        </div>
      ) : <p className="mb-3"><Badge tone="amber">{t("result.speakingPending")}</Badge></p>}
      {onSave && (
        <div className={cx("grid gap-3", fixed ? "sm:grid-cols-[10rem_1fr]" : "sm:grid-cols-[10rem_10rem_1fr]")}>
          <label className="text-sm font-medium text-slate-700">{t("result.points")} (0–{fmt(top || 0)})
            <input type="number" min={0} max={top} step="0.5" value={points} onChange={(e) => setPoints(e.target.value)}
              className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
          </label>
          {!fixed && (
            <label className="text-sm font-medium text-slate-700">{t("result.speakingMax")}
              <input type="number" min={1} step="0.5" value={maxIn} onChange={(e) => setMaxIn(e.target.value)}
                className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
            </label>
          )}
          <Textarea label={t("result.feedback")} rows={2} value={feedback} onChange={(e) => setFeedback(e.target.value)} />
          <div className="sm:col-span-2">
            <Button loading={busy} disabled={!valid} onClick={() => onSave(Number(points), feedback, fixed ? undefined : top)}>{t(result.speaking_score === null ? "result.saveSpeaking" : "result.updateSpeaking")}</Button>
            <p className="mt-2 text-xs text-slate-500">{t("result.speakingHint")}</p>
          </div>
        </div>
      )}
    </Card>
  );
}

export function ResultView({ result, onOffer, offerBusy, onGrade, gradeBusy, staff, onSpeaking }: {
  result: ResultDetail; onOffer?: (accept: boolean) => void; offerBusy?: boolean; staff?: boolean;  // staff = a teacher / admin / desk looks at someone else's result
  onGrade?: (grades: { question_id: number; points: number; feedback: string }[]) => void; gradeBusy?: boolean;
  onSpeaking?: (points: number, feedback: string, max?: number) => void;
}) {
  const { t } = useTranslation();
  const upgrade = result.kind === "UPGRADE";
  const pending = result.offer_status === "PENDING" && !!result.recommended_level_code;

  return (
    <div className="space-y-5">
      <Card>
        <div className="flex flex-col items-center gap-6 sm:flex-row">
          <div className={cx("flex h-32 w-32 shrink-0 flex-col items-center justify-center rounded-full border-8", result.passed ? "border-emerald-400 text-emerald-700" : "border-red-300 text-red-600")}>
            <span className="text-3xl font-bold tabular-nums">{fmt(result.total_score)}</span>
            <span className="text-xs">/ {fmt(result.max_score)} {t("exam.points")}</span>
          </div>
          <div className="flex-1 text-center sm:text-left">
            <h2 className="text-xl font-semibold">{result.examination_title}</h2>
            <p className="mt-1 text-sm text-slate-500">
              {result.student_name} · {result.level_code}{result.target_level_code ? ` → ${result.target_level_code}` : ""}
            </p>
            <div className="mt-3 flex flex-wrap justify-center gap-2 sm:justify-start">
              <OutcomeBadge r={result} />
              <Badge tone="green">{t("result.correct")}: {result.correct_count}</Badge>
              <Badge tone="red">{t("result.incorrect")}: {result.incorrect_count}</Badge>
              <Badge>{t("result.unanswered")}: {result.unanswered_count}</Badge>
              {result.attempt_status === "AUTO_SUBMITTED" && <Badge tone="amber">{t("result.autoSubmitted")}</Badge>}
            </div>
          </div>
        </div>
      </Card>

      {result.writing_pending && (
        <Card className="border-amber-200 bg-amber-50"><p className="text-sm text-amber-900">{t("result.writingPendingNote")}</p></Card>
      )}

      {staff && <Card title={t("result.sections")}>
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

      {/* the student sees the score, not the per-section breakdown or the written answers */}
      {staff && result.writing?.length > 0 && <WritingBlock items={result.writing} onGrade={onGrade} busy={gradeBusy}
        whoChecks={staff ? (upgrade ? "result.checkingTeacher" : "result.checkingDesk") : undefined} />}

      {result.kind === "UPGRADE" && (Number(result.speaking_points) > 0 || result.speaking_score !== null || !!onSpeaking) && (
        <SpeakingBlock key={`${result.speaking_score}`} result={result} onSave={onSpeaking} busy={gradeBusy} staff={staff} />
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
