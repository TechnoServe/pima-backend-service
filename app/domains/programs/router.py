from app.shared.domain_factory import build_crud_router

router = build_crud_router(
    entity="programs",
    tags=["programs"],
    require_project_scope=False,
)
