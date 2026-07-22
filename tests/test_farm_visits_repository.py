import unittest

from sqlalchemy import Column, MetaData, Table

from app.domains.farm_visits.repository import resolve_answer_column


class ResolveAnswerColumnTests(unittest.TestCase):
    def test_resolves_deployed_numeric_answer_alias(self):
        answers = Table("fv_best_practice_answers", MetaData(), Column("number_answer"))

        self.assertEqual(
            resolve_answer_column(answers, "numeric_answer").name,
            "number_answer",
        )

    def test_prefers_canonical_answer_column(self):
        answers = Table(
            "fv_best_practice_answers",
            MetaData(),
            Column("numeric_answer"),
            Column("number_answer"),
        )

        self.assertEqual(
            resolve_answer_column(answers, "numeric_answer").name,
            "numeric_answer",
        )


if __name__ == "__main__":
    unittest.main()
