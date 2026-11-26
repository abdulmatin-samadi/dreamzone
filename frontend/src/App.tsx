import { ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import type { Role } from "./api/types";
import { useAuth } from "./auth/AuthContext";
import { AppLayout } from "./components/AppLayout";
import { PageLoader } from "./components/ui";
import ApprovalsPage from "./pages/ApprovalsPage";
import DashboardPage from "./pages/DashboardPage";
import ExamEditorPage from "./pages/ExamEditorPage";
import ExamFlowPage from "./pages/ExamFlowPage";
import ExamsPage from "./pages/ExamsPage";
import GroupExamsPage, { GroupExamDetailPage } from "./pages/GroupExamsPage";
import GroupsPage from "./pages/GroupsPage";
import KioskPage from "./pages/KioskPage";
import LevelsPage from "./pages/LevelsPage";
import LoginPage from "./pages/LoginPage";
import MyExamsPage from "./pages/MyExamsPage";
import StatsPage from "./pages/StatsPage";
import MyGroupPage from "./pages/MyGroupPage";
import RegisterPage from "./pages/RegisterPage";
import PlacementsPage from "./pages/PlacementsPage";
import ProfilePage from "./pages/ProfilePage";
import QuestionsPage from "./pages/QuestionsPage";
import ResultDetailPage from "./pages/ResultDetailPage";
import ResultsPage from "./pages/ResultsPage";
import SchedulePage from "./pages/SchedulePage";
import StudentDetailPage from "./pages/StudentDetailPage";
import StudentsPage from "./pages/StudentsPage";
import TeachersPage from "./pages/TeachersPage";
import UsersPage from "./pages/UsersPage";
import AuditPage from "./pages/AuditPage";
import LiveAttemptsPage from "./pages/LiveAttemptsPage";
import ReportsPage from "./pages/ReportsPage";
import WritingQueuePage from "./pages/WritingQueuePage";

function Guard({ roles, children }: { roles?: Role[]; children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <PageLoader />;
  if (!user) return <Navigate to="/login" replace />;
  if (roles && !roles.includes(user.role)) return <Navigate to="/" replace />;
  return <>{children}</>;
}

const ADMIN: Role[] = ["ADMIN"];
const STAFF_EDU: Role[] = ["ADMIN", "TEACHER"];
const NOT_STUDENT: Role[] = ["ADMIN", "TEACHER", "RECEPTIONIST"];

export default function App() {
  const { user, loading } = useAuth();
  return (
    <Routes>
      <Route path="/login" element={loading ? <PageLoader /> : user ? <Navigate to="/" replace /> : <LoginPage />} />
      <Route path="/register" element={loading ? <PageLoader /> : user ? <Navigate to="/" replace /> : <RegisterPage />} />
      <Route path="/kiosk" element={<Guard roles={["RECEPTIONIST", "ADMIN"]}><KioskPage /></Guard>} />
      <Route path="/exam/:assignmentId" element={<Guard roles={["STUDENT"]}><ExamFlowPage /></Guard>} />
      <Route element={<Guard><AppLayout /></Guard>}>
        <Route index element={<DashboardPage />} />
        <Route path="users" element={<Guard roles={ADMIN}><UsersPage /></Guard>} />
        <Route path="teachers" element={<Guard roles={ADMIN}><TeachersPage /></Guard>} />
        <Route path="levels" element={<Guard roles={ADMIN}><LevelsPage /></Guard>} />
        <Route path="groups" element={<Guard roles={[...STAFF_EDU, "RECEPTIONIST"]}><GroupsPage /></Guard>} />
        <Route path="students" element={<Guard roles={NOT_STUDENT}><StudentsPage /></Guard>} />
        <Route path="students/:id" element={<Guard roles={NOT_STUDENT}><StudentDetailPage /></Guard>} />
        <Route path="placements" element={<Guard roles={["RECEPTIONIST", "ADMIN"]}><PlacementsPage /></Guard>} />
        <Route path="exams" element={<Guard roles={STAFF_EDU}><ExamsPage /></Guard>} />
        <Route path="exams/:id" element={<Guard roles={STAFF_EDU}><ExamEditorPage /></Guard>} />
        <Route path="questions" element={<Guard roles={STAFF_EDU}><QuestionsPage /></Guard>} />
        <Route path="schedule" element={<Guard roles={STAFF_EDU}><SchedulePage /></Guard>} />
        <Route path="approvals" element={<Guard roles={STAFF_EDU}><ApprovalsPage /></Guard>} />
        <Route path="my-exams" element={<Guard roles={["STUDENT"]}><MyExamsPage /></Guard>} />
        <Route path="my-group" element={<Guard roles={["STUDENT"]}><MyGroupPage /></Guard>} />
        <Route path="writing" element={<Guard roles={["TEACHER", "RECEPTIONIST"]}><WritingQueuePage /></Guard>} />
        <Route path="group-exams" element={<Guard roles={["ADMIN"]}><GroupExamsPage /></Guard>} />
        <Route path="group-exams/:exam/:group" element={<Guard roles={["ADMIN"]}><GroupExamDetailPage /></Guard>} />
        <Route path="live" element={<Guard roles={["RECEPTIONIST", "ADMIN"]}><LiveAttemptsPage /></Guard>} />
        <Route path="reports" element={<Guard roles={["RECEPTIONIST", "ADMIN"]}><ReportsPage /></Guard>} />
        <Route path="audit" element={<Guard roles={ADMIN}><AuditPage /></Guard>} />
        <Route path="results" element={<Guard roles={["TEACHER", "RECEPTIONIST", "STUDENT"]}><ResultsPage /></Guard>} />
        <Route path="stats" element={<Guard roles={["TEACHER", "ADMIN"]}><StatsPage /></Guard>} />
        <Route path="results/:id" element={<ResultDetailPage />} />
        <Route path="profile" element={<ProfilePage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
