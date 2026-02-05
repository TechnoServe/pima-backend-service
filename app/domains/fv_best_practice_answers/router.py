from app.shared.domain_factory import build_crud_router

router = build_crud_router(
    entity="fv_best_practice_answers",
    tags=["fv_best_practice_answers"],
    require_project_scope=False,
)
