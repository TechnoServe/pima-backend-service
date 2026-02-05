"""Domain model for `users`.

This backend uses runtime table reflection for strong compatibility with the live Postgres schema.
"""
from sqlalchemy import Table
from app.db.reflection import get_table

TABLE_NAME = "users"

def table() -> Table:
    return get_table(TABLE_NAME)
