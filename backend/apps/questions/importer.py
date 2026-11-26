"""Bulk question import from Excel (.xlsx), CSV, PDF (text based) and TXT files.

Every format is first converted into the same neutral row dict::

    {"question", "type", "section", "level", "points", "options": [str], "correct": str,
     "explanation", "passage": str}

and then validated with the regular ``QuestionSerializer`` so imported questions obey exactly the
same rules as questions created by hand. **Every question type is supported** (single / multiple
choice, true-false, fill in the blank, matching, reading with a shared passage, listening).
Questions that cannot be imported (e.g. no answer given) are *skipped and reported*; they never
block the others.

Text / PDF layout::

    Passage: <reading text shared by the questions that follow>
    1. She ___ a student.
    A) is
    B) are
    C) am
    Answer: A
    Explanation: optional

* several letters (``Answer: A, C``) -> multiple select;  ``Answer: True`` -> true/false
* no options + ``Answer: went | has gone`` -> fill in the blank (``|`` separates accepted answers)
* ``left = right`` option lines -> matching
* ``Type: LISTENING`` + an audio file uploaded with the test -> listening questions
* optional ``Section:``, ``Level:``, ``Points:`` lines before ``Answer:``
"""
import csv
import io
import re

from django.db import transaction

from apps.academics.models import Level

from .models import Passage, Section
from .serializers import QuestionSerializer

MAX_ROWS = 500
MAX_BYTES = 10 * 1024 * 1024
LETTERS = "ABCDEFGH"
TYPE_ALIASES = {
    "": None, "MCQ": "MCQ", "SINGLE": "MCQ", "MSQ": "MSQ", "MULTI": "MSQ", "MULTIPLE": "MSQ", "TF": "TF",
    "TRUEFALSE": "TF", "FILL": "FILL", "BLANK": "FILL", "MATCH": "MATCH", "MATCHING": "MATCH",
    "READING": "READING", "LISTENING": "LISTENING", "WRITING": "WRITING",
}


class ImportErrorList(Exception):
    def __init__(self, errors):
        self.errors = errors


# --------------------------------------------------------------------------- readers
def _norm(h):
    return re.sub(r"[^a-z0-9]", "", str(h or "").lower())


def new_row(**kw):
    row = {"question": "", "type": "", "section": "", "level": "", "points": "", "options": [], "correct": "",
           "explanation": "", "passage": ""}
    row.update(kw)
    return row


def _read_table(rows):
    rows = [r for r in rows if r and any(str(c or "").strip() for c in r)]
    if not rows:
        return []
    head = [_norm(h) for h in rows[0]]
    out = []
    for r in rows[1:]:
        def cell(name):
            if name not in head:
                return ""
            i = head.index(name)
            return str(r[i]).strip() if i < len(r) and r[i] is not None else ""

        opts = [cell(k) for k in ("a", "b", "c", "d", "e", "f", "g", "h")]
        out.append(new_row(
            question=cell("question"), type=cell("type"), section=cell("section"), level=cell("level"),
            points=cell("points"), options=[o for o in opts if o], correct=cell("correct"),
            explanation=cell("explanation"), passage=cell("passage"),
        ))
    return out


def read_xlsx(data):
    from openpyxl import load_workbook

    ws = load_workbook(io.BytesIO(data), read_only=True, data_only=True).active
    return _read_table(list(ws.iter_rows(values_only=True)))


def read_csv(data):
    text = data.decode("utf-8-sig", errors="replace")
    dialect = csv.Sniffer().sniff(text[:2000], delimiters=",;\t") if text.strip() else csv.excel
    return _read_table(list(csv.reader(io.StringIO(text), dialect)))


def pdf_text(data):
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def read_pdf(data):
    text = pdf_text(data)
    if not text.strip():
        raise ImportErrorList([{"row": 0, "message": "no_text_in_pdf"}])
    return parse_text(text)


