from __future__ import annotations
from sqlalchemy import MetaData, Table
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy import text
from typing import Dict, Iterable, Optional
import logging

logger = logging.getLogger(__name__)

metadata = MetaData()
_tables: Dict[str, Table] = {}

async def reflect_tables(engine: AsyncEngine, table_names: Iterable[str], schema: Optional[str] = None) -> None:
    # Reflect in a sync context via run_sync
    names = list(table_names)
    def _do_reflect(sync_conn):
        metadata.reflect(bind=sync_conn, only=names, schema=schema)
    await engine.run_sync(_do_reflect)

    for name in names:
        key = f"{schema}.{name}" if schema else name
        # MetaData stores tables with schema-qualified keys sometimes.
        if schema:
            tbl = metadata.tables.get(key)
        else:
            tbl = metadata.tables.get(name) or metadata.tables.get(f"public.{name}") or metadata.tables.get(f"pima.{name}")
        if tbl is None:
            logger.warning("Table not found during reflection: %s", key)
            continue
        _tables[name] = tbl

def get_table(name: str) -> Table:
    tbl = _tables.get(name)
    if tbl is None:
        raise RuntimeError(f"Table '{name}' not reflected. Ensure startup reflection ran.")
    return tbl
