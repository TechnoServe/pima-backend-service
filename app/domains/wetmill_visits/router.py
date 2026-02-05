from app.shared.domain_factory import build_crud_router

router = build_crud_router(
    entity="wetmill_visits",
    tags=["wetmill_visits"],
    require_project_scope=False,
)
