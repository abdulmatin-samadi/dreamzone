"""Examination engine: assignment, start/resume, autosave and submission.

All state transitions that must be atomic run inside ``transaction.atomic`` with
row locks, so concurrent requests (double clicks, two tabs) cannot create two
attempts or evaluate an attempt twice.
"""
import random
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.exceptions import DomainError
from apps.questions.grading import validate_answer_shape
from apps.questions.models import QuestionType

from .models import (
    AttemptStatus, AttemptViolation, ExamAssignment, ExamAttempt, StudentAnswer, ViolationKind,
)


# --------------------------------------------------------------------------- assignment
def usable_variants(examination):
    return [v for v in examination.variants.prefetch_related("variant_questions") if v.variant_questions.all()]


def assert_exam_assignable(examination):
    if not examination.is_published:
        raise DomainError("exam_not_published")
    if not usable_variants(examination):
        raise DomainError("exam_has_no_questions")


def create_assignments(*, examination, students, assigned_by, variant=None, group=None,
                       available_from=None, available_until=None, origin_result=None):
    """Create one assignment per student. Existing assignments are skipped (never duplicated).

    Returns ``(created, skipped)`` lists of assignments / students.
    """
    assert_exam_assignable(examination)
    if variant is not None:
        if variant.examination_id != examination.id:
            raise DomainError("variant_mismatch", status_code=400)
        if not variant.variant_questions.exists():
            raise DomainError("variant_empty", status_code=400)
    pool = usable_variants(examination)
    created, skipped = [], []
    for student in students:
        try:
            with transaction.atomic():
                a, was_created = ExamAssignment.objects.get_or_create(
                    examination=examination, student=student,
                    defaults=dict(
                        variant=variant or random.choice(pool), group=group, assigned_by=assigned_by,
                        available_from=available_from, available_until=available_until,
                        origin_result=origin_result,
                    ),
                )
        except IntegrityError:
            a, was_created = ExamAssignment.objects.get(examination=examination, student=student), False
        (created if was_created else skipped).append(a if was_created else student)
    return created, skipped


# --------------------------------------------------------------------------- start / resume
def _shuffle_within_blocks(vqs, rng):
    """Every student gets a different order, but each exercise stays together under its heading: questions are
    shuffled inside a block (same exercise = same category + instruction), the blocks keep their order, and
    questions on a reading / listening text keep the text's order (they follow it)."""
    blocks, key_of = [], None
    for vq in vqs:
        q = vq.question
        key = ("p", q.passage_id) if q.passage_id else ("c", q.category, q.instruction) if q.category or q.instruction else ("s", q.section)
        if not blocks or key != key_of:
            blocks.append([])
            key_of = key
        blocks[-1].append(vq.question_id)
    by_id = {vq.question_id: vq.question for vq in vqs}
    out = []
    for block in blocks:
        if not by_id[block[0]].passage_id:
            rng.shuffle(block)
        out.extend(block)
    return out


def _build_layout(attempt_seed, examination, variant):
    rng = random.Random(attempt_seed)
    vqs = list(variant.variant_questions.select_related("question").prefetch_related("question__options"))
    qids = [vq.question_id for vq in vqs]
    if examination.shuffle_questions:
        qids = _shuffle_within_blocks(vqs, rng)
    by_id = {vq.question_id: vq.question for vq in vqs}
    options, matches = {}, {}
    for qid in qids:
        q = by_id[qid]
        opt_ids = [o.id for o in q.options.all()]
        if q.question_type == QuestionType.MATCH:
            right = [o.match_text for o in q.options.all()]
            rng.shuffle(right)  # right-hand column is always shuffled, otherwise it leaks the answer
            matches[str(qid)] = right
            if examination.shuffle_options:
                rng.shuffle(opt_ids)
        elif examination.shuffle_options and q.question_type != QuestionType.TRUE_FALSE:
            rng.shuffle(opt_ids)
        options[str(qid)] = opt_ids
    return {"questions": qids, "options": options, "matches": matches}


def ensure_window_open(assignment, now=None):
    now = now or timezone.now()
    if assignment.available_from and now < assignment.available_from:
        raise DomainError("exam_not_open_yet")
    if assignment.available_until and now > assignment.available_until:
        raise DomainError("exam_window_closed")


LAST_SEEN_EVERY = timedelta(seconds=15)


