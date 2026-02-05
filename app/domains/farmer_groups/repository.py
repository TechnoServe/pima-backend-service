from app.shared.crud import CRUDRepository
from .models import table

def get_repository() -> CRUDRepository:
    return CRUDRepository(table())
