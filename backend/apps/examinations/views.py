from django.db import transaction
from django.utils import timezone
from django.db.models import ProtectedError, Q
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role
from apps.accounts.tokens import issue_kiosk_token
from apps.academics.models import Group, Level
from apps.core.exceptions import DomainError
from apps.core.permissions import IsAdmin, IsAdminOrReceptionist, IsAdminOrTeacher, IsStudent, IsStaffRole
from apps.questions.models import Question
from apps.students.models import StudentProfile
from apps.students.selectors import students_for

from . import services
from .models import AttemptStatus, ExamAssignment, ExamAttempt, ExamKind, ExamStatus, Examination, ExaminationVariant, GroupExam, VariantQuestion
from .serializers import (
    AnswersPayloadSerializer, AssignSerializer, ExamAssignmentSerializer, ExaminationSerializer,
    MyAssignmentSerializer, VariantSerializer, build_attempt_payload,
)


def exams_for(user, editable=False):
    """Exams the user may see. A teacher also sees the exams the admin gave to one of their groups,
    but may only assign those to students - ``editable=True`` leaves them out (questions, settings, delete)."""
    qs = Examination.objects.select_related("level", "target_level", "created_by")
    if user.role == Role.ADMIN:
        return qs
    if user.role == Role.TEACHER:
        mine = Q(created_by=user) | Q(teachers=user)
        if not editable:
            mine |= Q(group_grants__group__teacher__user=user)
        return qs.filter(mine).distinct()
    if user.role == Role.RECEPTIONIST:
        return qs.filter(kind=ExamKind.PLACEMENT)
    return qs.none()