def check_device(attempt, request):
    """One test = one device. The first device that touches the running test owns it; another device is refused
    (staff can release it). Requests without a device id (old clients, scripts) are only allowed when unbound."""
    from apps.accounts.sessions import device_headers, device_label

    if request is None or attempt.status != AttemptStatus.IN_PROGRESS:
        return attempt
    did, _name = device_headers(request)
    now = timezone.now()
    if not attempt.device_id:
        if did:
            ExamAttempt.objects.filter(pk=attempt.pk, device_id="").update(device_id=did, device_label=device_label(request)[:160], last_seen_at=now)
            attempt.refresh_from_db(fields=["device_id", "device_label", "last_seen_at"])
            if attempt.device_id != did:
                return check_device(attempt, request)  # another device won the race
        return attempt
    if did != attempt.device_id:
        if not AttemptViolation.objects.filter(attempt=attempt, kind=ViolationKind.OTHER_DEVICE, created_at__gte=now - timedelta(minutes=1)).exists():
            _log(attempt, ViolationKind.OTHER_DEVICE, device_label(request))
        raise DomainError("attempt_other_device", status_code=409)
    if attempt.last_seen_at is None or now - attempt.last_seen_at > LAST_SEEN_EVERY:
        ExamAttempt.objects.filter(pk=attempt.pk).update(last_seen_at=now)
        attempt.last_seen_at = now
    return attempt


@transaction.atomic
def release_device(attempt_id, *, actor):
    """Staff let the student continue the running test on another computer."""
    from apps.audit.services import record

    attempt = ExamAttempt.objects.select_for_update(of=("self",)).select_related("student__user").get(pk=attempt_id)
    if attempt.status not in (AttemptStatus.IN_PROGRESS, AttemptStatus.PENDING_TEACHER_APPROVAL):
        raise DomainError("attempt_not_running")
    old = attempt.device_label
    attempt.device_id, attempt.device_label = "", ""
    attempt.save(update_fields=["device_id", "device_label"])
    _log(attempt, ViolationKind.DEVICE_RELEASED, old, actor=actor)
    record("attempt.device_released", actor=actor, target=attempt.student, target_type="attempt",
           detail={"attempt": attempt.pk, "device": old})
    return attempt


@transaction.atomic
def start_attempt(*, assignment_id, student, started_by, request=None):
    """Idempotent start. Returns the existing attempt on refresh/reconnect – never a second one."""
    assignment = (
        ExamAssignment.objects.select_for_update(of=("self",))
        .select_related("examination", "variant")
        .filter(pk=assignment_id, student=student)
        .first()
    )
    if assignment is None:
        raise DomainError("assignment_not_found", status_code=404)

    existing = ExamAttempt.objects.filter(assignment=assignment).first()
    if existing:
        existing = expire_if_needed(existing)
        if existing.is_pending_approval:
            raise DomainError("attempt_pending_approval")
        if existing.is_finished:
            raise DomainError("attempt_already_finished")
        return check_device(existing, request)

    exam = assignment.examination
    if not exam.is_published:
        raise DomainError("exam_not_published")
    ensure_window_open(assignment)

    now = timezone.now()
    attempt = ExamAttempt.objects.create(
        assignment=assignment, student=student, examination=exam, variant=assignment.variant,
        started_at=now, deadline_at=now + timedelta(minutes=exam.duration_minutes),
        started_by=started_by, layout={},
    )
    attempt.layout = _build_layout(f"attempt-{attempt.pk}", exam, assignment.variant)
    attempt.save(update_fields=["layout"])
    return check_device(attempt, request)


# --------------------------------------------------------------------------- answers
def expire_if_needed(attempt):
    """Auto-submit when the deadline passed. Safe to call on every request."""
    if attempt.status != AttemptStatus.IN_PROGRESS:
        return attempt
    now = timezone.now()
    if now >= attempt.deadline_at:
        return submit_attempt(attempt.pk, auto=True).attempt
    if attempt.violation_deadline_at and now >= attempt.violation_deadline_at + _violation_grace():
        return terminate_attempt(attempt.pk)
    return attempt


def seconds_remaining(attempt):
    if attempt.is_pending_approval:
        return attempt.paused_remaining_seconds or 0
    if attempt.is_finished:
        return 0
    return max(0, int((attempt.deadline_at - timezone.now()).total_seconds()))


