"""Seed CEFR levels, placement tests (with sample questions) and demo users.

    python manage.py seed_demo            # levels + placement exams + demo users
    python manage.py seed_demo --levels-only
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import Role, TeacherProfile, User
from apps.academics.models import Group, Level
from apps.examinations.models import ExamKind, ExamStatus, Examination, ExaminationVariant, VariantQuestion
from apps.questions.models import AnswerOption, Question, QuestionType, Section
from apps.students.models import StudentGroup, StudentProfile

LEVELS = [
    ("Elementary", "Level 1"), ("Pre-Intermediate", "Level 2"), ("Intermediate", "Level 3"), ("Pre-IELTS", "Level 4"),
]

# (text, section, [(option, correct)...]) – a tiny sample bank per level, enough to try the system out.
SAMPLE = {
    "Elementary": [("She ___ a student.", "GRAMMAR", ["is", "are", "am"], 0), ("A person who teaches is a ___.", "VOCABULARY", ["teacher", "doctor", "driver"], 0)],
    "Pre-Intermediate": [("I ___ to the cinema yesterday.", "GRAMMAR", ["went", "go", "goes"], 0), ("What is the opposite of 'cheap'?", "VOCABULARY", ["expensive", "small", "quick"], 0)],
    "Intermediate": [("If I ___ rich, I would travel.", "GRAMMAR", ["were", "am", "will be"], 0), ("'Reluctant' means ___.", "VOCABULARY", ["unwilling", "eager", "angry"], 0)],
    "Pre-IELTS": [("By next year she ___ here for ten years.", "GRAMMAR", ["will have worked", "works", "worked"], 0), ("'Meticulous' means ___.", "VOCABULARY", ["very careful", "lazy", "noisy"], 0)],
}


class Command(BaseCommand):
    help = "Seed levels, placement exams and demo accounts."

    def add_arguments(self, parser):
        parser.add_argument("--levels-only", action="store_true")

    @transaction.atomic
    def handle(self, *args, **opts):
        levels = {}
        for i, (code, name) in enumerate(LEVELS, start=1):
            levels[code], _ = Level.objects.get_or_create(code=code, defaults={"name": name, "order": i})
        self.stdout.write(self.style.SUCCESS("Levels ready (Elementary … Pre-IELTS)."))
        if opts["levels_only"]:
            return

        admin, created = User.objects.get_or_create(username="admin", defaults=dict(
            first_name="System", last_name="Admin", role=Role.ADMIN, is_superuser=True, language="en"))
        if created:
            admin.set_password("Admin12345!")
            admin.save()
        demo = {}
        for username, first, last, role in [
            ("reception", "Malika", "Karimova", Role.RECEPTIONIST),
            ("teacher", "Dilshod", "Aliyev", Role.TEACHER),
            ("student", "Sardor", "Rahimov", Role.STUDENT),
        ]:
            u, c = User.objects.get_or_create(username=username, defaults=dict(
                first_name=first, last_name=last, role=role, phone="998901234567", language="uz"))
            if c:
                u.set_password("Demo12345!")
                u.save()
            demo[role] = u
        teacher_profile, _ = TeacherProfile.objects.get_or_create(user=demo[Role.TEACHER])
        group, _ = Group.objects.get_or_create(name="Intermediate Evening", defaults=dict(level=levels["Intermediate"], teacher=teacher_profile))
        student, _ = StudentProfile.objects.get_or_create(
            user=demo[Role.STUDENT], defaults=dict(current_level=levels["Intermediate"], initial_level=levels["Intermediate"]))
        StudentGroup.objects.get_or_create(student=student, group=group)

        for code, level in levels.items():
            exam, created = Examination.objects.get_or_create(
                kind=ExamKind.PLACEMENT, level=level,
                defaults=dict(title=f"{code} Placement Test", duration_minutes=40, passing_score=50, high_threshold=85,
                              status=ExamStatus.PUBLISHED, created_by=admin, shuffle_options=True,
                              instructions="Answer all questions. You can only take this test once."))
            if not created:
                continue
            variant = ExaminationVariant.objects.create(examination=exam, name="A")
            for order, (text, section, options, correct) in enumerate(SAMPLE[code]):
                q = Question.objects.create(text=text, question_type=QuestionType.MULTIPLE_CHOICE, section=Section(section),
                                            level=level, points=1, created_by=admin)
                AnswerOption.objects.bulk_create(
                    [AnswerOption(question=q, text=t, is_correct=i == correct, order=i) for i, t in enumerate(options)])
                VariantQuestion.objects.create(variant=variant, question=q, order=order)
        self.stdout.write(self.style.SUCCESS(
            "Placement exams seeded (2 sample questions each - add the real question bank in the admin panel).\n"
            "Logins: admin / Admin12345!   reception, teacher, student / Demo12345!"))
