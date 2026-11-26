"""Evaluation, placement recommendations, level changes and upgrade approval."""
from collections import OrderedDict
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import DomainError
from apps.examinations.models import ExamAssignment, ExamKind, Examination, StudentAnswer
from apps.examinations.services import create_assignments, usable_variants
from apps.questions.grading import grade, is_blank
from apps.questions.models import QuestionType, Section
from apps.students.models import LevelChangeHistory, StudentProfile

from .models import ApprovalStatus, ExamResult, OfferStatus, Recommendation

TWO = Decimal("0.01")


def q2(value):
    return Decimal(value).quantize(TWO, rounding=ROUND_HALF_UP)


# --------------------------------------------------------------------------- level changes
def change_student_level(student, to_level, *, reason, changed_by=None, result=None, note=""):
    """Single place that mutates ``current_level`` – always writes the history row."""
    student = StudentProfile.objects.select_for_update().get(pk=student.pk)
    if student.current_level_id == to_level.id:
        return None
    entry = LevelChangeHistory.objects.create(
        student=student, from_level=student.current_level, to_level=to_level, reason=reason,
        result=result, changed_by=changed_by, note=note,
    )
    student.current_level = to_level
    student.save(update_fields=["current_level"])
    return entry


# --------------------------------------------------------------------------- evaluation
def _variant_questions(attempt):
    return list(attempt.variant.variant_questions.select_related("question").prefetch_related("question__options"))


def _auto_grade(attempt, vqs):
    """Score every objective question. Written answers are only flagged for the teacher."""
    answers = {a.question_id: a for a in StudentAnswer.objects.filter(attempt=attempt)}
    to_update = []
    for vq in vqs:
        q = vq.question
        ans = answers.get(q.id)
        if ans is None:
            continue
        if q.question_type == QuestionType.WRITING:
            ans.is_correct, ans.points_awarded = None, Decimal(0)
            ans.needs_review = not is_blank(q.question_type, ans.answer)
        elif is_blank(q.question_type, ans.answer):
            ans.is_correct, ans.points_awarded = None, Decimal(0)
        else:
            ans.is_correct, ans.points_awarded = grade(q, list(q.options.all()), ans.answer)
        to_update.append(ans)
    if to_update:
        StudentAnswer.objects.bulk_update(to_update, ["is_correct", "points_awarded", "needs_review"])


def _totals(attempt, vqs):
    """Sum the points already stored on the answers (objective ones and the teacher's writing scores)."""
    answers = {a.question_id: a for a in StudentAnswer.objects.filter(attempt=attempt)}
    sections = OrderedDict((s.value, {"score": Decimal(0), "max": Decimal(0), "correct": 0, "total": 0}) for s in Section)
    total = max_score = Decimal(0)
    correct = incorrect = unanswered = pending = 0
    for vq in vqs:
        q = vq.question
        sec = sections[q.section]
        sec["max"] += q.points
        sec["total"] += 1
        max_score += q.points
        ans = answers.get(q.id)
        if ans is None or is_blank(q.question_type, ans.answer):
            unanswered += 1
            continue
        total += ans.points_awarded
        sec["score"] += ans.points_awarded
        if q.question_type == QuestionType.WRITING:
            pending += 1 if ans.needs_review else 0  # graded writing counts for points only
            continue
        if ans.is_correct:
            correct += 1
            sec["correct"] += 1
        else:
            incorrect += 1
    pct = q2(total / max_score * 100) if max_score else Decimal(0)
    section_scores = {
        k: {"score": float(v["score"]), "max": float(v["max"]), "correct": v["correct"], "total": v["total"],
            "percentage": float(q2(v["score"] / v["max"] * 100)) if v["max"] else 0.0}
        for k, v in sections.items() if v["total"]
    }
    return dict(total_score=q2(total), max_score=q2(max_score), percentage=pct, correct_count=correct,
                incorrect_count=incorrect, unanswered_count=unanswered, section_scores=section_scores, pending=pending)


def _post_process(result):
    """Decisions that need the final score: placement recommendation / upgrade approval."""
    if result.examination.kind == ExamKind.PLACEMENT:
        _apply_placement_logic(result)
    else:
        # upgrade: the teacher / admin looks at the result and decides passed or not; the student waits
        result.approval_status = ApprovalStatus.PENDING
        result.save(update_fields=["approval_status"])


