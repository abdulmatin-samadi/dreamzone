import { StoppedAttempts } from "../components/StoppedAttempts";
import ResultsPage from "./ResultsPage";

export default function ApprovalsPage() {
  return <><StoppedAttempts /><ResultsPage mode="approvals" /></>;
}
