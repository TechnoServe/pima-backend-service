from app.shared.domain_factory import build_crud_router

router = build_crud_router(
    entity="coffee_varieties",
    tags=["coffee_varieties"],
    require_project_scope=False,
)
