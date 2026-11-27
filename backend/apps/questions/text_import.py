"""Paste-in import: the exam text copied from a PDF / Word file + the answers in a separate box.

The test text is split into *sections* (a heading such as ``1. Complete the sentences`` followed by its
items). The heading decides the exercise type (``Category``):

=========================================  ============================================
Heading contains                           Exercise
=========================================  ============================================
true or false                              Reading - True/False (text before the items)
tick                                       Tick the correct sentence
mistake / error                            Find the mistake (write the right sentence)
odd one / different                        Odd one out
past simple / verbs                        Word formation (past simple)
conversation / dialogue / question words   Dialogue completion
choose the correct / multiple choice       Multiple choice
anything else with blanks                  Gap filling
=========================================  ============================================

The answers box holds one block per section, **in the same order**, blocks separated by an empty line
(a leading ``1.`` / ``Section 2`` line is allowed and ignored). Inside a block write the answers
numbered (``2 are``) or simply in order (``are, is, has``); several accepted answers: ``is | 's``.
Items without an answer are reported and not imported - nothing is guessed.
"""
import itertools
import re

from .models import Category

KEYWORDS = r"(?:complete|put|choose|tick|find|underline|write|writing|read|fill|match|circle|select|answer|correct|look|use|rewrite|order|make|unscramble|decide|listen|listening)"
HEAD_NUM = re.compile(rf"^\s*(\d{{1,2}})\s*[.)]\s+({KEYWORDS}\b.*)$", re.I)
HEAD_PLAIN = re.compile(rf"^\s*({KEYWORDS}\b[^\n]{{3,110}}[.:?])\s*$", re.I)
BLANK = re.compile(r"_{2,}|\.{4,}")
ITEM = re.compile(r"^\s*(\d{1,2})\s*[.):]?\s+(.+?)\s*$")
BOX = re.compile(r"[☐□☑☒✓✔✅]")  # tick boxes / marks
OPT = re.compile(r"^\s*\(?([A-Ha-h])[.)]\s+(.+?)\s*$")
EXAMPLE = re.compile(r"\(example\)|\bexample\b", re.I)

SECTION_OF = {
    Category.GAP: "GRAMMAR", Category.MCQ: "GRAMMAR", Category.TICK: "GRAMMAR", Category.MISTAKE: "GRAMMAR",
    Category.ODD: "VOCABULARY", Category.WORDFORM: "GRAMMAR", Category.DIALOGUE: "GRAMMAR", Category.TFREAD: "READING",
    Category.GAPTEXT: "GRAMMAR", Category.READQA: "READING", Category.LISTEN: "LISTENING", Category.WRITING: "WRITING",
}
NOT_GIVEN = {"ng", "ni", "not given", "no information", "no info", "not stated", "doesn't say", "doesnt say"}


WRITING_RE = re.compile(
    r"\bwriting\b|\bessay\b|write (?:an?|the|your)?\s*(?:short |formal |informal )?(?:email|e-mail|letter|paragraph|story|composition|report|review|article|note|message|description|text)"
    r"|\bwrite about\b|\bwrite \d+", re.I)


def classify(title):
    t = title.lower()
    if WRITING_RE.search(t):
        return Category.WRITING
    if "listen" in t:
        return Category.LISTEN
    if ("true" in t and "false" in t) or "not given" in t or "no information" in t:
        return Category.TFREAD
    if "answer the question" in t:
        return Category.READQA
    if "tick" in t:
        return Category.TICK
    if "gaps" in t or "complete the text" in t or "cloze" in t or "complete the passage" in t:
        return Category.GAPTEXT
    if "mistake" in t or "error" in t:
        return Category.MISTAKE
    if "choose the correct" in t or "multiple choice" in t or "circle" in t:
        return Category.MCQ
    if "odd one" in t or "different" in t:
        return Category.ODD
    if "past simple" in t or "verbs" in t:
        return Category.WORDFORM
    if "conversation" in t or "dialogue" in t or "question words" in t:
        return Category.DIALOGUE
    return Category.GAP


ORPHAN = re.compile(r"^(?:\d{1,2}|[\u2610\u25a1\u2611\u2612\u2713\u2714\u2705]|\d{1,2}\s*[\u2610\u25a1\u2611\u2612]|_{2,})$")


