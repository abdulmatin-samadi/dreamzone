"""Excel and PDF exports."""
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

SECTIONS = [("GRAMMAR", "Grammar"), ("VOCABULARY", "Vocabulary"), ("READING", "Reading"), ("LISTENING", "Listening"), ("WRITING", "Writing"), ("SPEAKING", "Speaking")]

# the centre's results sheet: Number | Full Name | Test | Writing | Speaking | Overall | Status
HEADER_FILL, NUMBER_FILL = "FFC000", "F4B183"
STATUS_FILL = {"Passed": "00B050", "C/Passed": "FFFF00", "Failed": "FF0000", "Pending": "D9D9D9"}
C_PASS_BAND = 0.10  # "C/Passed" (conditionally passed): up to 10 % of the maximum below the pass mark


def _pts(v):
    v = float(v or 0)
    return int(v) if v == int(v) else round(v, 1)


def _section_score(r, key):
    return float(((r.section_scores or {}).get(key) or {}).get("score") or 0)


def _status(r):
    """Passed / C/Passed / Failed. A teacher's / admin's decision on an upgrade wins; otherwise the score decides:
    at or above the pass mark -> Passed, within 10 % of the maximum below it -> C/Passed, lower -> Failed."""
    if r.approval_status == "APPROVED":
        return "Passed"
    if r.approval_status == "REJECTED":
        return "Failed"
    from .services import part_missing

    if r.writing_pending or part_missing(r, "speaking") or part_missing(r, "writing"):
        return "Pending"  # a part still waits for the teacher's score
    score, top, mark = float(r.total_score), float(r.max_score), float(r.examination.passing_score)
    if score >= mark:
        return "Passed"
    return "C/Passed" if top and score >= mark - top * C_PASS_BAND else "Failed"


def _columns(results):
    """Writing / Speaking columns only when the exported tests have that part."""
    have = {k for r in results for k in (r.section_scores or {})}
    return ["Number", "Full Name", "Test", *(["Writing"] if "WRITING" in have else []),
            *(["Speaking"] if "SPEAKING" in have else []), "Overall", "Status"]


def _sheet_rows(results):
    results = sorted(results, key=lambda r: (-float(r.total_score), r.student.user.full_name))
    cols = _columns(results)
    rows = []
    for i, r in enumerate(results, 1):
        writing, speaking = _section_score(r, "WRITING"), _section_score(r, "SPEAKING")
        row = {"Number": i, "Full Name": r.student.user.full_name, "Test": _pts(float(r.total_score) - writing - speaking),
               "Writing": _pts(writing), "Speaking": _pts(speaking), "Overall": _pts(r.total_score), "Status": _status(r)}
        rows.append([row[c] for c in cols])
    return cols, rows


def results_xlsx(results):
    from openpyxl.styles import Border, Side

    wb = Workbook()
    ws = wb.active
    ws.title = "Results"
    cols, rows = _sheet_rows(list(results))
    thin = Side(style="thin", color="808080")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    ws.append(cols)
    for c in ws[1]:
        c.font = Font(bold=True, size=12)
        c.fill = PatternFill("solid", fgColor=HEADER_FILL)
        c.alignment = Alignment(horizontal="left" if c.value == "Full Name" else "center", vertical="center")
        c.border = border
    status_col = cols.index("Status") + 1
    for row in rows:
        ws.append(row)
        for c in ws[ws.max_row]:
            c.border = border
            c.font = Font(bold=True, size=11)
            if c.column == 1:
                c.fill = PatternFill("solid", fgColor=NUMBER_FILL)
                c.alignment = Alignment(horizontal="center")
            elif c.column == status_col:
                c.fill = PatternFill("solid", fgColor=STATUS_FILL[c.value])
                c.alignment = Alignment(horizontal="center")
            elif cols[c.column - 1] != "Full Name":
                c.alignment = Alignment(horizontal="right")
    widths = {"Number": 9, "Full Name": 26, "Status": 13}
    for i, name in enumerate(cols, 1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = widths.get(name, 12)
    ws.freeze_panes = "A2"
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _table(data, widths=None, header=True):
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    style = [
        ("FONTSIZE", (0, 0), (-1, -1), 8), ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4F46E5")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white)]
    t.setStyle(TableStyle(style))
    return t


def results_pdf(results):
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=24, rightMargin=24, topMargin=24, bottomMargin=24)
    styles = getSampleStyleSheet()
    cols, rows = _sheet_rows(list(results))
    t = _table([cols] + [[str(v) for v in row] for row in rows])
    st = cols.index("Status")
    style = [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#" + HEADER_FILL)), ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
             ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 9)]
    for i, row in enumerate(rows, 1):
        style += [("BACKGROUND", (0, i), (0, i), colors.HexColor("#" + NUMBER_FILL)),
                  ("BACKGROUND", (st, i), (st, i), colors.HexColor("#" + STATUS_FILL[row[st]]))]
    t.setStyle(TableStyle(style))
    doc.build([Paragraph("Examination results", styles["Title"]), Spacer(1, 8), t])
    return buf.getvalue()


def result_report_pdf(result, answers=None, *, hide_decision=False):
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    exam = result.examination
    story = [
        Paragraph("Examination result report", styles["Title"]),
        Paragraph(f"<b>Student:</b> {result.student.user.full_name} &nbsp; <b>Phone:</b> {result.student.user.phone}", styles["Normal"]),
        Paragraph(f"<b>Examination:</b> {exam.title} ({exam.kind}) &nbsp; <b>Level:</b> {result.level.code}"
                  + (f" -> {exam.target_level.code}" if exam.target_level else ""), styles["Normal"]),
        Paragraph(f"<b>Date:</b> {result.created_at.astimezone():%Y-%m-%d %H:%M}", styles["Normal"]),
        Spacer(1, 12),
    ]
    status = "AWAITING THE TEACHER'S DECISION" if hide_decision else ("PASSED" if result.passed else "NOT PASSED")
    rows = [["Section", "Score", "Max", "Correct / Total"]]
    for name, s in result.section_scores.items():
        rows.append([name.title(), f"{s['score']:g}", f"{s['max']:g}", f"{s['correct']}/{s['total']}"])
    rows.append(["TOTAL", f"{result.total_score:g}", f"{result.max_score:g}",
                 f"{result.correct_count}/{result.correct_count + result.incorrect_count + result.unanswered_count}"])
    t = _table(rows)
    t.setStyle(TableStyle([("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold")]))
    story += [t, Spacer(1, 12),
              Paragraph(f"<b>Status:</b> {status} (passing score {exam.passing_score:g} points)", styles["Normal"])]
    if result.recommended_level:
        story.append(Paragraph(f"<b>Recommendation:</b> {result.recommendation} -> {result.recommended_level.code}", styles["Normal"]))
    if result.approval_status != "NOT_REQUIRED":
        story.append(Paragraph(f"<b>Approval:</b> {result.approval_status}", styles["Normal"]))
    doc.build(story)
    return buf.getvalue()
