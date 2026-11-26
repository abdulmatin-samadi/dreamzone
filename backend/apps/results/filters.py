import django_filters

from .models import ExamResult


class ResultFilter(django_filters.FilterSet):
    level = django_filters.NumberFilter(field_name="level_id")
    teacher = django_filters.NumberFilter(field_name="examination__created_by_id")
    kind = django_filters.CharFilter(field_name="examination__kind")
    date_from = django_filters.DateFilter(field_name="created_at__date", lookup_expr="gte")
    date_to = django_filters.DateFilter(field_name="created_at__date", lookup_expr="lte")
    group = django_filters.NumberFilter(method="in_group")

    def in_group(self, qs, name, value):
        """Results of the students who are in this group now."""
        return qs.filter(student__memberships__group_id=value).distinct()

    class Meta:
        model = ExamResult
        fields = ["student", "examination", "passed", "approval_status", "offer_status", "writing_pending"]
