from django.db.models import ProtectedError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.core.exceptions import DomainError
from apps.core.permissions import IsAdmin, IsAdminOrTeacher, IsAuthenticated, IsStaffRole, IsStudent
from apps.students.models import StudentGroup, StudentProfile

from .models import Group, Level, new_join_code
from .serializers import GroupSerializer, LevelSerializer


class LevelViewSet(viewsets.ModelViewSet):
    serializer_class = LevelSerializer
    queryset = Level.objects.all()
    pagination_class = None
    filterset_fields = ["is_active"]

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [IsAuthenticated()]
        return [IsAdmin()]

    def destroy(self, request, *args, **kwargs):
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            raise DomainError("level_in_use")


class GroupViewSet(viewsets.ModelViewSet):
    serializer_class = GroupSerializer
    filterset_fields = ["level", "teacher", "is_active"]
    # one box: group name, lesson time, teacher name, level (several words narrow the list down)
    search_fields = ["name", "schedule", "teacher__user__first_name", "teacher__user__last_name", "level__code", "level__name"]

    def get_queryset(self):
        qs = Group.objects.select_related("level", "teacher__user")
        u = self.request.user
        if u.role == Role.TEACHER:
            qs = qs.filter(teacher__user=u)
        elif u.role == Role.STUDENT:
            qs = qs.filter(memberships__student__user=u)
        return qs

    def get_permissions(self):
        if self.action == "join":
            return [IsStudent()]
        if self.action == "regenerate_code":
            return [IsAdminOrTeacher()]  # a teacher only reaches their own groups (queryset)
        if self.action == "ranking":
            return [IsStaffRole()]  # a teacher only reaches their own groups (queryset)
        if self.action in ("list", "retrieve", "members"):
            if self.action == "members" and self.request.method != "GET":
                return [IsAdminOrTeacher()]  # admin and the group's teacher (queryset is limited to own groups); not the front desk
            return [IsAuthenticated()]
        return [IsAdmin()]

    def destroy(self, request, *args, **kwargs):
        from apps.audit.services import record

        group = self.get_object()
        label, pk_ = group.name, group.pk
        try:
            resp = super().destroy(request, *args, **kwargs)
        except ProtectedError:
            raise DomainError("group_in_use")
        record("group.deleted", target_type="group", target_label=label, detail={"id": pk_})
        return resp

    @action(detail=True, methods=["get"])
    def ranking(self, request, pk=None):
        """Students of the group ranked by their latest score; the biggest improvers are flagged."""
        from apps.results.models import ExamResult
        from apps.students.models import LevelChangeHistory

        group = self.get_object()
        students = list(group.students.select_related("user", "current_level").filter(user__is_active=True))
        by_student = {}
        for r in (ExamResult.objects.filter(student__in=students, writing_pending=False)
                  .select_related("examination").order_by("created_at")):
            by_student.setdefault(r.student_id, []).append(r)
        ups = {}
        for h in LevelChangeHistory.objects.filter(student__in=students).exclude(reason=LevelChangeHistory.Reason.PLACEMENT).select_related("from_level", "to_level"):
            if h.from_level and h.to_level.order > h.from_level.order:
                ups[h.student_id] = ups.get(h.student_id, 0) + 1
        rows = []
        for st in students:
            res = by_student.get(st.id, [])
            pcts = [float(r.percentage) for r in res]  # ranking / growth compare share of the maximum
            pts = lambda r: {"score": float(r.total_score), "max": float(r.max_score)}
            best = max(res, key=lambda r: r.percentage) if res else None
            rows.append({
                "student_id": st.id, "name": st.user.full_name, "level": st.current_level.code if st.current_level else None,
                "exams": len(res), "latest": pcts[-1] if pcts else None,
                "latest_points": pts(res[-1]) if res else None, "best_points": pts(best) if best else None,
                "average_points": {"score": round(sum(float(r.total_score) for r in res) / len(res), 1),
                                   "max": round(sum(float(r.max_score) for r in res) / len(res), 1)} if res else None,
                "growth": round(pcts[-1] - pcts[0], 1) if len(pcts) >= 2 else None,
                "growth_points": round(float(res[-1].total_score) - float(res[0].total_score), 1) if len(res) >= 2 else None,
                "levels_up": ups.get(st.id, 0),
                "latest_exam": res[-1].examination.title if res else None, "latest_at": res[-1].created_at if res else None,
            })
        rows.sort(key=lambda x: (x["latest"] is None, -(x["latest"] or 0), x["name"]))
        for i, row in enumerate(rows, 1):
            row["rank"] = i if row["latest"] is not None else None
        growers = sorted((r for r in rows if r["levels_up"] > 0 or (r["growth"] or 0) > 0),
                         key=lambda x: (-x["levels_up"], -(x["growth"] or 0)))[:3]
        top = {r["student_id"] for r in growers}
        for row in rows:
            row["top_grower"] = row["student_id"] in top
        return Response({"group": {"id": group.id, "name": group.name, "level": group.level.code}, "students": rows})

    def get_throttles(self):
        if self.action == "join":
            self.throttle_scope = "group_join"  # codes must not be guessable by trying many of them
        return super().get_throttles()

    @action(detail=False, methods=["post"])
    def join(self, request):
        """A student types the code the teacher gave them."""
        code = str(request.data.get("code", "")).strip().upper().replace(" ", "")
        group = Group.objects.select_related("level", "teacher__user").filter(join_code=code, is_active=True).first() if code else None
        if group is None:
            raise DomainError("group_code_invalid", status_code=404)
        student = StudentProfile.objects.get(user=request.user)
        if StudentGroup.objects.filter(student=student, group=group).exists():
            raise DomainError("already_in_group")
        StudentGroup.objects.create(student=student, group=group)
        return Response(GroupSerializer(group, context={"request": request}).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="regenerate-code")
    def regenerate_code(self, request, pk=None):
        group = self.get_object()
        group.join_code = new_join_code()
        group.save(update_fields=["join_code"])
        return Response({"join_code": group.join_code})

    @action(detail=True, methods=["get", "post", "delete"])
    def members(self, request, pk=None):
        group = self.get_object()
        if request.method == "GET":
            from apps.students.serializers import StudentSerializer

            students = group.students.select_related("user", "current_level", "initial_level")
            return Response(StudentSerializer(students, many=True).data)
        student = StudentProfile.objects.filter(pk=request.data.get("student_id")).first()
        if student is None:
            raise DomainError("student_not_found", status_code=404)
        if request.user.role == Role.TEACHER and request.method == "POST":
            # a teacher may take students who have no group yet (or who already study with them)
            free = not student.groups.exists() or student.groups.filter(teacher__user=request.user).exists()
            if not free or student.is_guest:
                raise DomainError("student_not_accessible", status_code=403)
        if request.method == "POST":
            StudentGroup.objects.get_or_create(student=student, group=group)
            return Response(status=status.HTTP_201_CREATED)
        if StudentGroup.objects.filter(student=student, group=group).delete()[0]:
            from apps.audit.services import record

            record("group.member_removed", target=student, detail={"group": group.name})
        return Response(status=status.HTTP_204_NO_CONTENT)
