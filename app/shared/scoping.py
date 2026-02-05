from __future__ import annotations
from sqlalchemy import Table, select
from sqlalchemy.sql import Select
from typing import Iterable, Optional, Dict
from app.db.reflection import get_table

# A pragmatic scoping strategy based on known FK columns used in PIMA schema.
# If a table is project-scoped, we add joins/filters so users only see rows for their allowed project_ids.

def apply_project_scope(stmt: Select, table: Table, allowed_project_ids: Iterable[str]) -> Select:
    allowed = list(allowed_project_ids)
    if not allowed:
        # No accessible projects => return empty
        return stmt.where(False)

    cols = table.c

    # Direct project_id column
    if "project_id" in cols:
        return stmt.where(cols.project_id.in_(allowed))

    # farmer_groups.project_id
    if "farmer_group_id" in cols:
        fg = get_table("farmer_groups")
        stmt = stmt.select_from(table.join(fg, cols.farmer_group_id == fg.c.id))
        return stmt.where(fg.c.project_id.in_(allowed))

    # training_sessions -> farmer_groups -> project_id
    if "training_session_id" in cols:
        ts = get_table("training_sessions")
        fg = get_table("farmer_groups")
        stmt = stmt.select_from(
            table.join(ts, cols.training_session_id == ts.c.id).join(fg, ts.c.farmer_group_id == fg.c.id)
        )
        return stmt.where(fg.c.project_id.in_(allowed))

    # farm_visits -> training_sessions -> farmer_groups -> project_id
    if "farm_visit_id" in cols:
        fv = get_table("farm_visits")
        ts = get_table("training_sessions")
        fg = get_table("farmer_groups")
        stmt = stmt.select_from(
            table.join(fv, cols.farm_visit_id == fv.c.id)
                 .join(ts, fv.c.training_session_id == ts.c.id)
                 .join(fg, ts.c.farmer_group_id == fg.c.id)
        )
        return stmt.where(fg.c.project_id.in_(allowed))

    # farms -> farm_visits -> ...
    if "farm_id" in cols:
        farms = get_table("farms")
        fv = get_table("farm_visits")
        ts = get_table("training_sessions")
        fg = get_table("farmer_groups")
        stmt = stmt.select_from(
            table.join(farms, cols.farm_id == farms.c.id)
                 .join(fv, farms.c.farm_visit_id == fv.c.id)
                 .join(ts, fv.c.training_session_id == ts.c.id)
                 .join(fg, ts.c.farmer_group_id == fg.c.id)
        )
        return stmt.where(fg.c.project_id.in_(allowed))

    # observations -> farmer_groups -> project_id
    if "observation_id" in cols:
        obs = get_table("observations")
        fg = get_table("farmer_groups")
        stmt = stmt.select_from(
            table.join(obs, cols.observation_id == obs.c.id).join(fg, obs.c.farmer_group_id == fg.c.id)
        )
        return stmt.where(fg.c.project_id.in_(allowed))

    # fv_best_practices -> farm_visits -> ...
    if "fv_best_practice_id" in cols:
        fvbpa = get_table("fv_best_practices")
        fv = get_table("farm_visits")
        ts = get_table("training_sessions")
        fg = get_table("farmer_groups")
        stmt = stmt.select_from(
            table.join(fvbpa, cols.fv_best_practice_id == fvbpa.c.id)
                 .join(fv, fvbpa.c.farm_visit_id == fv.c.id)
                 .join(ts, fv.c.training_session_id == ts.c.id)
                 .join(fg, ts.c.farmer_group_id == fg.c.id)
        )
        return stmt.where(fg.c.project_id.in_(allowed))

    # Default: not project-scoped
    return stmt
