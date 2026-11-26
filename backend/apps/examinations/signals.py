"""A student who joins a group gets the exams the admin gave to that group."""
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.students.models import StudentGroup


@receiver(post_save, sender=StudentGroup)
def give_group_exams_to_newcomer(sender, instance, created, **kwargs):
    if not created:
        return
    from .models import GroupExam
    from .services import assign_group_members

    for grant in GroupExam.objects.filter(group_id=instance.group_id).select_related("examination", "group"):
        assign_group_members(grant.examination, grant.group, assigned_by=grant.assigned_by, students=[instance.student])
