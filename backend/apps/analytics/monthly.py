"""Monthly report: how many came for a placement test, which level they got, how many joined a group."""
import calendar
from datetime import date, datetime, time
from io import BytesIO

from django.db.models import Avg, Count, Q
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.models import Level
from apps.core.exceptions import DomainError
from apps.core.permissions import IsAdminOrReceptionist
from apps.examinations.models import ExamKind
from apps.results.models import ApprovalStatus, ExamResult
from apps.students.models import LevelChangeHistory, StudentGroup, StudentProfile

MONTHS_UZ = ["", "Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun", "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr"]


def _bounds(year, month):
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(date(year, month, 1), time.min), tz)
    last = calendar.monthrange(year, month)[1]
    end = timezone.make_aware(datetime.combine(date(year, month, last), time.max), tz)
    return start, end


def _prev(year, month):
    return (year - 1, 12) if month == 1 else (year, month - 1)


def _totals(start, end):
    rng = {"created_at__range": (start, end)}
    placement = ExamResult.objects.filter(examination__kind=ExamKind.PLACEMENT, **rng)
    upgrade = ExamResult.objects.filter(examination__kind=ExamKind.UPGRADE, **rng)
    placed_ids = set(LevelChangeHistory.objects.filter(reason=LevelChangeHistory.Reason.PLACEMENT, **rng).values_list("student_id", flat=True))
    joined = StudentGroup.objects.filter(joined_at__range=(start, end))
    return {
        "new_students": StudentProfile.objects.filter(is_guest=False, **rng).count(),
        "guests": StudentProfile.objects.filter(is_guest=True, **rng).count(),
        "placement_tests": placement.count(),
        "placement_avg": round(float(placement.aggregate(a=Avg("total_score"))["a"] or 0), 1),  # points
        "placement_avg_max": round(float(placement.aggregate(a=Avg("max_score"))["a"] or 0), 1),
        "placed": len(placed_ids),
        "joined_group": joined.values("student").distinct().count(),
        "placed_and_joined": StudentGroup.objects.filter(student_id__in=placed_ids).values("student").distinct().count(),
        "upgrade_tests": upgrade.count(),
        "upgrade_approved": upgrade.filter(approval_status=ApprovalStatus.APPROVED).count(),
        "upgrade_rejected": upgrade.filter(approval_status=ApprovalStatus.REJECTED).count(),
    }


def build_report(year, month):
    start, end = _bounds(year, month)
    py, pm = _prev(year, month)
    totals, prev = _totals(start, end), _totals(*_bounds(py, pm))
    rng = {"created_at__range": (start, end)}
    taken = dict(ExamResult.objects.filter(examination__kind=ExamKind.PLACEMENT, **rng)
                 .values_list("examination__level__code").annotate(n=Count("id")))
    placed = dict(LevelChangeHistory.objects.filter(reason=LevelChangeHistory.Reason.PLACEMENT, **rng)
                  .values_list("to_level__code").annotate(n=Count("id")))
    joined = dict(StudentGroup.objects.filter(joined_at__range=(start, end))
                  .values_list("group__level__code").annotate(n=Count("student", distinct=True)))
    upgraded = dict(LevelChangeHistory.objects.filter(reason__in=[LevelChangeHistory.Reason.UPGRADE, LevelChangeHistory.Reason.ADMIN], **rng)
                    .values_list("to_level__code").annotate(n=Count("id")))
    by_level = []
    for lv in Level.objects.filter(is_active=True).order_by("order"):
        row = {"level": lv.code, "name": lv.name, "placement_tests": taken.get(lv.code, 0), "placed": placed.get(lv.code, 0),
               "joined_group": joined.get(lv.code, 0), "upgraded_to": upgraded.get(lv.code, 0)}
        if any(v for k, v in row.items() if k not in ("level", "name")):
            by_level.append(row)
    days = calendar.monthrange(year, month)[1]
    per_day = dict(ExamResult.objects.filter(examination__kind=ExamKind.PLACEMENT, **rng)
                   .values_list("created_at__day").annotate(n=Count("id")))
    return {
        "month": f"{year:04d}-{month:02d}", "title": f"{MONTHS_UZ[month]} {year}",
        "totals": totals, "previous": prev, "by_level": by_level,
        "by_day": [{"day": d, "placement_tests": per_day.get(d, 0)} for d in range(1, days + 1)],
    }