def normalize_lines(text):
    """Text copied from a PDF often puts the number, the tick box and the blank on lines of their own;
    glue such fragments to the line that follows (``1`` / ``[box]`` / ``I like tea`` -> ``1 [box] I like tea``)."""
    out, pending = [], ""
    for raw in text.replace("\r", "").replace("\u00a0", " ").split("\n"):
        line = raw.strip()
        if not line:
            if pending:
                out.append(pending); pending = ""
            continue
        if ORPHAN.match(line):
            pending = f"{pending} {line}".strip()
            continue
        out.append(f"{pending} {line}".strip() if pending else line)
        pending = ""
    if pending:
        out.append(pending)
    return out


def _looks_like_box(text):
    """A word box: a few short lowercase words, no sentence punctuation ("live come speak have (x2) eat")."""
    words = text.split()
    return 3 <= len(words) <= 16 and re.fullmatch(r"[a-z][a-z'()\s/\-x0-9]*", text) is not None


KEYWORD_START = re.compile(rf"^\s*{KEYWORDS}\b", re.I)
TERMINAL = re.compile(r"[.:?!)\]]$")


def split_sections(text):
    """-> list of {"printed": int|None, "title": str, "lines": [str]}"""
    sections, cur = [], None
    lines = normalize_lines(text)
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if (m := HEAD_NUM.match(line)) and _continues_items(cur, int(m.group(1)), line):
            cur["lines"].append(line)  # "4. Make ______" inside "1. Go ___ / 2. Come ___ ...": an item, not a new exercise
            continue
        if m:
            title = m.group(2).strip()
            printed = int(m.group(1))
        elif (m := re.match(r"^\s*(\d{1,2})\s*[.)]\s+(.+)$", line)) and _looks_like_box(m.group(2)) and any(
                re.search(r"\(\d{1,2}\)\s*_{2,}", l) for l in lines[i:i + 16]):
            # "1. live come speak have (x2) eat ..." = word box of a text with numbered gaps
            cur = {"printed": int(m.group(1)), "title": "Complete the text.", "lines": [m.group(2)]}
            sections.append(cur)
            continue
        elif KEYWORD_START.match(line) and not ITEM.match(line) and len(line) < 160 and not (
                cur is not None and WRITING_RE.search(cur["title"])) and (cur is None or not _has_items(cur["lines"]) or TERMINAL.search(line)):
            title, printed = line, None
        else:
            if cur is not None:
                cur["lines"].append(line)
            continue  # text before the first heading (e.g. "ENGLISH TEST / full name") is ignored
        # a heading may wrap onto the next line: "Complete the dialogues with ... from" / "the boxes."
        while not TERMINAL.search(title) and i < len(lines) and len(title) < 200:
            nxt = lines[i].strip()
            if ITEM.match(nxt) or HEAD_NUM.match(nxt) or BLANK.search(nxt) or not (TERMINAL.search(nxt) and len(nxt.split()) <= 8):
                break
            title += " " + nxt
            i += 1
        if printed is None and cur is not None and not _has_items(cur["lines"]) and not WRITING_RE.search(cur["title"]):
            if title.strip(" .:").lower() != cur["title"].strip(" .:").lower():  # the same heading pasted twice is kept once
                cur["title"] = (cur["title"] if TERMINAL.search(cur["title"]) else cur["title"] + ".") + " " + title  # subtitle of the section above
        else:
            cur = {"printed": printed, "title": title, "lines": []}
            sections.append(cur)
    if not sections:
        # no recognisable heading at all ("What's the next word?"): the lines before the first item are the title
        k = next((j for j, l in enumerate(lines) if ITEM.match(l) or BLANK.search(l) or re.match(r"^example\b", l, re.I)), None)
        if k is not None:
            body = lines[k:]
            if _has_items(body):
                sections.append({"printed": None, "title": " ".join(lines[:k]).strip() or "Exercise", "lines": body})
    return sections


def _continues_items(cur, number, line):
    """A numbered line with a blank whose number follows the last item of the current exercise is the next item,
    even when it starts with a heading word ("4. Make ____", "8. Find ____")."""
    if cur is None or not BLANK.search(line):
        return False
    numbers = [int(m.group(1)) for l in cur["lines"] if (m := ITEM.match(l))]
    return bool(numbers) and number == numbers[-1] + 1


def _has_items(lines):
    return any(ITEM.match(l) or BLANK.search(l) or BOX.search(l) for l in lines)


