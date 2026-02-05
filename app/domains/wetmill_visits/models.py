"""Domain model for `wetmill_visits`.

This backend uses runtime table reflection for strong compatibility with the live Postgres schema.
"""
from sqlalchemy import Table
from app.db.reflection import get_table

TABLE_NAME = "wetmill_visits"

def table() -> Table:
    return get_table(TABLE_NAME)