LABELS = [
    ("new_students", "Yangi o'quvchilar (ro'yxatdan o'tgan)"), ("guests", "Mehmonlar (ro'yxatsiz test)"),
    ("placement_tests", "Saralash testlari"), ("placement_avg", "Saralash testi o'rtacha natijasi, %"),
    ("placed", "Darajasi aniqlanganlar"), ("joined_group", "Guruhga yozilganlar"),
    ("placed_and_joined", "Darajasi aniqlanib, guruhga yozilganlar"), ("upgrade_tests", "Daraja imtihonlari"),
    ("upgrade_approved", "Darajasi oshirilganlar"), ("upgrade_rejected", "Rad etilganlar"),
]
LEVEL_HEADERS = ["Daraja", "Saralash testlari", "Shu darajaga joylashtirilgan", "Guruhga yozilgan", "Shu darajaga ko'tarilgan"]


def report_xlsx(rep):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    wb = Workbook()
    head = (Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="2563EB"))
    ws = wb.active
    ws.title = "Umumiy"
    ws.append([f"Oylik hisobot — {rep['title']}"])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append([])
    ws.append(["Ko'rsatkich", rep["title"], "O'tgan oy", "Farq"])
    for c in ws[3]:
        c.font, c.fill = head
    for key, label in LABELS:
        cur, prev = rep["totals"][key], rep["previous"][key]
        ws.append([label, cur, prev, round(cur - prev, 1)])
    ws.column_dimensions["A"].width = 44
    for col in "BCD":
        ws.column_dimensions[col].width = 14
    ws2 = wb.create_sheet("Darajalar bo'yicha")
    ws2.append(LEVEL_HEADERS)
    for c in ws2[1]:
        c.font, c.fill = head
    for r in rep["by_level"]:
        ws2.append([f"{r['level']} — {r['name']}", r["placement_tests"], r["placed"], r["joined_group"], r["upgraded_to"]])
    ws2.column_dimensions["A"].width = 32
    for col in "BCDE":
        ws2.column_dimensions[col].width = 22
    ws3 = wb.create_sheet("Kunlar bo'yicha")
    ws3.append(["Kun", "Saralash testlari"])
    for c in ws3[1]:
        c.font, c.fill = head
    for d in rep["by_day"]:
        ws3.append([d["day"], d["placement_tests"]])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def report_pdf(rep):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    def table(data, widths):
        t = Table(data, colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 9), ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563EB")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (1, 1), (-1, -1), "RIGHT"), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F1F5F9")]),
        ]))
        return t

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    st = getSampleStyleSheet()
    rows = [["Ko'rsatkich", rep["title"], "O'tgan oy", "Farq"]]
    for key, label in LABELS:
        cur, prev = rep["totals"][key], rep["previous"][key]
        diff = round(cur - prev, 1)
        rows.append([label, f"{cur:g}", f"{prev:g}", f"{'+' if diff > 0 else ''}{diff:g}"])
    lv = [LEVEL_HEADERS] + [[r["level"], r["placement_tests"], r["placed"], r["joined_group"], r["upgraded_to"]] for r in rep["by_level"]]
    story = [
        Paragraph(f"Dreamzone — oylik hisobot", st["Title"]), Paragraph(rep["title"], st["Heading2"]), Spacer(1, 8),
        table(rows, [250, 80, 80, 60]), Spacer(1, 18), Paragraph("Darajalar bo'yicha", st["Heading3"]),
    ]
    story.append(table(lv, [90, 95, 120, 95, 110]) if rep["by_level"] else Paragraph("Bu oyda ma'lumot yo'q.", st["Normal"]))
    doc.build(story)
    return buf.getvalue()


class MonthlyReportView(APIView):
    permission_classes = [IsAdminOrReceptionist]

    def get(self, request):
        raw = request.query_params.get("month") or timezone.localdate().strftime("%Y-%m")
        try:
            year, month = (int(x) for x in raw.split("-"))
            date(year, month, 1)
        except (ValueError, TypeError):
            raise DomainError("invalid_month", status_code=400)
        rep = build_report(year, month)
        kind = request.query_params.get("file")
        if kind in ("xlsx", "pdf"):
            content = report_xlsx(rep) if kind == "xlsx" else report_pdf(rep)
            ctype = "application/pdf" if kind == "pdf" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            resp = HttpResponse(content, content_type=ctype)
            resp["Content-Disposition"] = f'attachment; filename="hisobot-{rep["month"]}.{kind}"'
            return resp
        return Response(rep)
