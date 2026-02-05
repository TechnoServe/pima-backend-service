"""Domain model for `farms`.

This backend uses runtime table reflection for strong compatibility with the live Postgres schema.
"""
from sqlalchemy import Table
from app.db.reflection import get_table

TABLE_NAME = "farms"

def table() -> Table:
    return get_table(TABLE_NAME)
