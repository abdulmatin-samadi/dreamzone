from rest_framework.test import APIClient

from apps.accounts.models import Role, TeacherProfile, User
from apps.academics.models import Level
from apps.examinations.models import ExamKind, ExamStatus, Examination, ExaminationVariant, VariantQuestion
from apps.questions.models import AnswerOption, Question, QuestionType, Section
from apps.students.models import StudentProfile

PASSWORD = "Str0ng-Pass!42"


def make_levels():
    return {c: Level.objects.get_or_create(code=c, defaults={"name": c, "order": i})[0]
            for i, c in enumerate(["A1", "A2", "B1", "B2", "C1", "C2"], start=1)}


def make_user(username, role, **kw):
    u = User.objects.create_user(username=username, password=PASSWORD, role=role, first_name=username.title(),
                                 last_name="Test", phone="998900000000", **kw)
    if role == Role.TEACHER:
        TeacherProfile.objects.create(user=u)
    return u


def make_student(username, level=None):
    u = make_user(username, Role.STUDENT)
    return StudentProfile.objects.create(user=u, current_level=level, initial_level=level)


def client_for(user):
    c = APIClient()
    c.force_authenticate(user)
    return c


def mcq(level, text="Q", points=1, section=Section.GRAMMAR, creator=None):
    q = Question.objects.create(text=text, question_type=QuestionType.MULTIPLE_CHOICE, section=section, level=level,
                                points=points, created_by=creator)
    AnswerOption.objects.create(question=q, text="right", is_correct=True, order=0)
    AnswerOption.objects.create(question=q, text="wrong", is_correct=False, order=1)
    return q


def make_exam(level, *, kind=ExamKind.PLACEMENT, target=None, n=4, creator=None, passing=None, high="85%",
              duration=30, published=True, **kw):
    """Thresholds are points; by default 50% / 85% of the n one-point questions."""
    passing = n * 0.5 if passing is None else passing
    high = n * 0.85 if high == "85%" else high
    exam = Examination.objects.create(
        kind=kind, title=f"{kind} {level.code}", level=level, target_level=target, passing_score=passing,
        high_threshold=high if kind == ExamKind.PLACEMENT else None, duration_minutes=duration, created_by=creator,
        status=ExamStatus.PUBLISHED if published else ExamStatus.DRAFT, **kw)
    variant = ExaminationVariant.objects.create(examination=exam, name="A")
    for i in range(n):
        VariantQuestion.objects.create(variant=variant, question=mcq(level, f"q{i}", creator=creator), order=i)
    return exam, variant


def answer_all(client, attempt_id, *, correct_count, total=None):
    """Answer the first ``correct_count`` questions correctly, the rest wrongly."""
    data = client.get(f"/api/v1/attempts/{attempt_id}/").json()
    items = []
    for i, q in enumerate(data["questions"]):
        want = "right" if i < correct_count else "wrong"
        opt = next(o["id"] for o in q["options"] if o["text"] == want)
        items.append({"question_id": q["id"], "answer": {"option_ids": [opt]}})
    r = client.put(f"/api/v1/attempts/{attempt_id}/answers/", {"answers": items})
    assert r.status_code == 200, r.content
    return items


def signup(client, *, first_name="Ali", last_name="Vali", username="ali_vali", password="Zx-91kLm-pass", **extra):
    """Self-registration (robot check + details). Returns the response."""
    from django.core.cache import cache

    from apps.accounts.verification import make_captcha

    cache.clear()  # the registration throttle (10/hour) must not leak from one test into the next

    token, _img, answer = make_captcha()
    return client.post("/api/v1/auth/register/", {"first_name": first_name, "last_name": last_name, "username": username,
                                                  "password": password, "captcha_token": token, "captcha_answer": answer, **extra},
                       format="json")
