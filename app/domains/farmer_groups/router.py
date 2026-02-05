from app.shared.domain_factory import build_crud_router
from .service import before_update

router = build_crud_router(
    entity="farmer_groups",
    tags=["farmer_groups"],
    require_project_scope=True,
    before_update=before_update,
)
