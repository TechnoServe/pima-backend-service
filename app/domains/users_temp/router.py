from app.shared.domain_factory import build_crud_router

router = build_crud_router(
    entity="users_temp",
    tags=["users_temp"],
    require_project_scope=False,
)
