import re

from django.db import transaction

from apps.accounts.models import Role, User
from apps.accounts.views import generate_password

from .models import StudentGroup, StudentProfile


def _unique_username(phone, first_name):
    base = re.sub(r"\D", "", phone) or re.sub(r"\W", "", first_name.lower()) or "student"
    username, n = base, 1
    while User.objects.filter(username=username).exists():
        n += 1
        username = f"{base}-{n}"
    return username


@transaction.atomic
def create_guest(*, initial_level, registered_by, first_name="", last_name=""):
    """Anonymous walk-in: a login-less account so the exam engine (attempts/results) works unchanged."""
    import uuid

    user = User(username=f"guest-{uuid.uuid4().hex[:10]}", first_name=first_name.strip() or "Mehmon",
                last_name=last_name.strip(), role=Role.STUDENT, language="uz", is_active=True)
    user.set_unusable_password()
    user.save()
    profile = StudentProfile.objects.create(user=user, initial_level=initial_level, registered_by=registered_by, is_guest=True)
    if not last_name.strip():
        user.last_name = f"#{profile.id}"
        user.save(update_fields=["last_name"])
    return profile


@transaction.atomic
def register_student(*, first_name, last_name, phone, initial_level, registered_by, group=None, notes="", password=None):
    """Create the login account and profile. Returns ``(profile, plain_password)``."""
    password = password or generate_password()
    user = User(
        username=_unique_username(phone, first_name), first_name=first_name.strip(), last_name=last_name.strip(),
        phone=phone.strip(), role=Role.STUDENT, language="uz",
    )
    user.set_password(password)
    user.save()
    profile = StudentProfile.objects.create(
        user=user, initial_level=initial_level, registered_by=registered_by, notes=notes,
    )
    if group is not None:
        StudentGroup.objects.create(student=profile, group=group)
    return profile, password