Q_RE = re.compile(r"^\s*(?:Q\s*)?(\d{1,3})\s*[.)\-:]\s+(.*\S)\s*$", re.I)
OPT_RE = re.compile(r"^\s*\(?([A-Ha-h])[.)]\s+(.*\S)\s*$")
ANS_RE = re.compile(r"^\s*(?:answers?|javob|to'g'ri|togri|correct)\s*[:\-]\s*(.*\S)\s*$", re.I)
KV_RE = re.compile(r"^\s*(explanation|izoh|section|bo'lim|level|daraja|points?|ball|type|turi)\s*[:\-]\s*(.*\S)\s*$", re.I)
PASSAGE_RE = re.compile(r"^\s*(?:reading\s+)?(?:passage|text|matn|o'qish matni)\s*[:\-]\s*(.*)$", re.I)
KV_MAP = {"explanation": "explanation", "izoh": "explanation", "section": "section", "bo'lim": "section",
          "level": "level", "daraja": "level", "point": "points", "points": "points", "ball": "points",
          "type": "type", "turi": "type"}


def parse_text(text):
    blocks, cur, passage = [], None, None  # ``passage``: list of lines while collecting, else the text
    for line in text.splitlines():
        if not line.strip():
            continue
        if (m := PASSAGE_RE.match(line)) and not (cur is not None and cur["_mode"] == "option"):
            passage, cur = [m.group(1).strip()] if m.group(1).strip() else [], None
        elif (m := ANS_RE.match(line)) and cur is not None:
            cur["correct"] = m.group(1).strip(); cur["_mode"] = None
        elif (m := KV_RE.match(line)) and cur is not None:
            key = KV_MAP[m.group(1).lower()]
            cur[key] = m.group(2).strip(); cur["_mode"] = "explanation" if key == "explanation" else None
        elif (m := OPT_RE.match(line)) and cur is not None:
            cur["options"].append(m.group(2).strip()); cur["_mode"] = "option"
        elif m := Q_RE.match(line):
            text_passage = " ".join(passage) if isinstance(passage, list) else (passage or "")
            if isinstance(passage, list):
                passage = text_passage
            cur = new_row(question=m.group(2).strip(), passage=text_passage)
            cur["_mode"] = "question"
            blocks.append(cur)
        elif isinstance(passage, list) and cur is None:
            passage.append(line.strip())  # still inside the passage block
        elif cur is not None:  # wrapped line: append to whatever came last
            mode = cur["_mode"]
            if mode == "option" and cur["options"]:
                cur["options"][-1] += " " + line.strip()
            elif mode == "explanation":
                cur["explanation"] += " " + line.strip()
            elif mode == "question":
                cur["question"] += " " + line.strip()
    for b in blocks:
        b.pop("_mode", None)
    return blocks


READERS = {".xlsx": read_xlsx, ".csv": read_csv, ".pdf": read_pdf, ".txt": lambda d: parse_text(d.decode("utf-8-sig", errors="replace"))}


# --------------------------------------------------------------------------- row -> serializer payload
def _letters_to_indexes(s, n):
    parts = [p for p in re.split(r"[\s,;/&+]+", s.upper().replace("AND", ",")) if p]
    if parts and all(len(p) == 1 and p in LETTERS[:n] for p in parts):
        return [LETTERS.index(p) for p in parts]
    return None


