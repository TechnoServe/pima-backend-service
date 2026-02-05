from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import setup_logging
from app.api.router import router as api_router
from app.db.session import engine
from app.db.reflection import reflect_tables

TABLES = [
    "users",
    "users_temp",
    "images",
    "locations",
    "programs",
    "projects",
    "project_staff_roles",
    "farmer_groups",
    "households",
    "farmers",
    "training_modules",
    "training_sessions",
    "attendances",
    "farm_visits",
    "farms",
    "coffee_varieties",
    "fv_best_practices",
    "fv_best_practice_answers",
    "observations",
    "checks",
    "observation_results",
    "wetmills",
    "wetmill_visits",
    "wv_survey_responses",
    "wv_survey_question_responses",
]

def create_app() -> FastAPI:
    setup_logging()
    app = FastAPI(title=settings.app_name)

    # CORS
    if settings.cors_origins == "*":
        allow_origins = ["*"]
    else:
        allow_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    async def _startup():
        await reflect_tables(engine, TABLES, schema=settings.db_schema)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    app.include_router(api_router, prefix=settings.api_prefix)
    return app

app = create_app()
