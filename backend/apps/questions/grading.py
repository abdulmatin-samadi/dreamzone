"""Pure grading functions. No database access, so they are trivially testable.

Answer payload shapes (``StudentAnswer.answer``):

* MCQ / TF / READING / LISTENING : ``{"option_ids": [<id>]}``
* MSQ                            : ``{"option_ids": [<id>, ...]}``
* FILL                           : ``{"text": "<string>"}``
* MATCH                          : ``{"pairs": {"<option id>": "<right-hand text>"}}``

Scoring is all-or-nothing per question.
"""
import re
from decimal import Decimal

from .models import QuestionType

CHOICE_TYPES = {
    QuestionType.MULTIPLE_CHOICE, QuestionType.TRUE_FALSE, QuestionType.READING, QuestionType.LISTENING,
}


def normalize_text(value):
    """Case, spacing, curly quotes and end punctuation do not matter when comparing typed answers."""
    s = str(value or "").replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
    s = re.sub(r"[.,;:!?]+(\s|$)", r"\1", s)
    return re.sub(r"\s+", " ", s).strip().casefold()


def is_blank(question_type, answer):
    if not answer:
        return True
    if question_type in (QuestionType.FILL, QuestionType.WRITING):
        return not normalize_text(answer.get("text"))
    if question_type == QuestionType.MATCH:
        pairs = answer.get("pairs") or {}
        return not any(normalize_text(v) for v in pairs.values())
    return not answer.get("option_ids")


def validate_answer_shape(question_type, answer, valid_option_ids):
    """Return a cleaned answer dict or raise ValueError."""
    if not isinstance(answer, dict):
        raise ValueError("answer must be an object")
    if question_type == QuestionType.FILL:
        text = answer.get("text", "")
        if not isinstance(text, str) or len(text) > 500:
            raise ValueError("text must be a string up to 500 characters")
        return {"text": text}
    if question_type == QuestionType.WRITING:
        text = answer.get("text", "")
        if not isinstance(text, str) or len(text) > 10000:
            raise ValueError("text must be a string up to 10000 characters")
        return {"text": text}
    if question_type == QuestionType.MATCH:
        pairs = answer.get("pairs", {})
        if not isinstance(pairs, dict):
            raise ValueError("pairs must be an object")
        clean = {}
        for key, val in pairs.items():
            if str(key) not in {str(i) for i in valid_option_ids}:
                raise ValueError("unknown matching item")
            if not isinstance(val, str) or len(val) > 500:
                raise ValueError("invalid matching value")
            clean[str(key)] = val
        return {"pairs": clean}
    ids = answer.get("option_ids", [])
    if not isinstance(ids, list) or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids):
        raise ValueError("option_ids must be a list of integers")
    if len(set(ids)) != len(ids) or not set(ids) <= set(valid_option_ids):
        raise ValueError("invalid option selection")
    if question_type != QuestionType.MULTIPLE_SELECT and len(ids) > 1:
        raise ValueError("only one option may be selected")
    return {"option_ids": ids}


def grade(question, options, answer):
    """Return ``(is_correct, points_awarded)``. ``options`` is a list of AnswerOption."""
    qtype = question.question_type
    points = Decimal(question.points)
    if is_blank(qtype, answer):
        return False, Decimal("0")

    if qtype in CHOICE_TYPES or qtype == QuestionType.MULTIPLE_SELECT:
        correct = {o.id for o in options if o.is_correct}
        ok = bool(correct) and set(answer.get("option_ids", [])) == correct
    elif qtype == QuestionType.FILL:
        given = normalize_text(answer.get("text"))
        ok = any(o.is_correct and normalize_text(o.text) == given for o in options)
    elif qtype == QuestionType.MATCH:
        pairs = answer.get("pairs") or {}
        ok = bool(options) and all(
            normalize_text(pairs.get(str(o.id))) == normalize_text(o.match_text) for o in options
        )
    else:  # pragma: no cover
        ok = False
    return ok, (points if ok else Decimal("0"))
