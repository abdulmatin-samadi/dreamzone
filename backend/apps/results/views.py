from django.http import HttpResponse
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.core.exceptions import DomainError
from apps.core.permissions import IsAdmin, IsAdminOrTeacher, IsAuthenticated, IsTeacherOrReceptionist, role_permission

from . import exports, services
from .filters import ResultFilter
from .selectors import results_for
from .serializers import ResultDetailSerializer, ResultListSerializer, awaiting_decision


class ResultViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    filterset_class = ResultFilter
    search_fields = ["student__user__first_name", "student__user__last_name", "student__user__phone", "examination__title"]
    ordering_fields = ["created_at", "percentage", "total_score"]

    @property
    def kiosk_ok(self):
        # the walk-in student's kiosk token may only read its own result and answer the level offer
        return getattr(self, "action", None) in ("retrieve", "offer")

    def get_queryset(self):
        return results_for(self.request.user)

    def get_serializer_class(self):
        return ResultDetailSerializer if self.action == "retrieve" else ResultListSerializer

    def get_permissions(self):
        if self.action == "writing_queue":
            return [IsTeacherOrReceptionist()]  # guests' writing -> reception, upgrade writing -> teacher
        if self.action == "grade_writing":
            return [role_permission(Role.TEACHER, Role.RECEPTIONIST, Role.ADMIN)()]  # the admin may score any written answer
        if self.action in ("approve", "reject", "export", "grade_speaking", "grade_paper_writing"):
            return [IsAdminOrTeacher()]
        if self.action == "override":
            return [IsAdmin()]
        return [IsAuthenticated()]

    # ---- upgrade workflow
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        result = services.approve_upgrade(self.get_object().pk, user=request.user, note=request.data.get("note", ""))
        return Response(ResultDetailSerializer(result, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        result = services.reject_upgrade(self.get_object().pk, user=request.user, note=request.data.get("note", ""))
        return Response(ResultDetailSerializer(result, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def override(self, request, pk=None):
        note = request.data.get("note", "").strip()
        if not note:
            raise DomainError("note_required", status_code=400)
        result = services.admin_override(
            self.get_object().pk, user=request.user, status=request.data.get("status"), note=note
        )
        return Response(ResultDetailSerializer(result, context={"request": request}).data)

    # ---- writing
    @action(detail=True, methods=["post"], url_path="speaking")
    def grade_speaking(self, request, pk=None):
        result = services.grade_speaking(self.get_object().pk, user=request.user, points=request.data.get("points"),
                                         feedback=request.data.get("feedback", ""), max_points=request.data.get("max"))
        return Response(ResultDetailSerializer(result, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="writing-score")
    def grade_paper_writing(self, request, pk=None):
        result = services.grade_part(self.get_object().pk, "writing", user=request.user, points=request.data.get("points"),
                                     feedback=request.data.get("feedback", ""), max_points=request.data.get("max"))
        return Response(ResultDetailSerializer(result, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="grade-writing")
    def grade_writing(self, request, pk=None):
        grades = request.data.get("grades")
        if not isinstance(grades, list) or not grades:
            raise DomainError("grades_required", status_code=400)
        result = self.get_object()
        if request.user.role != Role.ADMIN and result.examination.kind != services.writing_kind_for(request.user):
            raise DomainError("writing_not_yours", status_code=403)
        result = services.grade_writing(result.pk, user=request.user, grades=grades)
        return Response(ResultDetailSerializer(result, context={"request": request}).data)

    @action(detail=False, methods=["get"], url_path="writing-queue")
    def writing_queue(self, request):
        """Every result still waiting for writing scores, oldest first, with just the unscored answers."""
        qs = self.filter_queryset(self.get_queryset()).filter(
            writing_pending=True, examination__kind=services.writing_kind_for(request.user)).order_by("created_at")
        qs = qs.select_related("attempt__variant").prefetch_related("attempt__answers")
        helper = ResultDetailSerializer(context={"request": request})
        rows = []
        for r in qs[:200]:
            items = [w for w in helper.get_writing(r) if w["needs_review"]]
            if not items:
                continue
            rows.append({"id": r.id, "student": r.student.user.full_name, "student_id": r.student_id,
                         "examination": r.examination.title, "level": r.level.code, "kind": r.examination.kind,
                         "created_at": r.created_at, "writing": items})
        return Response(rows)

    # ---- placement workflow
    @action(detail=True, methods=["post"])
    def offer(self, request, pk=None):
        result = self.get_object()
        if request.user.role not in (Role.STUDENT, Role.RECEPTIONIST, Role.ADMIN):
            raise DomainError("forbidden", status_code=403)
        accept = request.data.get("accept")
        if not isinstance(accept, bool):
            raise DomainError("accept_required", status_code=400)
        result, assignment = services.respond_to_offer(result.pk, accept=accept, user=request.user)
        return Response({
            "result": ResultDetailSerializer(result, context={"request": request}).data,
            "assignment_id": assignment.id if assignment else None,
        })

    # ---- exports (staff only: the files carry points, which students do not see)
    @action(detail=False, methods=["get"])
    def export(self, request):
        _no_students(request)
        results = list(self.filter_queryset(self.get_queryset()))
        kind = request.query_params.get("file", "xlsx")
        if kind == "pdf":
            return _download(exports.results_pdf(results), "results.pdf", "application/pdf")
        return _download(
            exports.results_xlsx(results), "results.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    @action(detail=True, methods=["get"], url_path="export")
    def export_report(self, request, pk=None):
        _no_students(request)
        result = self.get_object()
        hide = request.user.role == Role.STUDENT and awaiting_decision(result)
        return _download(exports.result_report_pdf(result, hide_decision=hide), f"result-{result.pk}.pdf", "application/pdf")


def _download(content, name, ctype):
    resp = HttpResponse(content, content_type=ctype)
    resp["Content-Disposition"] = f'attachment; filename="{name}"'
    return resp


def _no_students(request):
    from rest_framework.exceptions import PermissionDenied

    if request.user.role == Role.STUDENT:
        raise PermissionDenied()
