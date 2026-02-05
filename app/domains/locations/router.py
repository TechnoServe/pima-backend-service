from app.shared.domain_factory import build_crud_router

router = build_crud_router(
    entity="locations",
    tags=["locations"],
    require_project_scope=False,
)