@transaction.atomic
def evaluate_attempt(attempt):
    exam = attempt.examination
    vqs = _variant_questions(attempt)
    _auto_grade(attempt, vqs)
    t = _totals(attempt, vqs)
    pending = t.pop("pending")
    result = ExamResult.objects.create(
        attempt=attempt, student=attempt.student, examination=exam, level=exam.level,
        passed=t["total_score"] >= exam.passing_score, writing_pending=pending > 0, **t,
    )
    if not result.writing_pending:  # with written work the level decision waits for the teacher's scores
        _post_process(result)
    return result


def writing_kind_for(user):
    """Who scores written answers: the guests' placement writing goes to reception, upgrade writing to the teacher."""
    from apps.accounts.models import Role

    return {Role.RECEPTIONIST: ExamKind.PLACEMENT, Role.TEACHER: ExamKind.UPGRADE}.get(user.role)


@transaction.atomic
def grade_writing(result_id, *, user, grades):
    """Teacher scores written answers. ``grades`` = [{"question_id", "points", "feedback"}].
    When the last one is scored the result is completed and placement / approval logic runs."""
    result = (
        ExamResult.objects.select_for_update(of=("self",))
        .select_related("examination", "level", "attempt__variant", "student__user").get(pk=result_id)
    )
    if not result.writing_pending:
        raise DomainError("writing_not_pending")
    attempt = result.attempt
    answers = {a.question_id: a for a in StudentAnswer.objects.filter(attempt=attempt, needs_review=True)}
    questions = {vq.question_id: vq.question for vq in _variant_questions(attempt)}
    now = timezone.now()
    for g in grades:
        ans, q = answers.get(g.get("question_id")), questions.get(g.get("question_id"))
        if ans is None or q is None or q.question_type != QuestionType.WRITING:
            raise DomainError("writing_answer_not_found", status_code=400)
        try:
            points = Decimal(str(g.get("points")))
        except ArithmeticError:
            raise DomainError("invalid_points", status_code=400)
        if points < 0 or points > q.points:
            raise DomainError("points_out_of_range", status_code=400)
        ans.points_awarded, ans.needs_review = points, False
        ans.feedback, ans.graded_by, ans.graded_at = str(g.get("feedback", ""))[:2000], user, now
        ans.save(update_fields=["points_awarded", "needs_review", "feedback", "graded_by", "graded_at"])
    pending = _recompute(result)
    result.writing_pending = pending > 0
    result.save()
    from apps.audit.services import record

    record("result.writing_graded", actor=user, target=result.student, target_type="result",
           detail={"result": result.pk, "exam": result.examination.title,
                   "scores": [{"question": g.get("question_id"), "points": str(g.get("points"))} for g in grades],
                   "total": f"{result.total_score}/{result.max_score}"})
    if not result.writing_pending:
        _post_process(result)
    return result


def _recompute(result):
    """Totals from the answers plus the speaking score (if given). Updates the result in memory; returns pending writing count."""
    t = _totals(result.attempt, _variant_questions(result.attempt))
    pending = t.pop("pending")
    if result.speaking_score is not None and result.speaking_max:
        t["total_score"] = q2(t["total_score"] + result.speaking_score)
        t["max_score"] = q2(t["max_score"] + result.speaking_max)
        t["percentage"] = q2(t["total_score"] / t["max_score"] * 100) if t["max_score"] else Decimal(0)
        t["section_scores"]["SPEAKING"] = {
            "score": float(result.speaking_score), "max": float(result.speaking_max), "correct": 0, "total": 1,
            "percentage": float(q2(result.speaking_score / result.speaking_max * 100))}
    for k, v in t.items():
        setattr(result, k, v)
    result.passed = result.total_score >= result.examination.passing_score  # the system's suggestion
    return pending


def speaking_missing(result):
    """An upgrade exam with a speaking part whose speaking score nobody has entered yet."""
    exam = result.examination
    return exam.kind == ExamKind.UPGRADE and exam.speaking_points > 0 and result.speaking_score is None