# --------------------------------------------------------------------------- answers
def split_answer_blocks(answers):
    blocks, cur = [], []
    for raw in answers.replace("\r", "").split("\n"):
        line = raw.strip()
        if not line:
            if cur:
                blocks.append(cur); cur = []
            continue
        if re.fullmatch(r"(?:section|bo'lim|part)?\s*\d{1,2}\s*[.):]?", line, re.I) and not cur:
            continue  # a bare "1." header line
        cur.append(line)
    if cur:
        blocks.append(cur)
    # "1. Where / at" <blank line> "2. What / At" ... : consecutive numbers continue the same block
    merged = []
    for blk in blocks:
        first = re.match(r"^\s*(\d{1,2})\s*[.):]", blk[0])
        last = None
        if merged:
            lm = re.match(r"^\s*(\d{1,2})\s*[.):]", merged[-1][-1])
            last = int(lm.group(1)) if lm else None
        if first and last is not None and int(first.group(1)) == last + 1:
            merged[-1].extend(blk)
        else:
            merged.append(list(blk))
    return merged


def parse_block(lines):
    """-> (numbered: {n: answer}, ordered: [answer], pairs: [(left, right)])"""
    tokens = []
    for line in lines:
        if len(lines) == 1 and (line.count(",") + line.count(";")) and not re.search(r"\s[-=→]\s|:\s", line) or ";" in line:
            tokens.extend(t.strip() for t in re.split(r"[;,]\s*(?=\S)", line) if t.strip())
        else:
            tokens.append(line)
    numbered, ordered, pairs = {}, [], []
    for tok in tokens:
        m = re.match(r"^\s*(\d{1,2})(?:\s*[.):=\-]\s*|\s+)(?!\|)(\S.*)$", tok)  # "2 are" / "3. is"; not "53 | He was 53"
        if m:
            numbered[int(m.group(1))] = m.group(2).strip()
        elif m := re.match(r"^\s*([A-Za-z']+)\s*(?:->|→|[-=:])\s*(.+)$", tok):
            pairs.append((m.group(1).strip(), m.group(2).strip()))
            ordered.append(tok)
        else:
            ordered.append(tok)
    if numbered and len(numbered) * 2 < len(tokens):
        # only a few lines start with a number ("53 years", "10 miles"): those are answers, not item numbers
        numbered, ordered = {}, list(tokens)
    return numbered, ordered, pairs


def _answer_text(raw):
    return re.sub(r"\s*\|\s*|\s*/\s*(?=\S)", " | ", raw.strip()) if " / " in raw or "|" in raw else raw.strip()


# --------------------------------------------------------------------------- per-kind extraction
def _gap_items(lines):
    items, box, n, open_item = [], "", 0, False
    # a context line such as "I went there ..." belongs to every blank-only line of the exercise
    prefix = next((l for l in lines if re.search(r"(\.{3}|\u2026)\s*$", l) and not BLANK.search(l)), "")
    for line in lines:
        m = ITEM.match(line)
        body = m.group(2) if m else line
        if BLANK.search(body):
            n = int(m.group(1)) if m else n + 1
            text = f"{prefix} {body}".strip() if (prefix and not m) else body
            items.append({"n": n, "text": text})
            open_item = True
        elif m:
            n = int(m.group(1))  # an example item (already answered): skipped, keeps numbering
            open_item = False
        elif line == prefix or re.match(r"^example\b", line, re.I):
            open_item = False
            continue
        elif open_item and items:
            items[-1]["text"] += " " + line  # the sentence continues on the next line ("... this" / "morning.")
        elif not items and not box and 3 <= len(line.split()) <= 12 and not re.search(r"[.?!]$", line):
            box = line
    return items, box


def _mcq_items(lines):
    """-> (items, reading text standing before the first question)"""
    items, cur, pre = [], None, []
    for line in lines:
        m = ITEM.match(line)
        if m and not OPT.match(line):
            body = m.group(2)
            cur = {"n": int(m.group(1)), "text": body, "options": [], "example": bool(re.search(r"\(\w+\)\s*/|/\s*\(\w+\)", body))}
            items.append(cur)
        elif (o := OPT.match(line)) and cur is not None:
            cur["options"].append(o.group(2))
        elif cur is not None and not cur["options"]:
            cur["text"] += " " + line
        elif cur is None:
            pre.append(line)
    out = []
    for it in items:
        if it["example"]:
            continue
        if not it["options"]:  # slash form: "She / Her plays tennis with I / me."
            groups = re.findall(r"([A-Za-z']+)\s*/\s*([A-Za-z']+)", it["text"])
            if groups:
                combos = list(itertools.product(*groups))[:16]
                it["options"] = [" ... ".join(c) for c in combos]
                it["slash"] = [" ".join(c) for c in combos]
        out.append(it)
    text = _join_passage(pre)
    return out, (text if len(text.split()) >= 20 else "")


