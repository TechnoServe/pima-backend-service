from __future__ import annotations

import logging
from typing import Dict, Iterable, Optional

from sqlalchemy import MetaData, Table
from sqlalchemy.ext.asyncio import AsyncEngine

import geoalchemy2 

logger = logging.getLogger(__name__)

metadata = MetaData()
_tables: Dict[str, Table] = {}


async def reflect_tables(
    engine: AsyncEngine,
    table_names: Iterable[str],
    schema: Optional[str] = 'pima',
) -> None:
    names = list(table_names)

    # Optional: if you re-run reflection at startup, clear previous state to avoid stale tables
    # metadata.clear()
    # _tables.clear()

    def _do_reflect(sync_conn):
        # SQLAlchemy 2.x style: pass connection as first arg
        # (Works in 1.4+ as well in most cases)
        metadata.reflect(sync_conn, only=names, schema=schema)
        
        print(f"Reflected tables: {list(metadata.tables.keys())}")

        # If your installed SQLAlchemy complains about the line above,
        # switch to the 1.4 style:
        # metadata.reflect(bind=sync_conn, only=names, schema=schema)

    async with engine.connect() as conn:
        await conn.run_sync(_do_reflect)

    for name in names:
        # if schema:
        #     # When schema is provided, SQLAlchemy usually stores as "schema.table"
        #     tbl = metadata.tables.get(f"{schema}.{name}") or metadata.tables.get(name)
        #else:
            # Try common schema-qualified variants if the DB uses schemas
        tbl = (
            metadata.tables.get(name)
            # or metadata.tables.get(f"public.{name}")
            or metadata.tables.get(f"pima.{name}")
        )

        if tbl is None:
            logger.warning("Table not found during reflection: %s", f"{schema}.{name}" if schema else name)
            continue

        _tables[name] = tbl


def get_table(name: str) -> Table:
    tbl = _tables.get(name)
    if tbl is None:
        raise RuntimeError(f"Table '{name}' not reflected. Ensure startup reflection ran.")
    return tbl