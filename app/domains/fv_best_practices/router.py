from app.shared.domain_factory import build_crud_router

router = build_crud_router(
    entity="fv_best_practices",
    tags=["fv_best_practices"],
    require_project_scope=False,
)