@transaction.atomic
def grade_speaking(result_id, *, user, points, feedback="", max_points=None):
    """Teacher / admin enters the speaking score; it is added to the total and the suggestion is recomputed."""
    from apps.accounts.models import Role
    from apps.audit.services import record

    result = (ExamResult.objects.select_for_update(of=("self",))
              .select_related("examination", "attempt__variant", "student__user").get(pk=result_id))
    exam = result.examination
    if exam.kind != ExamKind.UPGRADE:
        raise DomainError("not_an_upgrade_exam", status_code=400)
    top = exam.speaking_points or result.speaking_max
    if not exam.speaking_points and max_points not in (None, ""):
        # the exam has no speaking part set: the reviewer says what this speaking was out of
        try:
            top = Decimal(str(max_points))
        except ArithmeticError:
            raise DomainError("invalid_points", status_code=400)
    if not top or top <= 0:
        raise DomainError("speaking_not_set", status_code=400)
    if result.approval_status in (ApprovalStatus.APPROVED, ApprovalStatus.REJECTED) and user.role != Role.ADMIN:
        raise DomainError("result_locked")
    try:
        points = Decimal(str(points))
    except ArithmeticError:
        raise DomainError("invalid_points", status_code=400)
    if points < 0 or points > top:
        raise DomainError("points_out_of_range", status_code=400)
    result.speaking_score, result.speaking_max = points, top
    result.speaking_feedback, result.speaking_by, result.speaking_at = str(feedback or "")[:2000], user, timezone.now()
    _recompute(result)
    if result.approval_status == ApprovalStatus.APPROVED:
        result.passed = True  # a decision already taken stays the decision
    elif result.approval_status == ApprovalStatus.REJECTED:
        result.passed = False
    result.save()
    record("result.speaking_graded", actor=user, target=result.student, target_type="result",
           detail={"result": result.pk, "exam": exam.title, "speaking": f"{points:g} / {top:g}",
                   "total": f"{result.total_score:g} / {result.max_score:g}"})
    return result


# --------------------------------------------------------------------------- placement
def _offer_exam(student, level):
    """Placement exam of ``level`` if the student may still be offered it."""
    if level is None:
        return None
    exam = Examination.objects.filter(kind=ExamKind.PLACEMENT, level=level, status="PUBLISHED").first()
    if exam is None or not usable_variants(exam):
        return None
    if ExamAssignment.objects.filter(examination=exam, student=student).exists():
        return None  # one-time rule: never offer something already assigned
    return exam


def _apply_placement_logic(result):
    exam, level, student = result.examination, result.level, result.student
    score = result.total_score
    if score < exam.passing_score:
        band, target_level = Recommendation.LOWER, level.previous()
    elif exam.high_threshold is not None and score >= exam.high_threshold:
        band, target_level = Recommendation.HIGHER, level.next()
    else:
        band, target_level = Recommendation.CONFIRM, None

    result.recommendation = band
    if target_level is not None and _offer_exam(student, target_level):
        result.recommended_level = target_level
        result.offer_status = OfferStatus.PENDING
        result.save(update_fields=["recommendation", "recommended_level", "offer_status"])
        return
    result.save(update_fields=["recommendation"])
    _finalize_placement(result, changed_by=None)


def _finalize_placement(result, *, changed_by):
    """Decide the level the student ends up with when no (more) test is taken."""
    level = result.level
    if result.recommendation == Recommendation.LOWER:
        placed = level.previous() or level
    else:
        placed = level
    result.placed_level = placed
    result.save(update_fields=["placed_level"])
    change_student_level(
        result.student, placed, reason=LevelChangeHistory.Reason.PLACEMENT, changed_by=changed_by, result=result,
        note=f"Placement test {level.code}: {result.total_score:g} / {result.max_score:g}",
    )


@transaction.atomic
def respond_to_offer(result_id, *, accept, user):
    """Handle the 'Yes, try X / No, finish' buttons. Returns ``(result, new_assignment|None)``."""
    result = (
        ExamResult.objects.select_for_update(of=("self",))
        .select_related("examination", "level", "recommended_level", "student__user")
        .get(pk=result_id)
    )
    if result.offer_status != OfferStatus.PENDING:
        raise DomainError("offer_already_answered")
    if accept:
        exam = _offer_exam(result.student, result.recommended_level)
        if exam is None:
            raise DomainError("offer_unavailable")
        created, _ = create_assignments(
            examination=exam, students=[result.student], assigned_by=user, origin_result=result
        )
        result.offer_status = OfferStatus.ACCEPTED
        result.save(update_fields=["offer_status"])
        return result, created[0]
    result.offer_status = OfferStatus.DECLINED
    result.save(update_fields=["offer_status"])
    # Declined a "go lower" offer => placed one level below; declined "go higher" => keeps the tested level.
    _finalize_placement(result, changed_by=user)
    return result, None


