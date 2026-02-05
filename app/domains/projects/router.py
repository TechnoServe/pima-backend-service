from app.shared.domain_factory import build_crud_router

router = build_crud_router(
    entity="projects",
    tags=["projects"],
    require_project_scope=False,
)
