from datetime import date, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select, update

from app.db.session import get_session
from app.db.reflection import get_table
from app.auth.security import verify_password, hash_password, create_access_token
from app.shared.exceptions import Unauthorized
from app.auth.deps import get_accessible_project_ids, get_current_user
from app.auth.rbac import is_admin
from app.domains.programs.schemas import ProgramSummaryRead
from app.domains.projects.schemas import ProjectSummaryRead

router = APIRouter(prefix="/auth", tags=["auth"])

class LoginRequest(BaseModel):
    email: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict | None = None


def _to_iso(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _normalize_status(value) -> str:
    normalized = (str(value or "").strip().lower())
    return "inactive" if normalized in {"inactive", "in_active", "disabled"} else "active"

@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, session: AsyncSession = Depends(get_session)):
    users = get_table("users")
    res = await session.execute(select(users).where(users.c.email == payload.email))
    row = res.first()
    if not row:
        raise Unauthorized("Invalid credentials")
    user = row[0] if isinstance(row, tuple) else row
    user_dict = dict(user._mapping) if hasattr(user, "_mapping") else dict(user)

    stored = user_dict.get("password") or ""
    if not verify_password(payload.password, stored):
        raise Unauthorized("Invalid credentials")

    # If plain password, upgrade to bcrypt
    if stored and not (stored.startswith("$argon2$")):
        hashed = hash_password(payload.password)
        await session.execute(update(users).where(users.c.id == user_dict["id"]).values(password=hashed))
        await session.commit()

    token = create_access_token(str(user_dict["id"]), extra={"role": user_dict.get("user_role")})
    safe_user = {k: v for k, v in user_dict.items() if k not in {"password"}}
    return TokenResponse(access_token=token, user=safe_user)

# Endpoint to verify token and return user info
@router.get("/me")
async def me(current_user=Depends(get_current_user)):
    safe = {k: v for k, v in current_user.items() if k not in {"password"}}
    return safe


@router.get("/me/projects", response_model=list[ProjectSummaryRead])
async def get_my_projects(
    current_user=Depends(get_current_user),
    accessible_project_ids: list[str] | None = Depends(get_accessible_project_ids),
    session: AsyncSession = Depends(get_session),
):
    projects = get_table("projects")
    farmer_groups = get_table("farmer_groups")
    farmers = get_table("farmers")
    project_staff_roles = get_table("project_staff_roles")

    farmers_counts_stmt = (
        select(
            farmer_groups.c.project_id.label("project_id"),
            func.count(farmers.c.id).label("farmers_count"),
        )
        .select_from(farmer_groups.outerjoin(farmers, farmers.c.farmer_group_id == farmer_groups.c.id))
        .group_by(farmer_groups.c.project_id)
    )
    farmers_counts = {
        str(row.project_id): int(row.farmers_count or 0)
        for row in (await session.execute(farmers_counts_stmt)).all()
        if row.project_id is not None
    }

    trainers_stmt = select(
        project_staff_roles.c.project_id.label("project_id"),
        func.count(project_staff_roles.c.id).label("trainers_count"),
    ).group_by(project_staff_roles.c.project_id)
    if "status" in project_staff_roles.c:
        trainers_stmt = trainers_stmt.where(project_staff_roles.c.status == "Active")
    trainers_counts = {
        str(row.project_id): int(row.trainers_count or 0)
        for row in (await session.execute(trainers_stmt)).all()
        if row.project_id is not None
    }

    project_stmt = select(projects)
    if not is_admin(current_user.get("user_role")):
        allowed = accessible_project_ids or []
        if not allowed:
            return []
        project_stmt = project_stmt.where(projects.c.id.in_(allowed))

    project_rows = (await session.execute(project_stmt)).all()
    response: list[ProjectSummaryRead] = []
    for row in project_rows:
        project = row[0] if isinstance(row, tuple) else row
        project_dict = dict(project._mapping) if hasattr(project, "_mapping") else dict(project)
        project_id = str(project_dict.get("id", ""))
        response.append(
            ProjectSummaryRead(
                id=project_id,
                name=str(project_dict.get("name") or project_dict.get("project_name") or ""),
                country=str(project_dict.get("country") or ""),
                status=_normalize_status(project_dict.get("status")),
                startDate=_to_iso(project_dict.get("start_date")),
                endDate=_to_iso(project_dict.get("end_date")) or None,
                farmersCount=farmers_counts.get(project_id, 0),
                trainersCount=trainers_counts.get(project_id, 0),
            )
        )

    return response


@router.get("/me/programs", response_model=list[ProgramSummaryRead])
async def get_my_programs():
    return [
        ProgramSummaryRead(
            id="ethiopia-nespresso",
            name="Ethiopia Nespresso",
            description="Sustainability program for Ethiopia Nespresso operations.",
            status="active",
            wetmillsCount=0,
            startDate="2024-01-01",
        ),
        ProgramSummaryRead(
            id="ethiopia-regrow-usda",
            name="Ethiopia Regrow USDA",
            description="Sustainability program for Ethiopia Regrow USDA operations.",
            status="active",
            wetmillsCount=0,
            startDate="2024-01-01",
        ),
        ProgramSummaryRead(
            id="ethiopia-crew-gac",
            name="Ethiopia CREW GAC",
            description="Sustainability program for Ethiopia CREW GAC operations.",
            status="active",
            wetmillsCount=0,
            startDate="2024-01-01",
        ),
        ProgramSummaryRead(
            id="kenya-nespresso",
            name="Kenya Nespresso",
            description="Sustainability program for Kenya Nespresso operations.",
            status="active",
            wetmillsCount=0,
            startDate="2024-01-01",
        ),
    ]