# --------------------------------------------------------------------------- upgrade approval
def _lock(result_id):
    return (
        ExamResult.objects.select_for_update(of=("self",))
        .select_related("examination__target_level", "examination__level", "student__user", "student__current_level")
        .get(pk=result_id)
    )


@transaction.atomic
def approve_upgrade(result_id, *, user, note=""):
    result = _lock(result_id)
    exam = result.examination
    if exam.kind != ExamKind.UPGRADE:
        raise DomainError("not_an_upgrade_exam", status_code=400)
    if result.approval_status != ApprovalStatus.PENDING:
        raise DomainError("result_locked")
    if result.writing_pending:
        raise DomainError("writing_still_pending")
    if speaking_missing(result):
        raise DomainError("speaking_still_pending")
    if result.student.current_level_id not in (None, exam.level_id):  # no level yet (joined by group code): fine
        raise DomainError("student_level_changed")
    result.approval_status, result.passed = ApprovalStatus.APPROVED, True  # the reviewer's decision is the result
    result.reviewed_by, result.reviewed_at, result.review_note = user, timezone.now(), note
    result.save(update_fields=["approval_status", "passed", "reviewed_by", "reviewed_at", "review_note"])
    change_student_level(
        result.student, exam.target_level, reason=LevelChangeHistory.Reason.UPGRADE, changed_by=user,
        result=result, note=note,
    )
    _audit_review("result.approved", result, user, note)
    return result


def _audit_review(action, result, user, note, **extra):
    from apps.audit.services import record

    record(action, actor=user, target=result.student, target_type="result",
           detail={"result": result.pk, "exam": result.examination.title, "score": f"{result.total_score:g} / {result.max_score:g}", "note": note, **extra})


@transaction.atomic
def reject_upgrade(result_id, *, user, note=""):
    result = _lock(result_id)
    if result.examination.kind != ExamKind.UPGRADE:
        raise DomainError("not_an_upgrade_exam", status_code=400)
    if result.approval_status != ApprovalStatus.PENDING:
        raise DomainError("result_locked")
    if result.writing_pending:
        raise DomainError("writing_still_pending")
    if speaking_missing(result):
        raise DomainError("speaking_still_pending")
    result.approval_status, result.passed = ApprovalStatus.REJECTED, False
    result.reviewed_by, result.reviewed_at, result.review_note = user, timezone.now(), note
    result.save(update_fields=["approval_status", "passed", "reviewed_by", "reviewed_at", "review_note"])
    _audit_review("result.rejected", result, user, note)
    return result


@transaction.atomic
def admin_override(result_id, *, user, status, note):
    """Only administrators may change a locked decision. Level changes are applied / reverted."""
    result = _lock(result_id)
    exam = result.examination
    if exam.kind != ExamKind.UPGRADE:
        raise DomainError("not_an_upgrade_exam", status_code=400)
    if status not in (ApprovalStatus.APPROVED, ApprovalStatus.REJECTED, ApprovalStatus.PENDING):
        raise DomainError("invalid_status", status_code=400)
    previous = result.approval_status
    if previous == status:
        return result
    student = result.student
    if previous == ApprovalStatus.APPROVED and student.current_level_id == exam.target_level_id:
        change_student_level(student, exam.level, reason=LevelChangeHistory.Reason.REVERT, changed_by=user,
                             result=result, note=note)
    if status == ApprovalStatus.APPROVED:
        change_student_level(student, exam.target_level, reason=LevelChangeHistory.Reason.ADMIN, changed_by=user,
                             result=result, note=note)
    result.approval_status = status
    result.passed = {ApprovalStatus.APPROVED: True, ApprovalStatus.REJECTED: False}.get(
        status, result.total_score >= exam.passing_score)  # back to pending: the system's suggestion again
    result.reviewed_by, result.reviewed_at, result.review_note = user, timezone.now(), note
    result.save(update_fields=["approval_status", "passed", "reviewed_by", "reviewed_at", "review_note"])
    _audit_review("result.overridden", result, user, note, **{"from": previous, "to": status})
    return result
