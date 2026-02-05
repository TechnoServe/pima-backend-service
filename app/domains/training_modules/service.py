from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update, select
from app.db.reflection import get_table
from .models import table

def before_update(payload: dict, entity: str) -> dict:
    return dict(payload or {})

async def after_update_training_module(session: AsyncSession, project_id: str) -> None:
    psr = get_table("project_staff_roles")
    ts = get_table("training_sessions")
    fg = get_table("farmer_groups")

    values_psr = {}
    if "send_to_commcare" in psr.c:
        values_psr["send_to_commcare"] = True
    if "send_to_commcare_status" in psr.c:
        values_psr["send_to_commcare_status"] = "Pending"
    if values_psr:
        await session.execute(update(psr).where(psr.c.project_id == project_id).values(**values_psr))

    values_ts = {}
    if "send_to_commcare" in ts.c:
        values_ts["send_to_commcare"] = True
    if "send_to_commcare_status" in ts.c:
        values_ts["send_to_commcare_status"] = "Pending"
    if values_ts:
        await session.execute(
            update(ts)
            .where(ts.c.farmer_group_id.in_(select(fg.c.id).where(fg.c.project_id == project_id)))
            .values(**values_ts)
        )

    await session.commit()