def build_payload(row, *, default_level, default_section, levels, has_audio=False):
    q = row["question"]
    if not q:
        raise ValueError("question text is empty")
    opts, correct = row["options"], row["correct"].strip()
    qtype = TYPE_ALIASES.get(_norm(row["type"]).upper(), "?")
    if qtype == "?":
        raise ValueError(f"unknown type '{row['type']}'")
    listening = bool(row.get("listening"))
    if listening and not has_audio:
        raise ValueError("listening exercise but no audio file was uploaded")
    wants_listening = listening or qtype == "LISTENING" or (row["section"].upper() == "LISTENING" and has_audio and qtype in (None, "MCQ"))
    wants_reading = qtype == "READING"
    if qtype in ("READING", "LISTENING"):
        qtype = None  # the answer shape decides; READING / LISTENING are applied below
    if qtype == "WRITING":
        return {"text": q, "question_type": "WRITING", "section": (row["section"] or "WRITING").upper(), "level": (levels.get(row["level"].upper()) if row["level"] else default_level).id,
                "points": float(str(row["points"] or 10).replace(",", ".")), "category": row.get("category", "") or "WRITING",
                "instruction": row.get("instruction", ""), "explanation": row["explanation"], "options": []}

    pairs = [o for o in opts if "=" in o]
    if qtype is None:  # detect from the shape of the question
        if pairs and len(pairs) == len(opts):
            qtype = "MATCH"
        elif not opts and correct.lower() in ("true", "false", "t", "f", "to'g'ri", "noto'g'ri"):
            qtype = "TF"
        elif not opts:
            qtype = "FILL"
        elif len(opts) == 2 and {o.lower() for o in opts} == {"true", "false"}:
            qtype = "TF"
        else:
            qtype = "MSQ" if len(_letters_to_indexes(correct, len(opts)) or []) > 1 else "MCQ"

    options = []
    if qtype == "MATCH":
        for o in opts:
            if "=" not in o:
                raise ValueError("matching options must look like  left = right")
            left, right = (x.strip() for x in o.split("=", 1))
            options.append({"text": left, "match_text": right})
    elif qtype == "FILL":
        answers = [a.strip() for a in re.split(r"\s*\|\s*", correct) if a.strip()] or list(opts)
        if not answers:
            raise ValueError("no answer given for this fill-in question")
        options = [{"text": a, "is_correct": True} for a in answers]
    elif qtype == "TF":
        truthy = correct.lower() in ("true", "t", "to'g'ri", "togri", "a", "1", "yes")
        falsy = correct.lower() in ("false", "f", "noto'g'ri", "notogri", "b", "2", "no")
        if not (truthy or falsy):
            raise ValueError("true/false answer must be True or False")
        options = [{"text": "True", "is_correct": truthy}, {"text": "False", "is_correct": falsy}]
    else:
        idx = _letters_to_indexes(correct, len(opts))
        if idx is None:  # maybe the correct answer was written out in full
            idx = [i for i, o in enumerate(opts) if o.strip().lower() in {c.strip().lower() for c in correct.split("|")}]
        if not idx:
            raise ValueError("answer not given / not recognised (use letters like B or A,C)")
        options = [{"text": o, "is_correct": i in idx} for i, o in enumerate(opts)]
        if qtype == "MCQ" and len(idx) > 1:
            qtype = "MSQ"
        if qtype == "MCQ" and wants_listening:
            qtype = "LISTENING"
        elif qtype == "MCQ" and (wants_reading or row["passage"]):
            qtype = "READING"

    section = (row["section"] or default_section).upper()
    if section not in Section.values:
        raise ValueError(f"unknown section '{row['section']}'")
    if qtype == "LISTENING" and not has_audio:
        raise ValueError("listening question but no audio file was uploaded")
    level = levels.get(row["level"].upper()) if row["level"] else default_level
    if level is None:
        raise ValueError(f"unknown level '{row['level']}'")
    try:
        points = float(str(row["points"]).replace(",", ".")) if row["points"] else 1
    except ValueError:
        raise ValueError("points must be a number")
    if qtype == "WRITING":
        options = []
    return {"text": q, "question_type": qtype, "section": section, "level": level.id, "points": points,
            "category": row.get("category", ""), "instruction": row.get("instruction", ""), "gap_no": row.get("gap_no"), "explanation": row["explanation"], "options": [{**o, "order": i} for i, o in enumerate(options)]}


# --------------------------------------------------------------------------- public API
def parse_upload(uploaded):
    name = uploaded.name.lower()
    ext = next((e for e in READERS if name.endswith(e)), None)
    if ext is None:
        raise ImportErrorList([{"row": 0, "message": "unsupported_file"}])
    if uploaded.size > MAX_BYTES:
        raise ImportErrorList([{"row": 0, "message": "file_too_large"}])
    rows = READERS[ext](uploaded.read())
    if not rows:
        raise ImportErrorList([{"row": 0, "message": "no_questions_found"}])
    return rows


def import_questions(uploaded, *, user, default_level, default_section="GRAMMAR", variant=None, audio=None):
    """Create every importable question (and append them to ``variant``).

    Returns ``(created_questions, skipped)`` where ``skipped`` lists the questions that were not
    importable together with the reason. Raises ``ImportErrorList`` if nothing could be imported.
    """
    return import_rows(parse_upload(uploaded), user=user, default_level=default_level, default_section=default_section,
                       variant=variant, audio=audio)


