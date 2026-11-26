from django.db.models import ProtectedError, Q
from rest_framework import viewsets
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import SAFE_METHODS

from apps.accounts.models import Role
from apps.core.exceptions import DomainError
from apps.core.permissions import IsAdminOrTeacher

from .models import Passage, Question
from .serializers import PassageSerializer, QuestionSerializer


class OwnedContentMixin:
    """Admins manage everything; teachers read admin + own content and edit only their own."""

    permission_classes = [IsAdminOrTeacher]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def scope(self, qs):
        u = self.request.user
        if u.role == Role.ADMIN:
            return qs
        return qs.filter(Q(created_by=u) | Q(created_by__role=Role.ADMIN))

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        if request.method not in SAFE_METHODS and request.user.role != Role.ADMIN and obj.created_by_id != request.user.id:
            self.permission_denied(request, message="You can only modify your own content.")

    def destroy(self, request, *args, **kwargs):
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            raise DomainError("content_in_use")


class QuestionViewSet(OwnedContentMixin, viewsets.ModelViewSet):
    serializer_class = QuestionSerializer
    filterset_fields = ["section", "question_type", "category", "level", "passage", "is_active"]
    search_fields = ["text"]
    ordering_fields = ["created_at", "level__order", "points"]

    def get_queryset(self):
        qs = Question.objects.select_related("level", "passage", "created_by").prefetch_related("options")
        qs = self.scope(qs)
        if "is_active" not in self.request.query_params:
            qs = qs.filter(is_active=True)  # answer-sheet questions of PDF exams are inactive
        if self.request.query_params.get("mine") == "1":
            qs = qs.filter(created_by=self.request.user)
        return qs


class PassageViewSet(OwnedContentMixin, viewsets.ModelViewSet):
    serializer_class = PassageSerializer
    filterset_fields = ["level"]
    search_fields = ["title", "text"]

    def get_queryset(self):
        return self.scope(Passage.objects.select_related("level"))

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
