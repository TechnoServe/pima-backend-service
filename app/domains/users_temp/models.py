"""Domain model for `users_temp`.

This backend uses runtime table reflection for strong compatibility with the live Postgres schema.
"""
from sqlalchemy import Table
from app.db.reflection import get_table

TABLE_NAME = "users_temp"

def table() -> Table:
    return get_table(TABLE_NAME)
