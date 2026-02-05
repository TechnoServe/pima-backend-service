from app.shared.domain_factory import build_crud_router

router = build_crud_router(
    entity="wv_survey_responses",
    tags=["wv_survey_responses"],
    require_project_scope=False,
)