def import_rows(rows, *, user, default_level, default_section="GRAMMAR", variant=None, audio=None):
    """Validate and save neutral rows. Same return contract as ``import_questions``."""
    if len(rows) > MAX_ROWS:
        raise ImportErrorList([{"row": 0, "message": "too_many_rows"}])

    levels = {l.code.upper(): l for l in Level.objects.all()}
    request = type("R", (), {"user": user})()  # the serializer only needs request.user
    skipped = []
    created, passages = [], {}

    with transaction.atomic():
        audio_passage = None
        if audio is not None:
            audio_passage = Passage.objects.create(title=f"Audio: {audio.name}"[:200], audio=audio, level=default_level, created_by=user)

        for i, row in enumerate(rows, start=1):
            try:
                payload = build_payload(row, default_level=default_level, default_section=default_section, levels=levels,
                                        has_audio=audio_passage is not None)
                if payload["question_type"] == "LISTENING" or row.get("listening"):
                    payload["passage"] = audio_passage.id  # the audio track is the shared "passage" of the exercise
                elif row["passage"].strip():
                    key = row["passage"].strip()
                    if key not in passages:
                        passages[key] = Passage.objects.create(title=key[:60], text=key, level=default_level, created_by=user)
                    payload["passage"] = passages[key].id
                s = QuestionSerializer(data=payload, context={"request": request})
                if not s.is_valid():
                    raise ValueError("; ".join(f"{k}: {v[0] if isinstance(v, list) else v}" for k, v in s.errors.items()))
                created.append(s.save())
            except ValueError as exc:
                skipped.append({"row": i, "message": str(exc), "text": row["question"][:60]})

        if not created:
            transaction.set_rollback(True)
            raise ImportErrorList(skipped or [{"row": 0, "message": "no_questions_found"}])
        if audio_passage is not None and not audio_passage.questions.exists():
            audio_passage.delete()
        if variant is not None:
            from apps.examinations.models import VariantQuestion

            start = variant.variant_questions.count()
            VariantQuestion.objects.bulk_create(
                [VariantQuestion(variant=variant, question=q, order=start + i) for i, q in enumerate(created)])
    return created, skipped


def template_xlsx():
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = "Questions"
    ws.append(["type", "section", "level", "passage", "question", "points", "A", "B", "C", "D", "correct", "explanation"])
    ws.append(["MCQ", "GRAMMAR", "", "", "She ___ a student.", 1, "is", "are", "am", "", "A", "Third person singular"])
    ws.append(["MSQ", "VOCABULARY", "", "", "Select the fruits.", 2, "apple", "table", "banana", "", "A,C", ""])
    ws.append(["TF", "GRAMMAR", "", "", "'Goed' is the past of 'go'.", 1, "", "", "", "", "False", "Irregular verb: went"])
    ws.append(["FILL", "GRAMMAR", "", "", "I ___ to school yesterday.", 1, "", "", "", "", "went | has gone", ""])
    ws.append(["MATCH", "VOCABULARY", "", "", "Match the words.", 2, "cat = animal", "red = colour", "", "", "", ""])
    ws.append(["READING", "READING", "", "Tom gets up at 7. He walks to school.", "When does Tom get up?", 1, "At 6", "At 7", "At 8", "", "B", ""])
    ws.append(["READING", "READING", "", "Tom gets up at 7. He walks to school.", "How does Tom go to school?", 1, "By bus", "By car", "On foot", "", "C", ""])
    for c in ws[1]:
        c.font = Font(bold=True)
    ws2 = wb.create_sheet("Instructions")
    for line in [
        "One question per row. Columns type, section, level, passage, points, explanation are optional.",
        "type: MCQ (default) / MSQ / TF / FILL / MATCH / READING / LISTENING - detected automatically if left empty.",
        "section: GRAMMAR, VOCABULARY, READING, LISTENING (default is chosen in the upload dialog).",
        "level: the level name, e.g. Intermediate (default = the examination's level).",
        "correct: option letter (B), several letters (A,C), True/False, or the accepted answers separated by |.",
        "MATCH: write each pair in an option cell as  left = right  and leave 'correct' empty.",
        "passage: reading text. Rows with the same passage text share one passage.",
        "LISTENING: upload the audio file together with the test in the upload dialog.",
        "PDF / TXT files use the layout:  1. Question text / A) option / B) option / Answer: B  (Passage: ... for reading texts)",
    ]:
        ws2.append([line])
    ws2.column_dimensions["A"].width = 120
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

