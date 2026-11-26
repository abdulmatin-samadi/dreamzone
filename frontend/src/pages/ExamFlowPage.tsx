import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";

import { api } from "../api/client";
import { ExamFlow } from "../components/ExamFlow";

export default function ExamFlowPage() {
  const { assignmentId } = useParams();
  const nav = useNavigate();
  const { t } = useTranslation();
  return <ExamFlow api={api} initial={{ k: "instructions", assignmentId: Number(assignmentId) }} onExit={() => nav("/my-exams")} exitLabel={t("exam.backToExams")} />;
}
