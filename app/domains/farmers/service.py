from sqlalchemy.ext.asyncio import AsyncSession
from .models import table

def before_update(payload: dict, entity: str) -> dict:
    data = dict(payload or {})
    if "send_to_commcare" in table().c:
        data["send_to_commcare"] = True
    if "send_to_commcare_status" in table().c:
        data["send_to_commcare_status"] = "Pending"
    return data