def _sentence_choice_items(lines):
    """"1. I like leaving early today / I would like to leave early today": two (or more) whole sentences split by a
    slash, the student picks the right one. Wrapped lines are joined to their item. -> items with options, or []."""
    if any(BLANK.search(l) for l in lines):
        return []
    items, cur = [], None
    for line in lines:
        if m := ITEM.match(line):
            cur = {"n": int(m.group(1)), "text": m.group(2)}
            items.append(cur)
        elif cur is not None:
            cur["text"] += " " + line
    out = []
    for it in items:
        parts = [x.strip() for x in re.split(r"\s*/\s*", it["text"]) if x.strip()]
        if not (2 <= len(parts) <= 4 and all(len(x.split()) >= 2 for x in parts)):
            return []  # not this shape: leave the section to the usual reader
        out.append({"n": it["n"], "text": "Which sentence is correct?", "options": parts})
    return out if len(out) >= 2 else []


def _tick_items(lines):
    items, cur = [], None
    for line in lines:
        if BOX.search(line):
            body = BOX.sub("", line).strip()
            m = ITEM.match(body)
            if m and (cur is None or cur["options"] and len(cur["options"]) >= 2 or int(m.group(1)) != (cur or {"n": -1})["n"]):
                cur = {"n": int(m.group(1)), "text": "Tick the correct sentence.", "options": [m.group(2)]}
                items.append(cur)
            elif cur is not None:
                cur["options"].append(body)
        elif (m := ITEM.match(line)) and BOX.search(line) is None and not BLANK.search(line):
            cur = None
    return [i for i in items if len(i["options"]) >= 2]


def _numbered_items(lines):
    items = []
    for line in lines:
        m = ITEM.match(line)
        if m:
            items.append({"n": int(m.group(1)), "text": m.group(2), "example": bool(EXAMPLE.search(m.group(2)))})
    return [i for i in items if not i["example"]]


def _odd_items(lines):
    items, cur = [], None
    for line in lines:
        m = ITEM.match(line)
        if m and len(m.group(2)) <= 90:
            body = m.group(2)
            parts = [p for p in re.split(r"\t+|\s{2,}|,\s*", body) if p]
            if len(parts) < 3:
                parts = body.split()
            cur = {"n": int(m.group(1)), "options": parts}
            items.append(cur)
        elif cur is not None and len(line.split()) <= 3 and len(cur["options"]) < 8:
            cur["options"].append(line)  # one option per line
    return [i for i in items if 3 <= len(i["options"]) <= 8]


def _join_passage(lines):
    """Join wrapped PDF lines into paragraphs. A short first line without a full stop is the heading; a line that is
    clearly shorter than the rest and ends a sentence closes its paragraph."""
    lines = [l.strip() for l in lines if l.strip()]
    if not lines:
        return ""
    head = ""
    if len(lines) > 1 and len(lines[0].split()) <= 8 and not re.search(r"[.!?:]$", lines[0]):
        head, lines = lines[0], lines[1:]
    longest = max(len(l) for l in lines)
    paras, cur = [], []
    for l in lines:
        cur.append(l)
        if re.search(r"[.!?]$", l) and len(l) < 0.72 * longest and len(lines) > 3:
            paras.append(" ".join(cur)); cur = []
    if cur:
        paras.append(" ".join(cur))
    return "\n\n".join(([head] if head else []) + paras)


def _unnumbered_statements(lines):
    """True/False statements that carry no numbers: every full line except the solved example."""
    out = []
    for l in lines:
        if re.search(r"\bTrue\b.*\bFalse\b", l, re.I) or re.match(r"^(ex\.?|example)\b", l, re.I) or len(l.split()) < 3:
            continue
        out.append({"n": len(out) + 1, "text": BOX.sub("", l).strip(), "example": False})
    return out


def _read_questions(lines):
    """Short-answer questions about a text -> (items, text before the first question)."""
    pre, items = [], []
    for l in lines:
        m = ITEM.match(l)
        if m and (items or len(l.split()) <= 25):
            text = re.sub(r"[_.\u2026]{3,}\s*$", "", m.group(2)).strip()
            items.append({"n": int(m.group(1)), "text": text})
        elif items:
            if not BLANK.search(l):
                items[-1]["text"] += " " + l.strip()  # the question continues on the next line
        elif not re.match(r"^example\b", l, re.I):
            pre.append(l)
    return items, _join_passage(pre)


