"""Domain model for `wv_survey_question_responses`.

This backend uses runtime table reflection for strong compatibility with the live Postgres schema.
"""
from sqlalchemy import Table
from app.db.reflection import get_table

TABLE_NAME = "wv_survey_question_responses"

def table() -> Table:
    return get_table(TABLE_NAME)
