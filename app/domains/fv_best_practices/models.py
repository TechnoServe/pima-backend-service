"""Domain model for `fv_best_practices`.

This backend uses runtime table reflection for strong compatibility with the live Postgres schema.
"""
from sqlalchemy import Table
from app.db.reflection import get_table

TABLE_NAME = "fv_best_practices"

def table() -> Table:
    return get_table(TABLE_NAME)
