from django.db.models import Q
from rest_framework import mixins, serializers, viewsets
from rest_framework.response import Response

from apps.core.permissions import IsAdmin

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = ["id", "actor", "actor_name", "actor_role", "action", "target_type", "target_id", "target_label", "detail", "ip", "created_at"]


class AuditLogViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Admin only: the action log, newest first."""

    permission_classes = [IsAdmin]
    serializer_class = AuditLogSerializer
    filter_backends = []

    def get_queryset(self):
        qs = AuditLog.objects.all()
        p = self.request.query_params
        if p.get("action"):
            qs = qs.filter(action__startswith=p["action"])
        if p.get("actor"):
            qs = qs.filter(actor_id=p["actor"])
        if p.get("date_from"):
            qs = qs.filter(created_at__date__gte=p["date_from"])
        if p.get("date_to"):
            qs = qs.filter(created_at__date__lte=p["date_to"])
        if p.get("search"):
            for word in p["search"].split():
                qs = qs.filter(Q(target_label__icontains=word) | Q(actor_name__icontains=word))
        return qs

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.get_queryset())
        return self.get_paginated_response(self.get_serializer(page, many=True).data)


class AuditActionsView(viewsets.ViewSet):
    permission_classes = [IsAdmin]

    def list(self, request):
        return Response(sorted(AuditLog.objects.values_list("action", flat=True).distinct()))
