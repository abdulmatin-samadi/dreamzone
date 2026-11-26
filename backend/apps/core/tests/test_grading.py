from decimal import Decimal

from django.test import TestCase

from apps.questions.grading import grade, is_blank, validate_answer_shape
from apps.questions.models import AnswerOption, Question, QuestionType, Section
from apps.core.tests.helpers import make_levels


class GradingTests(TestCase):
    def setUp(self):
        self.level = make_levels()["A1"]

    def _q(self, qtype, options, points=2):
        q = Question.objects.create(text="t", question_type=qtype, section=Section.GRAMMAR, level=self.level, points=points)
        opts = [AnswerOption.objects.create(question=q, order=i, **o) for i, o in enumerate(options)]
        return q, opts

    def test_single_choice(self):
        q, (a, b) = self._q(QuestionType.MULTIPLE_CHOICE, [dict(text="a", is_correct=True), dict(text="b")])
        self.assertEqual(grade(q, [a, b], {"option_ids": [a.id]}), (True, Decimal(2)))
        self.assertEqual(grade(q, [a, b], {"option_ids": [b.id]}), (False, Decimal(0)))

    def test_multiple_select_is_all_or_nothing(self):
        q, (a, b, c) = self._q(QuestionType.MULTIPLE_SELECT,
                               [dict(text="a", is_correct=True), dict(text="b", is_correct=True), dict(text="c")])
        self.assertTrue(grade(q, [a, b, c], {"option_ids": [a.id, b.id]})[0])
        self.assertFalse(grade(q, [a, b, c], {"option_ids": [a.id]})[0])
        self.assertFalse(grade(q, [a, b, c], {"option_ids": [a.id, b.id, c.id]})[0])

    def test_fill_blank_is_case_and_space_insensitive(self):
        q, opts = self._q(QuestionType.FILL, [dict(text="Went", is_correct=True), dict(text="has gone", is_correct=True)])
        self.assertTrue(grade(q, opts, {"text": "  went "})[0])
        self.assertTrue(grade(q, opts, {"text": "HAS   GONE"})[0])
        self.assertFalse(grade(q, opts, {"text": "go"})[0])

    def test_matching(self):
        q, opts = self._q(QuestionType.MATCH, [dict(text="cat", match_text="animal"), dict(text="red", match_text="colour")])
        ok = {"pairs": {str(opts[0].id): "animal", str(opts[1].id): "colour"}}
        bad = {"pairs": {str(opts[0].id): "colour", str(opts[1].id): "animal"}}
        self.assertTrue(grade(q, opts, ok)[0])
        self.assertFalse(grade(q, opts, bad)[0])

    def test_blank_answers(self):
        self.assertTrue(is_blank(QuestionType.FILL, {"text": "  "}))
        self.assertTrue(is_blank(QuestionType.MULTIPLE_CHOICE, {}))
        self.assertFalse(is_blank(QuestionType.MULTIPLE_CHOICE, {"option_ids": [1]}))

    def test_shape_validation_rejects_foreign_options(self):
        with self.assertRaises(ValueError):
            validate_answer_shape(QuestionType.MULTIPLE_CHOICE, {"option_ids": [999]}, [1, 2])
        with self.assertRaises(ValueError):
            validate_answer_shape(QuestionType.MULTIPLE_CHOICE, {"option_ids": [1, 2]}, [1, 2])
        self.assertEqual(validate_answer_shape(QuestionType.MULTIPLE_SELECT, {"option_ids": [1, 2]}, [1, 2]),
                         {"option_ids": [1, 2]})
