import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from apps.accounts.models import Role
from apps.core.tests.helpers import client_for, make_exam, make_levels, make_user
from apps.questions.importer import template_xlsx
from apps.questions.models import Question

API = "/api/v1"

TEXT = """1. She ___ a student.
A) is
B) are
C) am
Answer: A
Explanation: third person
2. Select the fruits.
A) apple
B) table
C) banana
Answer: A, C
3. 'Goed' is the past of 'go'.
Answer: False
4. I ___ to school yesterday.
Answer: went | has gone
5. Match the words.
A) cat = animal
B) red = colour
"""


def make_pdf(text):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = 800
    for line in text.splitlines():
        c.drawString(40, y, line)
        y -= 16
    c.save()
    return buf.getvalue()


class ImportTests(TestCase):
    def setUp(self):
        self.L = make_levels()
        self.admin = make_user("admin", Role.ADMIN)
        self.exam, self.variant = make_exam(self.L["B1"], creator=self.admin, n=0)
        self.ac = client_for(self.admin)

    def upload(self, name, data, **extra):
        f = SimpleUploadedFile(name, data)
        return self.ac.post(f"{API}/variants/{self.variant.id}/import/", {"file": f, **extra}, format="multipart")

    def test_pdf_import_creates_questions_in_variant(self):
        r = self.upload("test.pdf", make_pdf(TEXT.replace("5. Match the words.\nA) cat = animal\nB) red = colour\n", "")))
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["created"], 4)
        self.assertEqual(self.variant.variant_questions.count(), 4)
        types = list(Question.objects.order_by("id").values_list("question_type", flat=True))
        self.assertEqual(types, ["MCQ", "MSQ", "TF", "FILL"])
        self.assertEqual(Question.objects.get(text__startswith="She").explanation, "third person")

    def test_txt_with_matching_and_xlsx_template_roundtrip(self):
        r = self.upload("t.txt", TEXT.encode(), section="VOCABULARY")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(Question.objects.get(text__startswith="Match").question_type, "MATCH")
        self.assertEqual(Question.objects.get(text__startswith="Select").section, "VOCABULARY")
        r2 = self.upload("template.xlsx", template_xlsx())
        self.assertEqual(r2.status_code, 201, r2.content)
        self.assertEqual(r2.json()["created"], 7)

    def test_csv(self):
        csv_data = "type,question,A,B,correct\nMCQ,What is 2+2?,3,4,B\n,Capital of Uzbekistan?,Tashkent,Samarkand,Tashkent\n"
        r = self.upload("q.csv", csv_data.encode())
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(Question.objects.count(), 2)

    def test_bad_rows_are_skipped_and_reported_but_good_ones_import(self):
        bad = "type,question,A,B,correct\nMCQ,Good one,x,y,A\nMCQ,No correct marker,x,y,Z\nMCQ,,x,y,A\n"
        r = self.upload("q.csv", bad.encode())
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["created"], 1)
        self.assertEqual([e["row"] for e in r.json()["skipped"]], [2, 3])
        self.assertEqual(Question.objects.count(), 1)
        # nothing importable at all -> 400 and nothing saved
        none = self.upload("n.csv", b"type,question,A,B,correct\nMCQ,Only bad,x,y,Z\n")
        self.assertEqual(none.status_code, 400)

    def test_every_question_type_in_one_pdf(self):
        text = """Passage: Tom gets up at seven. He walks to school.
1. When does Tom get up?
A) At six
B) At seven
Answer: B
2. How does Tom go to school?
A) By bus
B) On foot
Answer: B
3. The sun rises in the west.
Answer: False
4. Yesterday I ___ a film.
Answer: saw | watched
5. Pick the colours.
A) red
B) chair
C) blue
Answer: A, C
6. Match the words.
A) cat = animal
B) red = colour
7. Which word do you hear first?
Type: LISTENING
A) dog
B) cat
Answer: B
"""
        audio = SimpleUploadedFile("track.mp3", b"ID3fakeaudio")
        r = self.upload("all.pdf", make_pdf(text), audio=audio)
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["created"], 7, r.json()["skipped"])
        types = list(Question.objects.order_by("id").values_list("question_type", flat=True))
        self.assertEqual(types, ["READING", "READING", "TF", "FILL", "MSQ", "MATCH", "LISTENING"])
        reading = Question.objects.filter(question_type="READING")
        self.assertEqual(reading[0].passage_id, reading[1].passage_id)  # one shared passage
        self.assertIn("Tom gets up", reading[0].passage.text)
        self.assertTrue(Question.objects.get(question_type="LISTENING").passage.audio)

    def test_listening_without_audio_is_skipped_with_reason(self):
        r = self.upload("l.txt", b"1. Hear?\nType: LISTENING\nA) a\nB) b\nAnswer: A\n2. Plain?\nA) x\nB) y\nAnswer: B\n")
        self.assertEqual(r.json()["created"], 1)
        self.assertIn("audio", r.json()["skipped"][0]["message"])

    def test_rejects_unsupported_and_locked(self):
        self.assertEqual(self.upload("x.exe", b"abc").status_code, 400)
        self.assertEqual(self.upload("empty.pdf", make_pdf("")).json()["errors"][0]["message"], "no_text_in_pdf")
        # a variant of an exam students already took cannot be changed
        from apps.core.tests.helpers import make_student
        from apps.examinations.services import create_assignments, start_attempt
        exam, v = make_exam(self.L["A2"], creator=self.admin, n=2)
        stu = make_student("s", self.L["A2"])
        create_assignments(examination=exam, students=[stu], assigned_by=self.admin)
        start_attempt(assignment_id=stu.assignments.get().id, student=stu, started_by=stu.user)
        r = self.ac.post(f"{API}/variants/{v.id}/import/", {"file": SimpleUploadedFile("a.txt", TEXT.encode())}, format="multipart")
        self.assertEqual(r.status_code, 409)

    def test_template_download_and_permissions(self):
        self.assertTrue(self.ac.get(f"{API}/variants/import-template/").content.startswith(b"PK"))
        stu = make_user("stu", Role.STUDENT)
        self.assertEqual(client_for(stu).get(f"{API}/variants/import-template/").status_code, 403)
        other = make_user("t2", Role.TEACHER)  # not the owner of the exam
        r = client_for(other).post(f"{API}/variants/{self.variant.id}/import/", {"file": SimpleUploadedFile("a.txt", TEXT.encode())}, format="multipart")
        self.assertEqual(r.status_code, 404)



