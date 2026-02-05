from __future__ import annotations
from typing import Any, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.reflection import get_table

async def resolve_project_id_from_payload(table_name: str, payload: Dict[str, Any], session: AsyncSession) -> Optional[str]:
    # direct project_id
    if "project_id" in payload and payload["project_id"]:
        return str(payload["project_id"])

    # farmer_group_id -> farmer_groups.project_id
    if "farmer_group_id" in payload and payload["farmer_group_id"]:
        fg = get_table("farmer_groups")
        res = await session.execute(select(fg.c.project_id).where(fg.c.id == payload["farmer_group_id"]))
        row = res.first()
        return str(row[0]) if row and row[0] is not None else None

    # training_session_id -> training_sessions.farmer_group_id -> farmer_groups.project_id
    if "training_session_id" in payload and payload["training_session_id"]:
        ts = get_table("training_sessions")
        fg = get_table("farmer_groups")
        res = await session.execute(
            select(fg.c.project_id)
            .select_from(ts.join(fg, ts.c.farmer_group_id == fg.c.id))
            .where(ts.c.id == payload["training_session_id"])
        )
        row = res.first()
        return str(row[0]) if row and row[0] is not None else None

    # farm_visit_id -> farm_visits.training_session_id -> ...
    if "farm_visit_id" in payload and payload["farm_visit_id"]:
        fv = get_table("farm_visits")
        ts = get_table("training_sessions")
        fg = get_table("farmer_groups")
        res = await session.execute(
            select(fg.c.project_id)
            .select_from(fv.join(ts, fv.c.training_session_id == ts.c.id).join(fg, ts.c.farmer_group_id == fg.c.id))
            .where(fv.c.id == payload["farm_visit_id"])
        )
        row = res.first()
        return str(row[0]) if row and row[0] is not None else None

    # farm_id -> farms.farm_visit_id -> ...
    if "farm_id" in payload and payload["farm_id"]:
        farms = get_table("farms")
        fv = get_table("farm_visits")
        ts = get_table("training_sessions")
        fg = get_table("farmer_groups")
        res = await session.execute(
            select(fg.c.project_id)
            .select_from(
                farms.join(fv, farms.c.farm_visit_id == fv.c.id)
                     .join(ts, fv.c.training_session_id == ts.c.id)
                     .join(fg, ts.c.farmer_group_id == fg.c.id)
            )
            .where(farms.c.id == payload["farm_id"])
        )
        row = res.first()
        return str(row[0]) if row and row[0] is not None else None

    # observation_id -> observations.farmer_group_id -> project_id
    if "observation_id" in payload and payload["observation_id"]:
        obs = get_table("observations")
        fg = get_table("farmer_groups")
        res = await session.execute(
            select(fg.c.project_id)
            .select_from(obs.join(fg, obs.c.farmer_group_id == fg.c.id))
            .where(obs.c.id == payload["observation_id"])
        )
        row = res.first()
        return str(row[0]) if row and row[0] is not None else None

    # fv_best_practice_id -> fv_best_practices.farm_visit_id -> ...
    if "fv_best_practice_id" in payload and payload["fv_best_practice_id"]:
        fvb = get_table("fv_best_practices")
        fv = get_table("farm_visits")
        ts = get_table("training_sessions")
        fg = get_table("farmer_groups")
        res = await session.execute(
            select(fg.c.project_id)
            .select_from(
                fvb.join(fv, fvb.c.farm_visit_id == fv.c.id)
                   .join(ts, fv.c.training_session_id == ts.c.id)
                   .join(fg, ts.c.farmer_group_id == fg.c.id)
            )
            .where(fvb.c.id == payload["fv_best_practice_id"])
        )
        row = res.first()
        return str(row[0]) if row and row[0] is not None else None

    return None
