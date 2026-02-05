from app.shared.domain_factory import build_crud_router
from .service import before_update

router = build_crud_router(
    entity="farmers",
    tags=["farmers"],
    require_project_scope=True,
    before_update=before_update,
)