TEXT_EXAM = """ENGLISH TEST
STUDENT'S FULL NAME: ____________
1. Complete the sentences. Use is/are or have/has.
1 I have two sisters.
2 My sisters _________ both very pretty.
3 Our house _________ a big garden.
2. Put the prepositions in the correct place.
at in on last yesterday
on Wednesday
_________ 8 o'clock
I went there …
_________ 2017
3. Choose question words and put them in the correct place.
Evie is talking to her friend Freya.
when where who
Freya 1 What are you doing?
F Oh, 2 _________ are you going?
F 3 _________ are you going with?
4. Tick (✓) the correct sentence.
1
☐
I like leave early today.
☐
I'd like to leave early today.
2
☐
Do you like your job?
☐
Would you like your job?
5. Find the mistake
1 What are you doing this evening? (example)
2 I'm going see some friends tonight.
3 She seeing the doctor tomorrow.
6. Find the odd one
Underline the one that is different.
1
train
bus
bridge
motorbike
2
wife
waiter
daughter
grandfather
7. Write past simple of the verbs
get got do
buy go
8. Read the article. Are the sentences true or false?
Football star David Beckham has a family.
They have four children.
1
☒
The Beckhams' children are all boys.
No, they aren't.
2
☐
David Beckham is a footballer.
3
☐
Louise is David's sister.
"""
TEXT_KEY = """are, has

at, in

where, who

B, A

I'm going to see some friends tonight; She is seeing the doctor tomorrow

bridge, waiter

do - did
buy - bought

True, False"""