def _tf_split(lines):
    passage, items, seen_item = [], [], False
    has_box = any(BOX.search(l) for l in lines)
    for line in lines:
        m = ITEM.match(BOX.sub(" ", line)) if BOX.search(line) or ITEM.match(line) else None
        if m and (BOX.search(line) or seen_item or not has_box):
            seen_item = True
            marked = bool(re.search(r"[☒☑✓✔✅]", line))  # an already solved example
            items.append({"n": int(m.group(1)), "text": m.group(2).strip(), "example": marked})
        elif not seen_item:
            passage.append(line)
        # lines after an item that are not items = explanation of the example: ignored
    items = [i for i in items if not i["example"]]
    if not items:
        return "", _unnumbered_statements(lines)
    return _join_passage(passage), items


def _numbered_dialogues(lines):
    """Several short dialogues ``1 A ... B ...`` with blanks -> (items, word boxes, text).

    Every blank becomes its own question (numbered 1..k over the whole exercise); ``dlg`` / ``pos`` tell
    which dialogue and which blank of it, so an answer such as ``1. Where / at`` fills both blanks."""
    boxes, example, dialogs, cur = [], "", [], None
    for line in lines:
        m = re.match(r"^(\d{1,2})\s+(.*)$", line)
        if m:
            cur = {"n": int(m.group(1)), "lines": [m.group(2)]}
            dialogs.append(cur)
        elif cur is not None:
            if re.match(r"^[A-Z]\s", line) or not cur["lines"]:
                cur["lines"].append(line)
            else:
                cur["lines"][-1] += " " + line  # the previous sentence continues on this line
        elif re.match(r"^example\b", line, re.I):
            example = line
        elif not BLANK.search(line) and 3 <= len(line.split()) <= 14 and not re.search(r"[.?!:]", line):
            boxes.append(line)
    items, k, paras = [], 0, []
    for d in dialogs:
        out, pos = [], 0
        for ln in d["lines"]:
            def repl(_m):
                nonlocal k, pos
                k += 1
                items.append({"n": k, "text": f"Blank {k}", "dlg": d["n"], "pos": pos})
                pos += 1
                return f"[[{k}]]"
            ln = re.sub(r"_{2,}", repl, ln)
            sp = re.match(r"^([A-Z])\s+(.*)$", ln)
            out.append(f"{sp.group(1)}: {sp.group(2)}" if sp else ln)
        paras.append(f"{d['n']}.\n" + "\n".join(out))
    text = "\n\n".join(([example] if example else []) + paras)
    return items, "   |   ".join(boxes), text


def _writing_items(lines, title=""):
    """Writing tasks -> [{"n", "text", "points"}]. Numbered prompts are separate tasks, otherwise the body is one task."""
    lines = [l for l in lines if not re.match(r"^example\b", l, re.I)]
    items = []
    for l in lines:
        m = ITEM.match(l)
        if m:
            items.append({"n": int(m.group(1)), "text": m.group(2).strip()})
        elif items:
            items[-1]["text"] += " " + l.strip()
    if not items:
        items = [{"n": 1, "text": " ".join(lines).strip() or re.sub(r"^\s*writing\W*", "", title, flags=re.I).strip()}]
    pt = re.search(r"[\(\[]\s*(\d+(?:[.,]\d+)?)\s*(?:points?|marks?|ball|pts?)\s*[\)\]]", title, re.I)  # "(10 points)" in the heading
    for it in items:
        pm = re.search(r"[\(\[]\s*(\d+(?:[.,]\d+)?)\s*(?:points?|marks?|ball|pts?)\s*[\)\]]", it["text"], re.I)
        it["points"] = pm.group(1) if pm else (pt.group(1) if pt else "")
        if pm:
            it["text"] = (it["text"][:pm.start()] + it["text"][pm.end():]).strip()
    return items