def save_answers(attempt, items):
    """Persist (autosave) answers. ``items`` = [{"question_id": int, "answer": {...}}]."""
    grace = timedelta(seconds=settings.EXAM_SUBMIT_GRACE_SECONDS)
    if attempt.is_pending_approval:
        raise DomainError("attempt_pending_approval")
    if attempt.is_finished:
        raise DomainError("attempt_already_finished")
    if timezone.now() > attempt.deadline_at + grace:
        expire_if_needed(attempt)
        raise DomainError("time_expired")

    layout_ids = set(attempt.layout.get("questions", []))
    questions = {
        q.id: q for q in attempt.variant.questions.filter(id__in=[i["question_id"] for i in items])
        .prefetch_related("options")
    }
    saved = []
    with transaction.atomic():
        for item in items:
            qid = item["question_id"]
            q = questions.get(qid)
            if q is None or qid not in layout_ids:
                raise DomainError("question_not_in_attempt", status_code=400)
            try:
                clean = validate_answer_shape(q.question_type, item["answer"], [o.id for o in q.options.all()])
            except ValueError as exc:
                raise DomainError("invalid_answer", str(exc), status_code=400)
            StudentAnswer.objects.update_or_create(attempt=attempt, question=q, defaults={"answer": clean})
            saved.append(qid)
    return saved


# --------------------------------------------------------------------------- submit
@transaction.atomic
def submit_attempt(attempt_id, *, auto=False):
    """Finish the attempt and evaluate it. Idempotent: a second call returns the same result."""
    from apps.results.services import evaluate_attempt  # local import avoids a cycle

    attempt = ExamAttempt.objects.select_for_update(of=("self",)).select_related("examination", "variant").get(pk=attempt_id)
    if attempt.is_finished:
        return attempt.result
    if attempt.is_pending_approval:
        raise DomainError("attempt_pending_approval")
    now = timezone.now()
    expired = now >= attempt.deadline_at
    attempt.status = AttemptStatus.AUTO_SUBMITTED if (auto or expired) else AttemptStatus.SUBMITTED
    attempt.finished_at = min(now, attempt.deadline_at) if (auto or expired) else now
    attempt.save(update_fields=["status", "finished_at"])
    return evaluate_attempt(attempt)


def sweep_expired_attempts():
    """Background safety net (Celery beat): auto-submit every overdue attempt."""
    ids = list(
        ExamAttempt.objects.filter(status=AttemptStatus.IN_PROGRESS, deadline_at__lte=timezone.now())
        .values_list("id", flat=True)
    )
    for pk in ids:
        submit_attempt(pk, auto=True)
    # Students who left fullscreen and never came back (closed the tab, lost the network ...)
    overdue = list(
        ExamAttempt.objects.filter(
            status=AttemptStatus.IN_PROGRESS, violation_deadline_at__lte=timezone.now() - _violation_grace()
        ).values_list("id", flat=True)
    )
    for pk in overdue:
        terminate_attempt(pk)
    return len(ids) + len(overdue)


# --------------------------------------------------------------------------- fullscreen enforcement
# The browser only *reports* what it sees. Every decision (deadline, termination, resume) is taken here.
def _violation_seconds():
    return getattr(settings, "FULLSCREEN_VIOLATION_SECONDS", 10)


def _violation_grace():
    return timedelta(seconds=getattr(settings, "FULLSCREEN_NETWORK_GRACE_SECONDS", 2))


def _log(attempt, kind, detail="", actor=None):
    AttemptViolation.objects.create(attempt=attempt, kind=kind, detail=detail[:200], actor=actor)


@transaction.atomic
def report_fullscreen(attempt_id, *, ok, reason=""):
    """The client says it is (ok=True) or is not (ok=False) in fullscreen on the test page."""
    attempt = ExamAttempt.objects.select_for_update(of=("self",)).get(pk=attempt_id)
    if attempt.status != AttemptStatus.IN_PROGRESS:
        return attempt
    now = timezone.now()
    if now >= attempt.deadline_at:
        return attempt  # the normal expiry path submits it
    if attempt.violation_deadline_at and now >= attempt.violation_deadline_at + _violation_grace():
        return terminate_attempt(attempt.pk)  # too late, even if the student reports "ok" now
    if ok:
        if attempt.violation_deadline_at:
            attempt.violation_deadline_at = None
            attempt.save(update_fields=["violation_deadline_at"])
            _log(attempt, ViolationKind.RETURNED)
    elif attempt.violation_deadline_at is None:
        attempt.violation_deadline_at = now + timedelta(seconds=_violation_seconds())
        attempt.save(update_fields=["violation_deadline_at"])
        kind = {"hidden": ViolationKind.TAB_HIDDEN, "unsupported": ViolationKind.NOT_SUPPORTED}.get(
            reason, ViolationKind.FULLSCREEN_EXIT
        )
        _log(attempt, kind, reason)
    return attempt