class TextImportTests(TestCase):
    def setUp(self):
        self.L = make_levels()
        self.admin = make_user("admin", Role.ADMIN)
        self.exam, self.variant = make_exam(self.L["A1"], creator=self.admin, n=0)
        self.ac = client_for(self.admin)
        self.url = f"{API}/variants/{self.variant.id}/text-import/"

    def test_preview_shows_every_exercise_type(self):
        r = self.ac.post(self.url, {"text": TEXT_EXAM, "answers": TEXT_KEY}, format="json").json()
        cats = [s["category"] for s in r["sections"]]
        self.assertEqual(cats, ["GAP", "GAP", "DIALOGUE", "TICK", "MISTAKE", "ODD", "WORDFORM", "TFREAD"])
        counts = [len(s["questions"]) for s in r["sections"]]
        self.assertEqual(counts, [2, 2, 2, 2, 2, 2, 2, 2])
        self.assertEqual(r["ready"], 16)
        self.assertEqual(Question.objects.count(), 0)  # preview saves nothing

    def test_save_creates_graded_questions_with_categories(self):
        r = self.ac.post(self.url, {"text": TEXT_EXAM, "answers": TEXT_KEY, "save": True}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["created"], 16)
        by_cat = {}
        for q in Question.objects.order_by("id"):
            by_cat.setdefault(q.category, []).append(q)
        self.assertEqual({c: len(v) for c, v in by_cat.items()},
                         {"GAP": 4, "DIALOGUE": 2, "TICK": 2, "MISTAKE": 2, "ODD": 2, "WORDFORM": 2, "TFREAD": 2})
        tick = by_cat["TICK"][0]
        self.assertEqual([o.text for o in tick.options.all() if o.is_correct], ["I'd like to leave early today."])
        odd = by_cat["ODD"][0]
        self.assertEqual([o.text for o in odd.options.all() if o.is_correct], ["bridge"])
        self.assertEqual({q.question_type for q in by_cat["TFREAD"]}, {"TF"})
        self.assertIn("David Beckham", by_cat["TFREAD"][0].passage.text)  # shared reading text
        self.assertEqual(by_cat["TFREAD"][0].passage_id, by_cat["TFREAD"][1].passage_id)
        self.assertEqual(by_cat["WORDFORM"][0].options.get().text, "did")
        # the example items (already solved in the paper) are not imported
        self.assertFalse(Question.objects.filter(text__contains="this evening").exists())
        self.assertEqual(self.variant.variant_questions.count(), 16)
        # filter the bank by exercise type
        self.assertEqual(self.ac.get(f"{API}/questions/?category=TICK").json()["count"], 2)

    def test_missing_answers_are_reported_not_guessed(self):
        r = self.ac.post(self.url, {"text": TEXT_EXAM, "answers": "are", "save": True}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["created"], 1)
        self.assertEqual(r.json()["missing_answers"], 13)  # word-formation verbs come from the key itself

    def test_typed_answers_ignore_end_punctuation_and_curly_quotes(self):
        from apps.questions.grading import normalize_text
        self.assertEqual(normalize_text("I’m going to see friends tonight."), normalize_text("I'm going to see friends tonight"))

    def test_requires_text_and_staff_role(self):
        self.assertEqual(self.ac.post(self.url, {"text": "  "}, format="json").status_code, 400)
        stu = make_user("stu", Role.STUDENT)
        self.assertEqual(client_for(stu).post(self.url, {"text": TEXT_EXAM}, format="json").status_code, 403)


