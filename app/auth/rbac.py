from __future__ import annotations
from typing import Iterable, List, Set
from app.shared.exceptions import Forbidden

ALL_ROLES = {
    "CI Leadership",
    "Project Manager",
    "Senior MEL Specialist",
    "MEL Specialist",
    "Business Advisor",
    "Agronomy Advisor",
    "Senior Agronomy Advisor",
    "Senior Business Advisor",
    "Farmer Trainer",
    "Super Admin",
}

ADMIN_ROLES = {"Super Admin"}
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
