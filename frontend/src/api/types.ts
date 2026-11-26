export type Role = "ADMIN" | "RECEPTIONIST" | "TEACHER" | "STUDENT";
export type Section = "GRAMMAR" | "VOCABULARY" | "READING" | "LISTENING" | "WRITING";
export type QType = "MCQ" | "MSQ" | "TF" | "FILL" | "MATCH" | "READING" | "LISTENING" | "WRITING";
export type ExamKind = "PLACEMENT" | "UPGRADE";

export interface Paginated<T> { count: number; next: string | null; previous: string | null; results: T[] }

export interface User {
  id: number; username: string; first_name: string; last_name: string; full_name: string; email: string;
  phone: string; role: Role; language: string; current_level: string | null;
  is_active?: boolean; student_id?: number | null; teacher_id?: number | null; date_joined?: string;
}
export interface Level { id: number; code: string; name: string; description: string; order: number; is_active: boolean; student_count: number }
export interface Group { id: number; name: string; level: number; level_code: string; teacher: number | null; teacher_name: string | null; schedule: string; is_active: boolean; student_count: number; join_code?: string }
export interface Student {
  id: number; first_name: string; last_name: string; full_name: string; phone: string; username: string; is_active: boolean; is_guest: boolean;
  current_level: number | null; current_level_code: string | null; initial_level: number | null; initial_level_code: string | null;
  notes: string; groups: { id: number; name: string }[]; created_at: string;
}
export interface Option { id?: number; text: string; match_text: string; is_correct: boolean; order: number }
export interface Passage { id: number; title: string; text: string; audio: string | null; level: number; level_code: string; question_count: number }
export interface Question {
  id: number; text: string; question_type: QType; section: Section; category: string; level: number; level_code: string; points: string;
  explanation: string; image: string | null; audio: string | null; reading_passage: string; passage: number | null;
  passage_title: string | null; options: Option[]; created_by_name: string | null; in_use: boolean; created_at: string;
}
export interface Exam {
  id: number; kind: ExamKind; title: string; level: number; level_code: string; target_level: number | null;
  target_level_code: string | null; instructions: string; duration_minutes: number; passing_score: string; speaking_points: string;
  high_threshold: string | null; status: "DRAFT" | "PUBLISHED"; shuffle_questions: boolean; shuffle_options: boolean;
  show_correct_answers: boolean; teachers: number[]; teacher_names: string[]; created_by_name: string | null; variant_count: number; assignment_count: number;
  attempt_count: number; locked: boolean; can_edit: boolean; created_at: string;
}
export interface VariantQuestion { id: number; question: number; order: number; text: string; question_type: QType; section: Section; points: string }
export interface Variant { id: number; examination: number; name: string; order: number; question_count: number; total_points: number; questions: VariantQuestion[] }
export type AssignmentState = "available" | "scheduled" | "in_progress" | "completed" | "expired" | "pending_approval";
export interface Assignment {
  id: number; examination: number; examination_title: string; examination_kind: ExamKind; level_code: string;
  target_level_code: string | null; student: number; student_name: string; student_is_guest: boolean; variant: number; variant_name: string;
  group: number | null; group_name: string | null; available_from: string | null; available_until: string | null;
  state: AssignmentState; attempt_id: number | null; result_id: number | null; created_at: string;
}
export interface MyAssignment {
  id: number; examination_title: string; examination_kind: ExamKind; level_code: string; target_level_code: string | null;
  available_from: string | null; available_until: string | null; state: AssignmentState; attempt_id: number | null;
  result_id: number | null; duration_minutes: number; instructions: string; question_count: number; max_points: number; passing_points: number; passing_score: string;
  created_at: string;
}

export type Answer = { option_ids?: number[]; text?: string; pairs?: Record<string, string> };
export interface AttemptQuestion {
  id: number; type: QType; section: Section; category: string; instruction: string; gap_no: number | null; text: string; points: number; image: string | null; audio: string | null;
  passage: { id: number | null; title: string; text: string; audio: string | null } | null; answer: Answer | null;
  options: { id: number; text: string }[]; choices?: string[];
}
export interface AttemptPayload {
  id: number; examination: string; kind: ExamKind; level: string; target_level: string | null; status: string;
  started_at: string; deadline_at: string; server_now: string; remaining_seconds: number; duration_minutes: number;
  questions: AttemptQuestion[]; result_id: number | null;
  violation_seconds_left: number | null; violation_limit_seconds: number;
}

export interface SectionScore { score: number; max: number; correct: number; total: number; percentage: number }
export interface Result {
  id: number; student: number; student_name: string; student_phone: string; examination: number; examination_title: string;
  kind: ExamKind; level_code: string; target_level_code: string | null; total_score: string | null; max_score: string | null;  // null for the student: points are staff-only
  percentage: string | null; correct_count: number | null; incorrect_count: number | null; unanswered_count: number | null; passed: boolean | null;  // null: student, upgrade not decided yet
  recommendation: "NONE" | "CONFIRM" | "LOWER" | "HIGHER"; recommended_level_code: string | null;
  offer_status: "NONE" | "PENDING" | "ACCEPTED" | "DECLINED"; placed_level_code: string | null;
  approval_status: "NOT_REQUIRED" | "PENDING" | "APPROVED" | "REJECTED"; teacher_name: string | null;
  started_at: string; finished_at: string | null; attempt_status: string; writing_pending: boolean; created_at: string;
  speaking_score: string | null; speaking_max: string | null; review_note: string;
}
export interface ReviewItem {
  question_id: number; text: string; type: QType; section: Section; points: number; points_awarded: number;
  is_correct: boolean | null; student_answer: string | string[] | { left: string; right: string }[] | null;
  correct_answer: string[] | { left: string; right: string }[]; explanation: string;
}
export interface WritingItem { question_id: number; prompt: string; text: string; max_points: number; points: number | null; feedback: string; needs_review: boolean; words: number }
export interface ResultDetail extends Result {
  writing: WritingItem[];
  section_scores: Record<string, SectionScore>; review_note: string; reviewed_by_name: string | null;
  reviewed_at: string | null; is_locked: boolean; answers: ReviewItem[] | null; passing_score: string;  // pass mark in points
  speaking_points: string; speaking_score: string | null; speaking_max: string | null; speaking_feedback: string; speaking_by_name: string | null; speaking_at: string | null;
}
export interface LevelChange {
  id: number; student: number; student_name: string; from_level_code: string | null; to_level_code: string;
  reason: string; changed_by_name: string | null; note: string; created_at: string;
}
