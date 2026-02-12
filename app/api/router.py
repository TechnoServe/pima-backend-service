from fastapi import APIRouter

from app.auth.router import router as auth_router

# Domain routers
from app.domains.attendances.router import router as attendances_router
from app.domains.checks.router import router as checks_router
from app.domains.coffee_varieties.router import router as coffee_varieties_router
from app.domains.data_verification.router import router as data_verification_router
from app.domains.farm_visits.router import router as farm_visits_router
from app.domains.farmer_groups.router import router as farmer_groups_router
from app.domains.farmers.router import router as farmers_router
from app.domains.farms.router import router as farms_router
from app.domains.fv_best_practice_answers.router import router as fv_best_practice_answers_router
from app.domains.fv_best_practices.router import router as fv_best_practices_router
from app.domains.households.router import router as households_router
from app.domains.images.router import router as images_router
from app.domains.locations.router import router as locations_router
from app.domains.observation_results.router import router as observation_results_router
from app.domains.observations.router import router as observations_router
from app.domains.programs.router import router as programs_router
from app.domains.project_staff_roles.router import router as project_staff_roles_router
from app.domains.projects.router import router as projects_router
from app.domains.training_modules.router import router as training_modules_router
from app.domains.training_sessions.router import router as training_sessions_router
from app.domains.users.router import router as users_router
from app.domains.users_temp.router import router as users_temp_router
from app.domains.wetmills.router import router as wetmills_router
from app.domains.wetmill_visits.router import router as wetmill_visits_router
from app.domains.wv_survey_responses.router import router as wv_survey_responses_router
from app.domains.wv_survey_question_responses.router import router as wv_survey_question_responses_router

router = APIRouter()

router.include_router(auth_router)

router.include_router(users_router)
router.include_router(users_temp_router)

router.include_router(programs_router)
router.include_router(projects_router)
router.include_router(project_staff_roles_router)

router.include_router(locations_router)
router.include_router(images_router)

router.include_router(farmer_groups_router)
router.include_router(households_router)
router.include_router(farmers_router)

router.include_router(training_modules_router)
router.include_router(training_sessions_router)
router.include_router(data_verification_router)
router.include_router(attendances_router)

router.include_router(farm_visits_router)
router.include_router(farms_router)
router.include_router(coffee_varieties_router)
router.include_router(fv_best_practices_router)
router.include_router(fv_best_practice_answers_router)

router.include_router(observations_router)
router.include_router(checks_router)
router.include_router(observation_results_router)

router.include_router(wetmills_router)
router.include_router(wetmill_visits_router)
router.include_router(wv_survey_responses_router)
router.include_router(wv_survey_question_responses_router)