def _dialogue(lines):
    """Conversation with numbered blanks -> (items, word box, text with one turn per line and [[n]] blanks)."""
    if sum(1 for l in lines if re.match(r"^\d{1,2}\s+[A-Z]\s", l)) >= 2:
        return _numbered_dialogues(lines)
    # intro lines and the word box come before the first speaker line; the box has no sentence punctuation
    box_i = next((i for i, l in enumerate(lines) if not BLANK.search(l) and 3 <= len(l.split()) <= 14 and not re.search(r"[.?!]$", l)
                  and i > 0), None)
    intro = " ".join(lines[:box_i]) if box_i else ""
    box = lines[box_i] if box_i is not None else ""
    body = lines[box_i + 1:] if box_i is not None else lines
    firsts = [l.split()[0] for l in body if l.split()]
    singles = {w for w in set(firsts) if re.fullmatch(r"[A-Z]", w) and firsts.count(w) >= 2}  # "F" / "E"
    names = {w[0]: w for w in firsts if re.fullmatch(r"[A-Z][a-z]{2,7}", w) and w[0] in singles}  # Freya / Evie
    speakers = singles | set(names.values())
    turns = []
    for line in body:
        head, _, rest = line.partition(" ")
        if head in speakers:
            turns.append([names.get(head[0], head), rest.strip()])
        elif turns:
            turns[-1][1] += " " + line.strip()
        else:
            turns.append(["", line.strip()])
    items, counter = [], 0

    def repl(m):
        nonlocal counter
        counter = int(m.group(1)) if m.group(1) else counter + 1
        items.append({"n": counter, "text": f"Blank {counter}"})
        return f"[[{counter}]]"

    out = []
    for who, said in turns:
        said = re.sub(r"^\d{1,2}\s+(?!_)", "", said.strip())  # the number of an already-solved example ("Freya 1 What ...")
        said = re.sub(r"\b(\d{1,2})\s*_{2,}|_{2,}", repl, said)
        out.append(f"{who}: {said.strip()}" if who else said)
    text = "\n".join(out)
    return items, box, (intro + "\n\n" + text) if intro else text


def _gap_text(lines):
    """Text with numbered blanks -> (text with [[n]] markers, [{"n", "text"}], word box)"""
    lines = [l for l in lines if l.strip()]
    box = ""
    if len(lines) > 1 and _looks_like_box(lines[0]) and not BLANK.search(lines[0]):
        box, lines = lines[0], lines[1:]
    paras, cur = [], []
    for l in lines:
        if re.fullmatch(r"[A-Z][A-Z\s'\u2019,.-]{2,60}", l) and len(re.findall(r"[A-Z]", l)) >= 3:  # "HOME", "TRAINING"
            if cur:
                paras.append(" ".join(cur)); cur = []
            paras.append(l)
        else:
            cur.append(l)
    if cur:
        paras.append(" ".join(cur))
    paragraph = "\n\n".join(paras) if len(paras) > 1 and len(paras[0].split()) <= 8 and not re.search(r"[.!?:]$", paras[0]) else " ".join(paras)
    items, counter = [], 0

    def repl(m):
        nonlocal counter
        n = m.group(1) or m.group(2)
        counter = int(n) if n else counter + 1
        items.append({"n": counter, "text": f"Gap {counter}"})
        return f"[[{counter}]]"

    paragraph = re.sub(r"\(\s*(\d{1,2})\s*\)\s*_{2,}|\b(\d{1,2})\s*_{2,}|_{2,}\s*\(\s*(\d{1,2})\s*\)|_{2,}", lambda m: repl(type("M", (), {"group": lambda self, i: (m.group(1) or m.group(2) or m.group(3)) if i in (1, 2) else None})()), paragraph)
    return paragraph, items, box


