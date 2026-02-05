from app.shared.domain_factory import build_crud_router

router = build_crud_router(
    entity="farms",
    tags=["farms"],
    require_project_scope=False,
)
