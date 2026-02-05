from app.shared.domain_factory import build_crud_router

router = build_crud_router(
    entity="users",
    tags=["users"],
    require_project_scope=False,
)