class ReadingLayoutImportTests(TestCase):
    def setUp(self):
        self.L = make_levels()
        self.admin = make_user("admin", Role.ADMIN)
        self.exam, self.variant = make_exam(self.L["A1"], creator=self.admin, n=0)
        self.ac = client_for(self.admin)
        self.url = f"{API}/variants/{self.variant.id}/text-import/"

    def test_gaps_in_a_text_become_numbered_blanks_of_one_passage(self):
        text = """1. Fill in the gaps in the text.
In many cities, empty plots of land are being turned into community gardens. Local residents share the work of planting, watering and (1) _______ the vegetables they grow. Most gardens are run by volunteers, and anyone who lives in the (2) _______ can join."""
        r = self.ac.post(self.url, {"text": text, "answers": "harvesting, area", "save": True}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        qs = list(Question.objects.order_by("gap_no"))
        self.assertEqual([(q.category, q.question_type, q.gap_no) for q in qs], [("GAPTEXT", "FILL", 1), ("GAPTEXT", "FILL", 2)])
        self.assertEqual(qs[0].passage_id, qs[1].passage_id)
        self.assertIn("[[1]]", qs[0].passage.text)
        self.assertIn("[[2]]", qs[0].passage.text)
        self.assertEqual(qs[1].options.get().text, "area")

    def test_true_false_no_information_has_three_buttons(self):
        text = """9. Read the text. Choose True, False or No Information.
Sleep and memory. Scientists believed the brain rested during sleep.
1 Scientists have always known the brain is active during sleep.
2 The students learned the words in the evening.
3 The students who stayed awake were paid."""
        r = self.ac.post(self.url, {"text": text, "answers": "False, True, NG", "save": True}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        qs = list(Question.objects.order_by("id"))
        self.assertEqual([o.text for o in qs[0].options.all()], ["TRUE", "FALSE", "NO INFORMATION"])
        correct = [[o.text for o in q.options.all() if o.is_correct][0] for q in qs]
        self.assertEqual(correct, ["FALSE", "TRUE", "NO INFORMATION"])
        self.assertEqual({q.category for q in qs}, {"TFREAD"})


class WrappedHeadingAndTwoBlanksTests(TestCase):
    def test_unnumbered_wrapped_heading_and_two_blanks_per_dialogue(self):
        L = make_levels()
        admin = make_user("admin", Role.ADMIN)
        exam, variant = make_exam(L["A1"], creator=admin, n=0)
        text = """ Complete the dialogues with question words and prepositions from
the boxes.
When What Where Who How When What When
on in at in at on from in
Example: A When do you usually go out? B On Friday nights.
1 A ________ do you live?
B In London. But I go to my parents' house
________ the weekend.
2 A ________ time do you get up?
B ________ eight o'clock.
"""
        answers = "1. Where / at\n\n2. What / At\n"  # one numbered answer per paragraph, two answers each
        c = client_for(admin)
        url = f"{API}/variants/{variant.id}/text-import/"
        r = c.post(url, {"text": text, "answers": answers}, format="json").json()
        self.assertEqual(len(r["sections"]), 1, r)
        self.assertEqual(r["sections"][0]["category"], "DIALOGUE")
        self.assertEqual([q["answer"] for q in r["sections"][0]["questions"]], ["Where", "at", "What", "At"])
        self.assertEqual(c.post(url, {"text": text, "answers": answers, "save": True}, format="json").json()["created"], 4)
        qs = list(Question.objects.order_by("gap_no"))
        self.assertEqual([q.gap_no for q in qs], [1, 2, 3, 4])
        self.assertEqual(len({q.passage_id for q in qs}), 1)
        self.assertIn("B: In London. But I go to my parents' house [[2]] the weekend.", qs[0].passage.text)
        self.assertTrue(qs[0].instruction.startswith("Complete the dialogues with question words and prepositions from the boxes."))


class PastSimpleGapsTests(TestCase):
    def test_complete_with_past_simple_is_ordinary_gap_filling(self):
        L = make_levels()
        admin = make_user("admin", Role.ADMIN)
        exam, variant = make_exam(L["A1"], creator=admin, n=0)
        text = """Complete the sentences with the past simple of
the verbs in brackets.
Example: Peter was (be) in London yesterday.
1 I ________ (study) history at university.
2 Joe ________ (have) eggs for breakfast this
morning.
3 Sally ________ (go) to the gym yesterday
evening.
"""
        c = client_for(admin)
        r = c.post(f"{API}/variants/{variant.id}/text-import/", {"text": text, "answers": "studied\nhad\nwent"}, format="json").json()
        self.assertEqual([s["category"] for s in r["sections"]], ["GAP"])
        self.assertEqual([(q["n"], q["answer"], q["status"]) for q in r["sections"][0]["questions"]], [(1, "studied", "ok"), (2, "had", "ok"), (3, "went", "ok")])
        self.assertEqual(r["sections"][0]["questions"][1]["text"], "Joe ________ (have) eggs for breakfast this morning.")
        saved = c.post(f"{API}/variants/{variant.id}/text-import/", {"text": text, "answers": "studied\nhad\nwent", "save": True}, format="json")
        self.assertEqual(saved.json()["created"], 3)
        self.assertIn("Example: Peter was (be) in London yesterday.", Question.objects.first().instruction)


class HeadingWithoutKeywordTests(TestCase):
    def test_question_style_heading_and_gaps_at_the_end_of_the_line(self):
        L = make_levels()
        admin = make_user("admin", Role.ADMIN)
        exam, variant = make_exam(L["A1"], creator=admin, n=0)
        text = """What's the next word?
Example: breakfast, lunch, dinner
1 yesterday, today, ________
2 sixth, seventh, ________
3 June, July, ________
"""
        c = client_for(admin)
        r = c.post(f"{API}/variants/{variant.id}/text-import/", {"text": text, "answers": "tomorrow\neighth\nAugust"}, format="json").json()
        sec = r["sections"][0]
        self.assertEqual((sec["title"], sec["category"]), ("What's the next word?", "GAP"))
        self.assertEqual([(q["n"], q["text"], q["answer"]) for q in sec["questions"]],
                         [(1, "yesterday, today, ________", "tomorrow"), (2, "sixth, seventh, ________", "eighth"), (3, "June, July, ________", "August")])
        saved = c.post(f"{API}/variants/{variant.id}/text-import/", {"text": text, "answers": "tomorrow\neighth\nAugust", "save": True}, format="json").json()
        self.assertEqual(saved["created"], 3)
        self.assertIn("Example: breakfast, lunch, dinner", Question.objects.first().instruction)


class TextWithNumberedGapsTests(TestCase):
    TEXT = """1. live come speak have (x2) eat swim drink like want
THE BEST SWIMMER IN THE WORLD
Michael Phelps has 14 Olympic gold medals.
HOME
'I (1) come from Baltimore, USA. My father is a police officer. I (2) ________ two sisters, both older
than me. I still (3) ________ in Baltimore.
TRAINING
I (4) ________ 10 miles, that's 16
kilometres, every day.
"""

    def test_one_text_with_inline_gaps_and_a_solved_example(self):
        L = make_levels()
        admin = make_user("admin", Role.ADMIN)
        exam, variant = make_exam(L["A1"], creator=admin, n=0)
        c = client_for(admin)
        url = f"{API}/variants/{variant.id}/text-import/"
        for key in ("have\nlive\nswim", "come\nhave\nlive\nswim"):  # the key may or may not list the example gap
            r = c.post(url, {"text": self.TEXT, "answers": key}, format="json").json()
            sec = r["sections"][0]
            self.assertEqual((len(r["sections"]), sec["category"]), (1, "GAPTEXT"))
            self.assertEqual([(q["n"], q["answer"]) for q in sec["questions"]], [(2, "have"), (3, "live"), (4, "swim")])
        saved = c.post(url, {"text": self.TEXT, "answers": "have\nlive\nswim", "save": True}, format="json").json()
        self.assertEqual(saved["created"], 3)
        qs = list(Question.objects.order_by("gap_no"))
        self.assertEqual([q.gap_no for q in qs], [2, 3, 4])
        text = qs[0].passage.text
        self.assertTrue(text.startswith("THE BEST SWIMMER IN THE WORLD\n\n"))
        self.assertIn("I (1) come from Baltimore", text)          # the solved example stays in the text
        self.assertIn("I [[2]] two sisters", text)
        self.assertIn("\n\nHOME\n\n", text)
        self.assertIn("10 miles", text)                         # a number after a blank is not a gap number
        self.assertIn("live come speak have (x2) eat swim drink like want", qs[0].instruction)


class ReadingMultipleChoiceTests(TestCase):
    def test_reading_text_with_multiple_choice_questions(self):
        L = make_levels()
        admin = make_user("admin", Role.ADMIN)
        exam, variant = make_exam(L["A1"], creator=admin, n=0)
        text = """1. Read the text and choose the correct answer.
SLEEP AND MEMORY
For a long time, scientists believed that the brain simply rested during sleep. Research over the past thirty
years has shown that this is not the case. While we sleep, the brain replays information from the day.
1 What did scientists believe for a long time?
A) The brain rests during sleep.
B) The brain is very active.
C) The brain stops working.
2 What does the brain do while we sleep?
A) It forgets the day.
B) It replays information.
C) It makes new words.
"""
        c = client_for(admin)
        url = f"{API}/variants/{variant.id}/text-import/"
        r = c.post(url, {"text": text, "answers": "A, B"}, format="json").json()
        self.assertEqual([(s["category"], len(s["questions"])) for s in r["sections"]], [("MCQ", 2)])
        self.assertEqual(c.post(url, {"text": text, "answers": "A, B", "save": True}, format="json").json()["created"], 2)
        qs = list(Question.objects.order_by("id"))
        self.assertEqual({(q.question_type, q.section) for q in qs}, {("READING", "READING")})
        self.assertEqual(qs[0].passage_id, qs[1].passage_id)
        self.assertTrue(qs[0].passage.text.startswith("SLEEP AND MEMORY\n\nFor a long time"))
        self.assertEqual([[o.text for o in q.options.all() if o.is_correct][0] for q in qs],
                         ["The brain rests during sleep.", "It replays information."])


class ReadingShortAnswersTests(TestCase):
    TEXT = """1. Read the text and answer the questions.
Isambard Brunel
Isambard Brunel was a great engineer. He built bridges, railways, tunnels, and boats. But
what do we know about his life and work?
Brunel was born in Portsmouth in the south of England on 9th April 1806. His mother was
English, but his father, Marc Brunel, was French. His father was a famous engineer in
France, but he left his country in 1793.
Brunel wasn't a good businessman. He was only 53 when
he died.
Example: What was Isambard Brunel's job? He was an engineer.
1 Where was Isambard Brunel from? ______________________________
2 How old was he when he died? ______________________________
Read the text again and tick (\u2713) True or False.
Ex. Brunel wasn\u2019t an engineer. \u2014 True \u2610 False \u2612
Brunel\u2019s mother was French.
Brunel spoke two languages.
"""

    def test_short_answers_and_unnumbered_true_false_share_one_text(self):
        L = make_levels()
        admin = make_user("admin", Role.ADMIN)
        exam, variant = make_exam(L["A1"], creator=admin, n=0)
        c = client_for(admin)
        url = f"{API}/variants/{variant.id}/text-import/"
        answers = "England | He was from England\n53\n\nFalse, True"
        r = c.post(url, {"text": self.TEXT, "answers": answers}, format="json").json()
        self.assertEqual([(s["category"], len(s["questions"])) for s in r["sections"]], [("READQA", 2), ("TFREAD", 2)])
        self.assertEqual(r["sections"][0]["questions"][0]["text"], "Where was Isambard Brunel from?")  # the blank line is not part of it
        self.assertEqual(c.post(url, {"text": self.TEXT, "answers": answers, "save": True}, format="json").json()["created"], 4)
        qs = list(Question.objects.order_by("id"))
        self.assertEqual(len({q.passage_id for q in qs}), 1)                     # "the text again" = the same text
        self.assertTrue(qs[0].passage.text.startswith("Isambard Brunel\n\nIsambard Brunel was a great engineer."))
        self.assertEqual([q.question_type for q in qs], ["FILL", "FILL", "TF", "TF"])
        self.assertIn("Example: What was Isambard Brunel's job?", qs[0].instruction)
        self.assertEqual(sorted(o.text for o in qs[0].options.all()), ["England", "He was from England"])


class WritingAndListeningTests(TestCase):
    TEXT = """1. Listen and choose the correct answer.
1 Where does Tom live?
A) In London
B) In Leeds
2 What time does he get up?
A) At six
B) At seven
2. Listen and complete the sentences.
1 Tom gets up at ________ o'clock.
3. Writing. Write an email to a friend about your weekend. (10 points)
Write 80-100 words.
"""

    def setUp(self):
        self.L = make_levels()
        self.admin = make_user("admin", Role.ADMIN)
        self.exam, self.variant = make_exam(self.L["A1"], creator=self.admin, n=0)
        self.c = client_for(self.admin)
        self.url = f"{API}/variants/{self.variant.id}/text-import/"

    def test_preview_tells_that_the_audio_is_missing(self):
        r = self.c.post(self.url, {"text": self.TEXT, "answers": "A, B\n\nseven"}, format="json").json()
        self.assertEqual([s["category"] for s in r["sections"]], ["LISTEN", "LISTEN", "WRITING"])
        self.assertEqual([q["status"] for q in r["sections"][0]["questions"]], ["no_audio", "no_audio"])
        self.assertEqual(r["sections"][2]["questions"][0]["status"], "ok")   # writing needs no answer key
        self.assertEqual(r["ready"], 1)

    def test_listening_with_audio_and_a_writing_task_are_saved(self):
        audio = SimpleUploadedFile("track.mp3", b"ID3audio")
        r = self.c.post(self.url, {"text": self.TEXT, "answers": "A, B\n\nseven", "save": "true", "audio": audio}, format="multipart")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["created"], 4, r.json())
        qs = {q.text[:12]: q for q in Question.objects.all()}
        mcq, gap = qs["Where does T"], qs["Tom gets up "]
        self.assertEqual((mcq.question_type, mcq.section, mcq.category), ("LISTENING", "LISTENING", "LISTEN"))
        self.assertEqual((gap.question_type, gap.section), ("FILL", "LISTENING"))
        self.assertTrue(mcq.passage.audio and mcq.passage_id == gap.passage_id)       # one audio track for the exercise
        w = Question.objects.get(question_type="WRITING")
        self.assertEqual((w.section, w.category, float(w.points)), ("WRITING", "WRITING", 10.0))
        self.assertEqual(w.text, "Write 80-100 words.")
        self.assertEqual(w.instruction, "Writing. Write an email to a friend about your weekend.")   # the task stays in the heading, once
        self.assertEqual(w.options.count(), 0)


class NumberedItemsStartingWithHeadingWords(TestCase):
    """"4. Make ___" / "8. Find ___" inside one list are items, not new exercises."""

    def test_one_exercise_ten_answers(self):
        from apps.questions.text_import import build

        verbs = ["Go", "Come", "Have", "Make", "See", "Buy", "Say", "Find", "Catch", "Win"]
        text = "Find the past simple of the VERBS\nFind the past simple of the VERBS\n" + "\n".join(f"{i}. {v} ______" for i, v in enumerate(verbs, 1))
        report, rows = build(text, "went\ncame\nhad\nmade\nsaw\nbought\nsaid\nfound\ncaught\nwon")
        self.assertEqual(len(report["sections"]), 1)
        self.assertEqual(report["sections"][0]["title"], "Find the past simple of the VERBS")
        self.assertEqual([r["correct"] for r in rows], ["went", "came", "had", "made", "saw", "bought", "said", "found", "caught", "won"])