class ExaminationViewSet(viewsets.ModelViewSet):
    serializer_class = ExaminationSerializer
    filterset_fields = ["kind", "level", "target_level", "status"]
    search_fields = ["title"]
    ordering_fields = ["created_at", "title", "level__order"]
    ordering = ["kind", "level__order", "-created_at"]  # placement tests first, by level; then upgrade exams, newest first

    def get_queryset(self):
        return exams_for(self.request.user, editable=self.action in ("update", "partial_update", "destroy", "publish", "unpublish"))

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [IsStaffRole()]
        if self.action == "revoke_group":
            return [IsAdmin()]
        return [IsAdminOrTeacher()]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def destroy(self, request, *args, **kwargs):
        exam = self.get_object()
        if exam.attempts.exists():
            raise DomainError("exam_has_attempts")
        title, pk_ = exam.title, exam.pk
        try:
            resp = super().destroy(request, *args, **kwargs)
        except ProtectedError:
            raise DomainError("exam_has_attempts")
        from apps.audit.services import record

        record("exam.deleted", target_type="examination", target_label=title, detail={"id": pk_})
        return resp

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        exam = self.get_object()
        if not services.usable_variants(exam):
            raise DomainError("exam_has_no_questions")
        exam.status = ExamStatus.PUBLISHED
        exam.save(update_fields=["status"])
        return Response(self.get_serializer(exam).data)

    @action(detail=True, methods=["post"])
    def unpublish(self, request, pk=None):
        exam = self.get_object()
        exam.status = ExamStatus.DRAFT
        exam.save(update_fields=["status"])
        return Response(self.get_serializer(exam).data)

    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        exam = self.get_object()
        user = request.user
        if exam.kind == ExamKind.PLACEMENT and user.role != Role.ADMIN:
            raise DomainError("placement_via_reception", status_code=403)
        s = AssignSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data
        if user.role == Role.ADMIN and exam.kind == ExamKind.UPGRADE and request.data.get("to") != "students":
            return self._give_to_groups(exam, data, user)

        allowed = students_for(user)
        groups = Group.objects.filter(id__in=data["group_ids"])
        if user.role == Role.TEACHER:
            groups = groups.filter(teacher__user=user)
            if not exams_for(user, editable=True).filter(pk=exam.pk).exists():
                # an exam the admin gave to some of my groups: only those groups and their students
                granted = Group.objects.filter(exam_grants__examination=exam, teacher__user=user)
                allowed = allowed.filter(groups__in=granted).distinct()
                groups = groups.filter(pk__in=granted)
        direct = list(allowed.filter(id__in=data["student_ids"]))
        if len(direct) != len(set(data["student_ids"])):
            raise DomainError("student_not_accessible", status_code=403)
        groups = list(groups)
        if len(groups) != len(set(data["group_ids"])):
            raise DomainError("group_not_accessible", status_code=403)

        kwargs = dict(examination=exam, assigned_by=user, variant=data.get("variant"),
                      available_from=data.get("available_from"), available_until=data.get("available_until"))
        created = skipped = 0
        mismatched = []
        seen = set()
        batches = [(None, direct)] + [(g, list(g.students.select_related("user", "current_level", "initial_level"))) for g in groups]
        with transaction.atomic():
            for group, students in batches:
                eligible = []
                for st in students:
                    if st.id in seen:
                        continue
                    seen.add(st.id)
                    effective = st.current_level or st.initial_level  # not placed yet: the level estimated at registration
                    if exam.kind == ExamKind.UPGRADE and effective is not None and effective.id != exam.level_id:  # no level yet: may sit it
                        mismatched.append({"name": st.user.full_name, "level": effective.code if effective else None})
                        continue
                    eligible.append(st)
                c, sk = services.create_assignments(students=eligible, group=group, **kwargs)
                created += len(c)
                skipped += len(sk)
        return Response({"created": created, "skipped_existing": skipped, "skipped_level_mismatch": mismatched},
                        status=status.HTTP_201_CREATED)

    def _give_to_groups(self, exam, data, user):
        """Admin gives an upgrade exam to groups: every student of the group (at the exam's level) gets it now,
        and students who join the group later get it too (see signals)."""
        from apps.audit.services import record

        if data["student_ids"]:
            raise DomainError("admin_assigns_groups", status_code=400)
        if not exam.is_published:
            raise DomainError("exam_not_published")
        groups = list(Group.objects.filter(id__in=data["group_ids"], is_active=True).select_related("level", "teacher__user"))
        if len(groups) != len(set(data["group_ids"])):
            raise DomainError("group_not_accessible", status_code=403)
        added, existing, mismatched, no_teacher, students = [], 0, [], [], 0
        with transaction.atomic():
            for g in groups:
                if g.level_id != exam.level_id:
                    mismatched.append({"name": g.name, "level": g.level.code})
                    continue
                _, made = GroupExam.objects.get_or_create(examination=exam, group=g, defaults={"assigned_by": user})
                students += len(services.assign_group_members(exam, g, assigned_by=user))  # also fills in newcomers
                if not made:
                    existing += 1
                    continue
                added.append(g.name)
                if g.teacher_id is None:
                    no_teacher.append(g.name)
            if added or students:
                record("exam.given_to_groups", actor=user, target_type="examination", target_label=exam.title,
                       detail={"groups": added or [g.name for g in groups if g.level_id == exam.level_id], "students": students})
        return Response({"groups_added": len(added), "groups_existing": existing, "groups_level_mismatch": mismatched,
                         "groups_without_teacher": no_teacher, "students_assigned": students}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def groups(self, request, pk=None):
        """Groups this exam was given to, with how many of each group's students the teacher has assigned."""
        exam = self.get_object()
        grants = exam.group_grants.select_related("group__level", "group__teacher__user", "assigned_by")
        if request.user.role == Role.TEACHER:
            grants = grants.filter(group__teacher__user=request.user)
        rows = []
        for gr in grants:
            g = gr.group
            members = g.students.values_list("id", flat=True)
            rows.append({
                "group": g.id, "name": g.name, "level": g.level.code,
                "teacher": g.teacher.user.full_name if g.teacher_id else None,
                "students": len(members),
                "assigned": exam.assignments.filter(student_id__in=list(members)).count(),
                "given_by": gr.assigned_by.full_name if gr.assigned_by_id else None, "given_at": gr.created_at,
            })
        return Response(rows)

    @action(detail=True, methods=["post"], url_path="revoke-group")
    def revoke_group(self, request, pk=None):
        """Admin takes the exam back from a group. Assignments the teacher already made stay."""
        from apps.audit.services import record

        exam = self.get_object()
        gr = exam.group_grants.select_related("group").filter(group_id=request.data.get("group")).first()
        if gr is None:
            raise DomainError("not_found", status_code=404)
        name = gr.group.name
        gr.delete()
        record("exam.taken_from_group", actor=request.user, target_type="examination", target_label=exam.title,
               detail={"group": name})
        return Response(status=status.HTTP_204_NO_CONTENT)


class VariantViewSet(viewsets.ModelViewSet):
    serializer_class = VariantSerializer
    permission_classes = [IsAdminOrTeacher]
    filterset_fields = ["examination"]
    pagination_class = None

    def get_queryset(self):
        return ExaminationVariant.objects.filter(
            examination__in=exams_for(self.request.user, editable=self.action not in ("list", "retrieve"))
        ).select_related("examination").prefetch_related("variant_questions__question")

    def _assert_unlocked(self, variant):
        if variant.examination.attempts.exists():
            raise DomainError("exam_has_attempts")

    def destroy(self, request, *args, **kwargs):
        variant = self.get_object()
        self._assert_unlocked(variant)
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            raise DomainError("variant_has_assignments")

    @action(detail=True, methods=["post"])
    def duplicate(self, request, pk=None):
        """A new variant with copies of every question: the copies can be edited without touching the original."""
        from apps.audit.services import record
        from apps.questions.models import AnswerOption

        src = self.get_object()
        self._assert_unlocked(src)
        exam = src.examination
        used = set(exam.variants.values_list("name", flat=True))
        name = next((c for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if c not in used), None)
        if name is None:
            name = next(f"{src.name} ({i})" for i in range(2, 999) if f"{src.name} ({i})" not in used)
        with transaction.atomic():
            new = ExaminationVariant.objects.create(examination=exam, name=name[:50], order=(max((v.order for v in exam.variants.all()), default=0) + 1))
            links = list(src.variant_questions.select_related("question").prefetch_related("question__options"))
            for vq in links:
                q = vq.question
                options = list(q.options.all())
                q.pk = None
                q.id = None
                q._state.adding = True
                q.created_by = request.user
                q.save()
                AnswerOption.objects.bulk_create([
                    AnswerOption(question=q, text=o.text, match_text=o.match_text, is_correct=o.is_correct, order=o.order)
                    for o in options
                ])
                VariantQuestion.objects.create(variant=new, question=q, order=vq.order)
        record("variant.duplicated", target=exam, detail={"from": src.name, "to": new.name, "questions": len(links)})
        return Response(self.get_serializer(self.get_queryset().get(pk=new.pk)).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"], url_path="import-template")
    def import_template(self, request):
        from django.http import HttpResponse

        from apps.questions.importer import template_xlsx

        resp = HttpResponse(template_xlsx(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        resp["Content-Disposition"] = 'attachment; filename="questions-template.xlsx"'
        return resp

    @action(detail=True, methods=["post"], url_path="import", parser_classes=[MultiPartParser])
    def import_file(self, request, pk=None):
        """Upload an Excel / CSV / PDF / TXT test file: questions are created and added to this variant."""
        from apps.questions.importer import ImportErrorList, import_questions

        variant = self.get_object()
        self._assert_unlocked(variant)
        upload = request.FILES.get("file")
        if upload is None:
            raise DomainError("file_required", status_code=400)
        exam = variant.examination
        level = Level.objects.filter(pk=request.data.get("level") or exam.level_id).first() or exam.level
        try:
            created, skipped = import_questions(
                upload, user=request.user, default_level=level, default_section=request.data.get("section") or "GRAMMAR",
                variant=variant, audio=request.FILES.get("audio"))
        except ImportErrorList as exc:
            return Response({"code": "import_failed", "detail": "Import failed.", "errors": exc.errors}, status=400)
        return Response({"created": len(created), "skipped": skipped,
                         "variant": VariantSerializer(self.get_queryset().get(pk=variant.pk)).data},
                        status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="text-import", parser_classes=[MultiPartParser, JSONParser])
    def text_import(self, request, pk=None):
        """Paste-in import: ``text`` = the exam as copied, ``answers`` = the key. ``save=false`` only previews."""
        from apps.questions.importer import ImportErrorList, import_rows
        from apps.questions.text_import import build

        variant = self.get_object()
        text, answers = str(request.data.get("text", "")), str(request.data.get("answers", ""))
        if not text.strip():
            raise DomainError("text_required", status_code=400)
        audio = request.FILES.get("audio")
        preview, rows = build(text, answers, has_audio=audio is not None)
        if request.data.get("save") not in (True, "true", "1", 1):
            preview["ready"] = len(rows)
            return Response(preview)
        self._assert_unlocked(variant)
        if not rows:
            raise DomainError("nothing_to_import", status_code=400)
        try:
            created, skipped = import_rows(rows, user=request.user, default_level=variant.examination.level, variant=variant, audio=audio)
        except ImportErrorList as exc:
            return Response({"code": "import_failed", "detail": "Import failed.", "errors": exc.errors}, status=400)
        missing = sum(1 for s in preview["sections"] for q in s["questions"] if q["status"] != "ok")
        return Response({"created": len(created), "skipped": skipped, "missing_answers": missing}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["put"])
    def questions(self, request, pk=None):
        variant = self.get_object()
        self._assert_unlocked(variant)
        ids = request.data.get("question_ids")
        if not isinstance(ids, list) or len(set(ids)) != len(ids) or not all(isinstance(i, int) for i in ids):
            raise DomainError("invalid_question_ids", status_code=400)
        user = request.user
        visible = Question.objects.filter(id__in=ids, is_active=True)
        if user.role != Role.ADMIN:
            visible = visible.filter(Q(created_by=user) | Q(created_by__role=Role.ADMIN))
        if visible.count() != len(ids):
            raise DomainError("question_not_accessible", status_code=400)
        with transaction.atomic():
            variant.variant_questions.all().delete()
            VariantQuestion.objects.bulk_create(
                [VariantQuestion(variant=variant, question_id=qid, order=i) for i, qid in enumerate(ids)]
            )
        variant = self.get_queryset().get(pk=variant.pk)
        return Response(self.get_serializer(variant).data)


class AssignmentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin,
                        mixins.DestroyModelMixin, viewsets.GenericViewSet):
    serializer_class = ExamAssignmentSerializer
    permission_classes = [IsAdminOrTeacher]
    filterset_fields = ["examination", "student", "group", "examination__kind"]
    search_fields = ["student__user__first_name", "student__user__last_name", "examination__title"]
    ordering_fields = ["created_at", "available_from"]
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_queryset(self):
        return ExamAssignment.objects.filter(examination__in=exams_for(self.request.user)).select_related(
            "examination__level", "examination__target_level", "student__user", "variant", "group", "attempt__result"
        )

    def destroy(self, request, *args, **kwargs):
        a = self.get_object()
        if hasattr(a, "attempt"):
            raise DomainError("assignment_has_attempt")
        return super().destroy(request, *args, **kwargs)


# --------------------------------------------------------------------------- student side
class MyAssignmentsView(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = MyAssignmentSerializer
    permission_classes = [IsStudent]
    kiosk_ok = True  # the instructions screen of a follow-up placement exam reads it
    pagination_class = None

    def get_queryset(self):
        return ExamAssignment.objects.filter(
            student__user=self.request.user, examination__status=ExamStatus.PUBLISHED
        ).select_related("examination__level", "examination__target_level", "variant", "attempt__result")


class AttemptAccessMixin:
    permission_classes = [IsStudent]
    kiosk_ok = True

    def get_attempt(self, pk):
        attempt = ExamAttempt.objects.select_related(
            "examination__level", "examination__target_level", "variant", "student__user"
        ).filter(pk=pk, student__user=self.request.user).first()
        if attempt is None:
            raise DomainError("attempt_not_found", status_code=404)
        return services.check_device(services.expire_if_needed(attempt), self.request)


class StartAssignmentView(APIView):
    permission_classes = [IsStudent]
    kiosk_ok = True

    def post(self, request, pk):
        student = StudentProfile.objects.get(user=request.user)
        attempt = services.start_attempt(assignment_id=pk, student=student, started_by=request.user, request=request)
        return Response(build_attempt_payload(attempt, request), status=status.HTTP_200_OK)


class AttemptView(AttemptAccessMixin, APIView):
    def get(self, request, pk):
        attempt = self.get_attempt(pk)
        return Response(build_attempt_payload(attempt, request))


class AttemptAnswersView(AttemptAccessMixin, APIView):
    def put(self, request, pk):
        attempt = self.get_attempt(pk)
        s = AnswersPayloadSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        saved = services.save_answers(attempt, s.validated_data["answers"])
        return Response({"saved": saved, "remaining_seconds": services.seconds_remaining(attempt)})


class AttemptSubmitView(AttemptAccessMixin, APIView):
    def post(self, request, pk):
        attempt = self.get_attempt(pk)
        # A final batch of answers may ride along with the submit request.
        if request.data.get("answers"):
            s = AnswersPayloadSerializer(data=request.data)
            s.is_valid(raise_exception=True)
            if not attempt.is_finished:
                try:
                    services.save_answers(attempt, s.validated_data["answers"])
                except DomainError as exc:
                    if exc.code != "time_expired":
                        raise
        result = services.submit_attempt(attempt.pk)
        return Response({"result_id": result.id})


class AttemptFullscreenView(AttemptAccessMixin, APIView):
    """The browser reports fullscreen state; the server owns the deadline and the termination."""

    def post(self, request, pk):
        attempt = self.get_attempt(pk)
        ok = bool(request.data.get("ok"))
        reason = str(request.data.get("reason", ""))[:40]
        attempt = services.report_fullscreen(attempt.pk, ok=ok, reason=reason)
        attempt = services.expire_if_needed(attempt)
        left = (
            max(0, int((attempt.violation_deadline_at - timezone.now()).total_seconds()))
            if attempt.violation_deadline_at else None
        )
        return Response({
            "status": attempt.status, "violation_seconds_left": left,
            "result_id": attempt.result.id if attempt.is_finished and hasattr(attempt, "result") else None,
        })


def attempts_for(user):
    qs = ExamAttempt.objects.select_related("student__user", "examination__level", "assignment")
    if user.role == Role.ADMIN:
        return qs
    return qs.filter(Q(examination__in=exams_for(user)) | Q(student__in=students_for(user))).distinct()


class StoppedAttemptViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Tests stopped because of a fullscreen violation – staff resume or finalise them."""

    permission_classes = [IsStaffRole]

    def get_queryset(self):
        user = self.request.user
        if user.role == Role.RECEPTIONIST:
            # placement tests are run at the front desk: walk-in guests come back to the receptionist, not the admin
            qs = ExamAttempt.objects.select_related("student__user", "examination__level", "assignment").filter(examination__kind=ExamKind.PLACEMENT)
        else:
            qs = attempts_for(user).exclude(student__is_guest=True)
        return qs.filter(status=AttemptStatus.PENDING_TEACHER_APPROVAL).order_by("-terminated_at")

    def list(self, request, *args, **kwargs):
        services.sweep_expired_attempts()  # also covers students who never came back (no background worker needed)
        rows = []
        for a in self.get_queryset().prefetch_related("violations"):
            rows.append({
                "id": a.id, "student": a.student.user.get_full_name() or a.student.user.username,
                "student_id": a.student_id, "is_guest": a.student.is_guest, "assignment_id": a.assignment_id, "examination": a.examination.title, "level": a.examination.level.code,
                "kind": a.examination.kind, "terminated_at": a.terminated_at,
                "remaining_seconds": a.paused_remaining_seconds or 0, "answered": a.answers.count(),
                "total": len(a.layout.get("questions", [])), "resume_count": a.resume_count,
                "violations": [{"kind": v.kind, "at": v.created_at} for v in a.violations.all()],
            })
        return Response(rows)

    def _get(self, pk):
        a = self.get_queryset().filter(pk=pk).first()
        if a is None:
            raise DomainError("attempt_not_found", status_code=404)
        return a

    @action(detail=True, methods=["post"])
    def resume(self, request, pk=None):
        a = services.resume_attempt(self._get(pk).pk, actor=request.user)
        return Response({"id": a.id, "status": a.status})

    @action(detail=True, methods=["post"])
    def finalize(self, request, pk=None):
        result = services.finalize_attempt(self._get(pk).pk, actor=request.user)
        return Response({"result_id": result.id})


class LiveAttemptViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Tests running right now: who sits which test on which computer and how much time is left."""

    permission_classes = [IsAdminOrReceptionist]
    pagination_class = None

    def get_queryset(self):
        qs = ExamAttempt.objects.select_related("student__user", "examination__level").filter(
            status__in=[AttemptStatus.IN_PROGRESS, AttemptStatus.PENDING_TEACHER_APPROVAL])
        if self.request.user.role == Role.RECEPTIONIST:
            qs = qs.filter(examination__kind=ExamKind.PLACEMENT)
        return qs.order_by("started_at")

    def list(self, request, *args, **kwargs):
        from django.db.models import Count

        services.sweep_expired_attempts()
        now = timezone.now()
        rows = []
        for a in self.get_queryset().annotate(n_answers=Count("answers")):
            seen = a.last_seen_at
            rows.append({
                "id": a.id, "student": a.student.user.full_name, "student_id": a.student_id, "is_guest": a.student.is_guest,
                "examination": a.examination.title, "level": a.examination.level.code, "kind": a.examination.kind,
                "status": a.status, "started_at": a.started_at, "deadline_at": a.deadline_at,
                "remaining_seconds": services.seconds_remaining(a), "answered": a.n_answers,
                "total": len(a.layout.get("questions", [])), "device": a.device_label, "last_seen_at": seen,
                "online": bool(seen and (now - seen).total_seconds() <= 45),
                "violation": a.violation_deadline_at is not None,
            })
        return Response({"server_time": now, "attempts": rows})

    @action(detail=True, methods=["post"], url_path="release-device")
    def release_device(self, request, pk=None):
        a = self.get_queryset().filter(pk=pk).first()
        if a is None:
            raise DomainError("attempt_not_found", status_code=404)
        services.release_device(a.pk, actor=request.user)
        return Response({"id": a.pk})


# --------------------------------------------------------------------------- receptionist placement
class PlacementViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Receptionists assign placement tests and start them for walk-in students."""

    serializer_class = ExamAssignmentSerializer
    permission_classes = [IsAdminOrReceptionist]
    filterset_fields = ["student"]
    search_fields = ["student__user__first_name", "student__user__last_name", "student__user__phone"]

    def get_queryset(self):
        return ExamAssignment.objects.filter(examination__kind=ExamKind.PLACEMENT).select_related(
            "examination__level", "examination__target_level", "student__user", "variant", "group", "attempt__result"
        )

    def create(self, request):
        student = StudentProfile.objects.filter(pk=request.data.get("student")).first()
        level = Level.objects.filter(pk=request.data.get("level"), is_active=True).first()
        if student is None or level is None:
            raise DomainError("student_or_level_not_found", status_code=404)
        exam = Examination.objects.filter(kind=ExamKind.PLACEMENT, level=level).first()
        if exam is None or not exam.is_published:
            raise DomainError("placement_exam_unavailable")
        created, skipped = services.create_assignments(examination=exam, students=[student], assigned_by=request.user)
        if not created:
            raise DomainError("placement_already_assigned")
        student.initial_level = level
        student.save(update_fields=["initial_level"])
        return Response(self.get_serializer(created[0]).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"])
    def quick(self, request):
        """Walk-in with no registration: pick a level, the test starts immediately."""
        from apps.students.services import create_guest

        level = Level.objects.filter(pk=request.data.get("level"), is_active=True).first()
        if level is None:
            raise DomainError("student_or_level_not_found", status_code=404)
        exam = Examination.objects.filter(kind=ExamKind.PLACEMENT, level=level).first()
        if exam is None or not exam.is_published or not services.usable_variants(exam):
            raise DomainError("placement_exam_unavailable")
        with transaction.atomic():
            guest = create_guest(initial_level=level, registered_by=request.user,
                                 first_name=request.data.get("first_name", ""), last_name=request.data.get("last_name", ""))
            created, _ = services.create_assignments(examination=exam, students=[guest], assigned_by=request.user)
            attempt = services.start_attempt(assignment_id=created[0].id, student=guest, started_by=request.user, request=request)
        return Response({"attempt_id": attempt.id, "kiosk_token": issue_kiosk_token(guest.user),
                         "student_name": guest.user.full_name})

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        assignment = self.get_object()
        attempt = services.start_attempt(
            assignment_id=assignment.id, student=assignment.student, started_by=request.user, request=request
        )
        return Response({
            "attempt_id": attempt.id,
            "kiosk_token": issue_kiosk_token(assignment.student.user),
            "student_name": assignment.student.user.full_name,
        })