# --------------------------------------------------------------------------- main entry
def build(text, answers, section_title_limit=220, has_audio=False):
    """Parse ``text`` + ``answers``. Returns a preview dict and the ready-to-save rows."""
    sections = split_sections(text)
    blocks = split_answer_blocks(answers)
    preview, rows = [], []
    notes = []
    last_passage = ""
    if blocks and len(blocks) != len(sections):
        notes.append({"code": "blocks_mismatch", "sections": len(sections), "blocks": len(blocks)})

    for idx, sec in enumerate(sections):
        kind = classify(sec["title"])
        if kind == Category.WORDFORM and any(BLANK.search(l) for l in sec["lines"]):
            kind = Category.GAP  # "Complete the sentences with the past simple of the verbs ...": ordinary gaps
        block = blocks[idx] if idx < len(blocks) else []
        numbered, ordered, pairs = parse_block(block)
        questions = []
        passage, box = "", ""
        title = sec["title"][:section_title_limit]

        choice = _sentence_choice_items(sec["lines"]) if kind in (Category.GAP, Category.MCQ) else []
        if choice:
            kind, items = Category.MCQ, choice  # "A sentence / B sentence": pick the correct one
        elif kind == Category.WORDFORM:
            for left, right in pairs or []:
                questions.append({"n": None, "text": left, "answer": right, "options": [], "type": "FILL", "instruction": title})
            items = []
        elif kind == Category.WRITING:
            items = _writing_items(sec["lines"], sec["title"])
        elif kind == Category.LISTEN:
            ls = sec["lines"]
            if any(OPT.match(l) for l in ls):
                items, _pre = _mcq_items(ls); listen_shape = "MCQ"
            elif any(BLANK.search(l) for l in ls):
                items, box = _gap_items(ls); listen_shape = "FILL"
            elif "true" in sec["title"].lower() and "false" in sec["title"].lower():
                _p, items = _tf_split(ls); listen_shape = "TF"
            else:
                items, _p = _read_questions(ls); listen_shape = "FILL"
        elif kind == Category.READQA:
            items, passage = _read_questions(sec["lines"])
        elif kind == Category.TFREAD:
            passage, items = _tf_split(sec["lines"])
        elif kind == Category.GAPTEXT:
            passage, items, box = _gap_text(sec["lines"])
        elif kind == Category.TICK:
            items = _tick_items(sec["lines"])
        elif kind == Category.MCQ:
            items, passage = _mcq_items(sec["lines"])
        elif kind == Category.ODD:
            items = _odd_items(sec["lines"])
        elif kind == Category.MISTAKE:
            items = _numbered_items(sec["lines"])
        elif kind == Category.DIALOGUE:
            items, box, passage = _dialogue(sec["lines"])
        else:
            items, box = _gap_items(sec["lines"])

        if kind in (Category.TFREAD, Category.READQA) and not passage and last_passage:
            passage = last_passage  # "Read the text again ...": the text of the previous exercise
        if passage and kind in (Category.TFREAD, Category.READQA, Category.MCQ):
            last_passage = passage

        # which answer belongs to which item
        def answer_for(pos, it):
            if numbered and it["n"] in numbered:
                return numbered[it["n"]]
            if not numbered and ordered:
                if kind == Category.GAPTEXT and len(ordered) == len(items) + 1:
                    return ordered[pos + 1]  # the key also lists the already solved example gap first
                if kind == Category.ODD and len(ordered) == len(items) - 1 and pos > 0:
                    return ordered[pos - 1]  # the first row is the already-solved example of the paper
                if pos < len(ordered):
                    return ordered[pos]
            return None

        three = None
        if kind == Category.TFREAD:
            given = [a.strip().lower() for a in [*numbered.values(), *ordered]]
            if any(a in NOT_GIVEN for a in given) or "not given" in sec["title"].lower() or "no information" in sec["title"].lower():
                three = "NOT GIVEN" if ("not given" in sec["title"].lower() or "not given" in given) else "NO INFORMATION"

        for pos, it in enumerate(items):
            if "dlg" in it:  # several blanks per dialogue: "Where / at"
                raw = numbered.get(it["dlg"]) or (ordered[it["dlg"] - 1] if it["dlg"] - 1 < len(ordered) and not numbered else None)
                parts = [x.strip() for x in re.split(r"\s*/\s*|\s*,\s*", raw)] if raw else []
                ans = parts[it["pos"]] if it["pos"] < len(parts) and parts[it["pos"]] else None
            else:
                ans = answer_for(pos, it)
            if three and ans:
                low = ans.strip().lower()
                ans = three if low in NOT_GIVEN else ("TRUE" if low in ("t", "true") else "FALSE" if low in ("f", "false") else ans)
            q = {"n": it["n"], "answer": ans}
            shown_box = re.sub(r"\s{2,}", " \u00b7 ", box.strip()) if box else ""  # words of the box, as laid out in the paper
            if kind == Category.WRITING:
                title = re.sub(r"\s*[\(\[]\s*\d+(?:[.,]\d+)?\s*(?:points?|marks?|ball|pts?)\s*[\)\]]", "", title).strip()
            instruction = title + (f"  [{shown_box}]" if shown_box else "")
            example = next((l for l in sec["lines"] if re.match(r"^example\b", l, re.I)), "")
            if example and kind != Category.DIALOGUE:
                instruction += f"  \u2014 {example}"  # the worked example of the paper stays visible above the group
            q["instruction"] = instruction
            if kind == Category.TICK:
                q.update(text="Which sentence is correct?", options=it["options"], type="MCQ")
            elif kind == Category.MCQ:
                q.update(text=it["text"], options=it["options"], type="MCQ", slash=it.get("slash"))
            elif kind == Category.ODD:
                q.update(text="Which word is different?", options=it["options"], type="MCQ")
            elif kind == Category.TFREAD:
                q.update(text=it["text"], options=["TRUE", "FALSE", three] if three else [], type="MCQ" if three else "TF")
            elif kind == Category.GAPTEXT:
                q.update(text=it["text"], options=[], type="FILL", gap_no=it["n"])
            elif kind == Category.READQA:
                q.update(text=it["text"], options=[], type="FILL")
            elif kind == Category.WRITING:
                q.update(text=it["text"], options=[], type="WRITING", answer="-", points=it.get("points", ""))
            elif kind == Category.LISTEN:
                if listen_shape == "MCQ":
                    q.update(text=it["text"], options=it["options"], type="MCQ", slash=it.get("slash"))
                elif listen_shape == "TF":
                    q.update(text=it["text"], options=[], type="TF")
                else:
                    q.update(text=it["text"], options=[], type="FILL")
            elif kind == Category.DIALOGUE:
                q.update(text=it["text"], options=[], type="FILL", gap_no=it["n"])
            elif kind == Category.MISTAKE:
                q.update(text=it["text"], options=[], type="FILL")
            else:
                q.update(text=it["text"][:480], options=[], type="FILL")
            questions.append(q)

        for q in questions:
            q["status"] = "ok" if q["answer"] else "no_answer"
            if kind == Category.LISTEN and not has_audio and q["status"] == "ok":
                q["status"] = "no_audio"  # the audio track is uploaded together with the text
            if q["answer"] and q["type"] == "MCQ" and not q.get("options"):
                q["status"] = "bad"
            elif (q["answer"] and q["type"] == "MCQ" and not q.get("slash") and not re.fullmatch(r"\s*[A-Ha-h]\s*", q["answer"])
                  and _match_option(q["options"], q["answer"]) is None):
                q["status"] = "bad"  # the answer names none of the options: nothing is guessed
            rows.append(_row(q, kind, passage, sec["title"])) if q["status"] == "ok" else None
        preview.append({
            "index": idx + 1, "printed": sec["printed"], "title": title, "category": kind, "category_label": kind.label,
            "passage": passage[:160], "questions": [
                {k: q.get(k) for k in ("n", "text", "type", "answer", "options", "status")} for q in questions],
            "answers_given": bool(block),
        })
    return {"sections": preview, "notes": notes}, rows


