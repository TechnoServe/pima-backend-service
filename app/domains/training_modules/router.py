from app.shared.domain_factory import build_crud_router
from .service import before_update, after_update_training_module

router = build_crud_router(
    entity="training_modules",
    tags=["training_modules"],
    require_project_scope=True,
    before_update=before_update,
    after_update_training_module=after_update_training_module,
)
