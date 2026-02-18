from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import asyncio

from app.core.config import settings
from app.core.logging import setup_logging
from app.api.router import router as api_router
from app.db.session import engine
from app.db.reflection import reflect_tables
from app.domains.farmers.upload_worker import uploads_cron_loop
from app.domains.training_sessions.sampling_worker import training_session_sampling_cron_loop

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
    print("Setting up logging...")
    setup_logging()
    print("Logging is set up.")
    
    print("Creating FastAPI app...")
    app = FastAPI(title=settings.app_name)
    print("FastAPI app created.")

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
        print("Reflecting database tables...")
        await reflect_tables(engine, TABLES, schema=settings.db_schema)
        print("Database tables reflected successfully.")
        app.state.farmers_upload_worker = asyncio.create_task(uploads_cron_loop())
        app.state.training_session_sampling_worker = asyncio.create_task(training_session_sampling_cron_loop())

    @app.on_event("shutdown")
    async def _shutdown():
        task = getattr(app.state, "farmers_upload_worker", None)
        if task:
            task.cancel()
        sampling_task = getattr(app.state, "training_session_sampling_worker", None)
        if sampling_task:
            sampling_task.cancel()

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    app.include_router(api_router, prefix=settings.api_prefix)
    return app

app = create_app()