def _words(s):
    return re.sub(r"[\u2018\u2019\u02bc`]", "'", s.lower()).replace("'", "").split()


def _match_option(options, answer):
    """Index of the option the answer names: the same text, or a shortened copy of exactly one option
    ("I would like to leave early" for "I would like to leave early today"), else the clearly closest one."""
    norm = lambda s: re.sub(r"\W", "", " ".join(_words(s)))  # noqa: E731
    a = norm(answer)
    if not a:
        return None
    same = [i for i, o in enumerate(options) if norm(o) == a]
    if same:
        return same[0]
    inside = [i for i, o in enumerate(options) if norm(o).startswith(a) or a.startswith(norm(o))]
    if len(inside) == 1:
        return inside[0]
    aw = set(_words(re.sub(r"[^\w\s'\u2019]", " ", answer)))
    scores = []
    for o in options:
        ow = set(_words(re.sub(r"[^\w\s'\u2019]", " ", o)))
        scores.append(len(aw & ow) / len(aw | ow) if aw | ow else 0)
    best = max(scores, default=0)
    if best >= 0.6 and scores.count(best) == 1:
        return scores.index(best)
    return None


def _row(q, kind, passage, title):
    from .importer import new_row

    options, correct = list(q["options"]), q["answer"] or ""
    if q["type"] == "FILL":
        correct = _answer_text(correct)
    elif q["type"] == "TF":
        correct = "True" if correct.strip().lower() in ("t", "true", "to'g'ri", "togri", "yes") else "False"
    elif q["type"] == "MCQ":
        a = correct.strip()
        if q.get("slash"):  # "I him" -> letter of that combination
            norm = re.sub(r"\s+", " ", a.lower().replace("...", " "))
            hit = [i for i, c in enumerate(q["slash"]) if re.sub(r"\s+", " ", c.lower()) == norm]
            correct = "ABCDEFGH"[hit[0]] if hit else a
        elif not re.fullmatch(r"[A-Ha-h]", a):
            hit = _match_option(options, a)
            correct = "ABCDEFGH"[hit] if hit is not None else a
        else:
            correct = a.upper()
    return new_row(question=q["text"], type=q["type"], section="READING" if (kind == Category.MCQ and passage) else SECTION_OF[kind], options=options, correct=correct,
                   passage=passage if kind in (Category.TFREAD, Category.DIALOGUE, Category.GAPTEXT, Category.MCQ, Category.READQA) else "",
                   category=kind.value, gap_no=q.get("gap_no"), instruction=q.get("instruction", ""),
                   points=q.get("points", ""), listening=(kind == Category.LISTEN))
