from __future__ import annotations
from typing import Iterable, List, Set
from app.shared.exceptions import Forbidden

ALL_ROLES = {
    "CI Leadership",
    "Project Manager",
    "Senior MEL Specialist",
    "MEL Specialist",
    "Agronomy Advisor",
    "Senior Agronomy Advisor",
    "Senior Business Advisor",
    "Business Advisor",
    "Farmer Trainer",
    "Super Admin",
}

ADMIN_ROLES = {"Super Admin", "Superadmin"}
WRITE_ROLES = {
    "Super Admin",
    "CI Leadership",
    "Project Manager",
    "Senior MEL Specialist",
    "Senior Agronomy Advisor",
    "Senior Business Advisor",
}

def is_admin(user_role: str | None) -> bool:
    return (user_role or "") in ADMIN_ROLES

def can_write(role: str | None) -> bool:
    return (role or "") in WRITE_ROLES

def ensure_can_write(role: str | None) -> None:
    if not can_write(role):
        raise Forbidden("You do not have permission to perform this action")

def ensure_project_access(user_role: str | None, user_project_roles: Set[str]) -> None:
    if is_admin(user_role):
        return  # Admins have access to all projects
    if not user_project_roles:
        raise Forbidden("You do not have access to this project")