@transaction.atomic
def terminate_attempt(attempt_id):
    """Stop the test: answers stay saved, the clock is frozen and a teacher has to decide."""
    attempt = ExamAttempt.objects.select_for_update(of=("self",)).get(pk=attempt_id)
    if attempt.status != AttemptStatus.IN_PROGRESS:
        return attempt
    started = (
        attempt.violation_deadline_at - timedelta(seconds=_violation_seconds())
        if attempt.violation_deadline_at else timezone.now()
    )
    attempt.status = AttemptStatus.PENDING_TEACHER_APPROVAL
    attempt.terminated_at = timezone.now()
    attempt.paused_remaining_seconds = max(0, int((attempt.deadline_at - started).total_seconds()))
    attempt.violation_deadline_at = None
    attempt.save(update_fields=["status", "terminated_at", "paused_remaining_seconds", "violation_deadline_at"])
    _log(attempt, ViolationKind.TERMINATED, f"{attempt.answers.count()} answers saved")
    from apps.audit.services import record

    record("attempt.terminated", actor=None, target=attempt.student, target_type="attempt",
           detail={"attempt": attempt.pk, "exam": attempt.examination.title, "answers": attempt.answers.count()})
    return attempt


@transaction.atomic
def resume_attempt(attempt_id, *, actor):
    """A teacher lets the student continue with the time that was left."""
    attempt = ExamAttempt.objects.select_for_update(of=("self",)).get(pk=attempt_id)
    if not attempt.is_pending_approval:
        raise DomainError("attempt_not_pending")
    remaining = max(attempt.paused_remaining_seconds or 0, 60)
    attempt.status = AttemptStatus.IN_PROGRESS
    attempt.deadline_at = timezone.now() + timedelta(seconds=remaining)
    attempt.paused_remaining_seconds = None
    attempt.violation_deadline_at = None
    attempt.resume_count += 1
    attempt.device_id, attempt.device_label = "", ""  # the student may come back on another computer
    attempt.save(update_fields=["status", "deadline_at", "paused_remaining_seconds", "violation_deadline_at", "resume_count",
                                "device_id", "device_label"])
    _log(attempt, ViolationKind.RESUMED, actor=actor)
    from apps.audit.services import record

    record("attempt.resumed", actor=actor, target=attempt.student, target_type="attempt",
           detail={"attempt": attempt.pk, "exam": attempt.examination.title, "minutes_left": round(remaining / 60)})
    return attempt


@transaction.atomic
def finalize_attempt(attempt_id, *, actor):
    """A teacher closes the stopped test: it is graded with the answers that were saved."""
    from apps.results.services import evaluate_attempt

    attempt = ExamAttempt.objects.select_for_update(of=("self",)).select_related("examination", "variant").get(pk=attempt_id)
    if not attempt.is_pending_approval:
        raise DomainError("attempt_not_pending")
    attempt.status = AttemptStatus.SUBMITTED
    attempt.finished_at = attempt.terminated_at or timezone.now()
    attempt.save(update_fields=["status", "finished_at"])
    _log(attempt, ViolationKind.FINALIZED, actor=actor)
    from apps.audit.services import record

    record("attempt.finalized", actor=actor, target=attempt.student, target_type="attempt",
           detail={"attempt": attempt.pk, "exam": attempt.examination.title})
    return evaluate_attempt(attempt)


def assign_group_members(examination, group, *, assigned_by, students=None):
    """A group was given this exam: every student of the group gets it - being in the group is what counts,
    not the level on the student's profile. ``students`` limits it to some members (a student who just joined
    with the group code). Returns the created assignments."""
    if not examination.is_published or not usable_variants(examination):
        return []
    members = list(group.students.all()) if students is None else students
    created, _ = create_assignments(examination=examination, students=members, group=group, assigned_by=assigned_by)
    return created
