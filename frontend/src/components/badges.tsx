import { useTranslation } from "react-i18next";

import type { Result } from "../api/types";
import { Badge, Tone } from "./ui";

export function LevelBadge({ code }: { code: string | null | undefined }) {
  return code ? <Badge tone="indigo">{code}</Badge> : <span className="text-slate-400">—</span>;
}

/** null = an upgrade result the teacher / admin has not decided on yet. */
export function PassBadge({ passed }: { passed: boolean | null }) {
  const { t } = useTranslation();
  if (passed === null) return <Badge tone="amber">{t("result.awaited")}</Badge>;
  return <Badge tone={passed ? "green" : "red"}>{passed ? t("result.passed") : t("result.failed")}</Badge>;
}

const approvalTone: Record<Result["approval_status"], Tone> = { NOT_REQUIRED: "gray", PENDING: "amber", APPROVED: "green", REJECTED: "red" };
export function ApprovalBadge({ status }: { status: Result["approval_status"] }) {
  const { t } = useTranslation();
  if (status === "NOT_REQUIRED") return <span className="text-slate-400">—</span>;
  return <Badge tone={approvalTone[status]}>{t(`approval.${status}`)}</Badge>;
}

export function KindBadge({ kind }: { kind: string }) {
  const { t } = useTranslation();
  return <Badge tone={kind === "PLACEMENT" ? "blue" : "indigo"}>{t(`kinds.${kind}`)}</Badge>;
}

const stateTone: Record<string, Tone> = { available: "green", scheduled: "blue", in_progress: "amber", completed: "gray", expired: "red", pending_approval: "amber" };
export function StateBadge({ state }: { state: string }) {
  const { t } = useTranslation();
  return <Badge tone={stateTone[state] ?? "gray"}>{t(`states.${state}`)}</Badge>;
}

/** Outcome of a result: writing being checked / awaiting the teacher's decision / the system's suggestion (staff) / passed or not. */
export function OutcomeBadge({ r }: { r: { writing_pending: boolean; passed: boolean | null; kind: string; approval_status?: string } }) {
  const { t } = useTranslation();
  if (r.writing_pending) return <Badge tone="amber">{t("result.writingPending")}</Badge>;
  if (r.passed !== null && r.kind === "UPGRADE" && r.approval_status === "PENDING")
    return <Badge tone="indigo">{t(r.passed ? "result.suggestPassed" : "result.suggestFailed")}</Badge>;
  return <PassBadge passed={r.passed} />;
}
