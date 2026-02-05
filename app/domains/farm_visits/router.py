from app.shared.domain_factory import build_crud_router

router = build_crud_router(
    entity="farm_visits",
    tags=["farm_visits"],
    require_project_scope=False,
)
