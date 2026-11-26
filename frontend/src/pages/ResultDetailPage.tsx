import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api, download } from "../api/client";
import type { ResultDetail } from "../api/types";
import { LoadError } from "../components/NotFound";
import { useAuth } from "../auth/AuthContext";
import { ResultView } from "../components/ResultView";
import { useNotify } from "../components/Toast";
import { Button, Card, Modal, PageHeader, PageLoader, Select, Textarea } from "../components/ui";
import { ReviewModal } from "./ResultsPage";

export default function ResultDetailPage() {
  const { id } = useParams();
  const { t } = useTranslation();
  const { user } = useAuth();
  const nav = useNavigate();
  const qc = useQueryClient();
  const notify = useNotify();
  const [review, setReview] = useState<"approve" | "reject" | null>(null);
  const [override, setOverride] = useState(false);
  const [ov, setOv] = useState({ status: "REJECTED", note: "" });
  const [busy, setBusy] = useState(false);

  const q = useQuery({ queryKey: ["results", id], queryFn: async () => (await api.get<ResultDetail>(`/results/${id}/`)).data });
  if (q.isError) return <LoadError />;
  if (q.isLoading || !q.data) return <PageLoader />;
  const r = q.data;
  const role = user!.role;
  const canReview = (role === "ADMIN" || role === "TEACHER") && r.approval_status === "PENDING";
  const refresh = () => void qc.invalidateQueries({ queryKey: ["results"] });

  const answerOffer = async (accept: boolean) => {
    setBusy(true);
    try {
      const { data } = await api.post<{ assignment_id: number | null }>(`/results/${r.id}/offer/`, { accept });
      refresh();
      if (accept && data.assignment_id) {
        if (role === "STUDENT") return nav(`/exam/${data.assignment_id}`);
        notify.ok("offer.assignedNotice"); return nav("/placements");
      }
    } catch (e) { notify.fail(e); } finally { setBusy(false); }
  };

  const doOverride = async () => {
    setBusy(true);
    try { await api.post(`/results/${r.id}/override/`, ov); notify.ok("common.saved"); setOverride(false); refresh(); } catch (e) { notify.fail(e); } finally { setBusy(false); }
  };

  // guests' (placement) writing is scored at reception, level-upgrade writing by the teacher
  const canGrade = r.writing_pending && (r.kind === "UPGRADE" ? role === "TEACHER" : role === "RECEPTIONIST");
  const grade = async (grades: { question_id: number; points: number; feedback: string }[]) => {
    setBusy(true);
    try { await api.post(`/results/${r.id}/grade-writing/`, { grades }); notify.ok("result.scoresSaved"); refresh(); } catch (e) { notify.fail(e); } finally { setBusy(false); }
  };
  // speaking: an upgrade exam with a speaking part, scored by the teacher or the admin
  const canSpeak = r.kind === "UPGRADE" && (role === "ADMIN" || (role === "TEACHER" && !["APPROVED", "REJECTED"].includes(r.approval_status)));
  const speak = async (points: number, feedback: string, max?: number) => {
    setBusy(true);
    try { await api.post(`/results/${r.id}/speaking/`, { points, feedback, ...(max ? { max } : {}) }); notify.ok("result.scoresSaved"); refresh(); } catch (e) { notify.fail(e); } finally { setBusy(false); }
  };
  const canOffer = r.offer_status === "PENDING" && ["STUDENT", "RECEPTIONIST", "ADMIN"].includes(role);
  return (
    <>
      <PageHeader title={t("result.title")} actions={<>
        {role !== "ADMIN" && role !== "TEACHER" && <Button variant="secondary" onClick={() => nav(-1)}>{t("common.back")}</Button>}  {/* staff: the layout's back button */}
        {role !== "RECEPTIONIST" && <Button variant="secondary" onClick={() => download(`/results/${r.id}/export/`, {}, `result-${r.id}.pdf`)}>PDF</Button>}
        {canReview && <><Button variant="success" onClick={() => setReview("approve")}>{t("approvals.approve")}</Button><Button variant="danger" onClick={() => setReview("reject")}>{t("approvals.reject")}</Button></>}
        {role === "ADMIN" && r.kind === "UPGRADE" && r.is_locked && <Button variant="secondary" onClick={() => setOverride(true)}>{t("approvals.override")}</Button>}
      </>} />
      {role !== "STUDENT" && <p className="mb-4 text-sm"><Link className="text-indigo-700 hover:underline" to={`/students/${r.student}`}>{t("result.studentProfile")} →</Link></p>}
      <ResultView result={r} staff={role !== "STUDENT"} onOffer={canOffer ? answerOffer : undefined} offerBusy={busy} onGrade={canGrade ? grade : undefined} gradeBusy={busy} onSpeaking={canSpeak ? speak : undefined} />
      {role === "RECEPTIONIST" && r.offer_status === "ACCEPTED" && <Card className="mt-5"><Link className="text-indigo-700" to="/placements">{t("offer.goToPlacements")} →</Link></Card>}

      <ReviewModal result={review ? r : null} mode={review ?? "approve"} onClose={() => setReview(null)} onDone={() => { setReview(null); refresh(); }} />
      <Modal open={override} onClose={() => setOverride(false)} title={t("approvals.override")}
        footer={<><Button variant="secondary" onClick={() => setOverride(false)}>{t("common.cancel")}</Button><Button loading={busy} disabled={!ov.note.trim()} onClick={doOverride}>{t("common.save")}</Button></>}>
        <p className="mb-3 text-sm text-slate-600">{t("approvals.overrideHint")}</p>
        <Select label={t("approval.title")} value={ov.status} onChange={(e) => setOv({ ...ov, status: e.target.value })}>
          {["APPROVED", "REJECTED", "PENDING"].map((s) => <option key={s} value={s}>{t(`approval.${s}`)}</option>)}
        </Select>
        <Textarea className="mt-3" label={t("approvals.note")} required value={ov.note} onChange={(e) => setOv({ ...ov, note: e.target.value })} />
      </Modal>
    </>
  );
}
