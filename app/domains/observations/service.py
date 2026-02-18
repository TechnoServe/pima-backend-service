from __future__ import annotations

import io
from datetime import datetime
from uuid import UUID

from openpyxl import Workbook
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.api_errors import NotFoundError
from app.domains.observation_results.repository import ObservationResultsRepository

from .repository import DemoPlotObservationFilters, ObservationsRepository
from .schemas import DemoPlotObservationListParams


class ObservationsService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = ObservationsRepository(db)
        self.results_repo = ObservationResultsRepository(db)

    @staticmethod
    def _normalize_sort(sort_by: str, sort_dir: str):
        safe_sort = sort_by if sort_by in ObservationsRepository.SORT_ALLOWLIST else "observation_date"
        safe_dir = "asc" if (sort_dir or "").lower() == "asc" else "desc"
        return safe_sort, safe_dir

    @staticmethod
    def _filters(params: DemoPlotObservationListParams):
        return DemoPlotObservationFilters(
            project_id=params.project_id,
            date_from=params.date_from,
            date_to=params.date_to,
            observation_type=params.observation_type,
            search=params.search,
        )

    async def list_demo_plot_observations(self, params: DemoPlotObservationListParams):
        sort_by, sort_dir = self._normalize_sort(params.sort_by, params.sort_dir)
        data, total = await self.repo.list(
            filters=self._filters(params),
            page=params.page,
            page_size=params.page_size,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )
        return {"data": data, "pagination": {"page": params.page, "page_size": params.page_size, "total": total}}

    async def stats(self, *, project_id: UUID, date_from=None, date_to=None, observation_type=None, search=None):
        filters = DemoPlotObservationFilters(
            project_id=project_id,
            date_from=date_from,
            date_to=date_to,
            observation_type=observation_type,
            search=search,
        )
        return await self.repo.stats(filters=filters)

    async def filter_options(self, *, project_id: UUID):
        return {"observation_types": await self.repo.filter_types(filters=DemoPlotObservationFilters(project_id=project_id))}

    async def detail(self, *, project_id: UUID, observation_id: UUID):
        observation = await self.repo.get_detail(observation_id=observation_id, project_id=project_id)
        if not observation:
            raise NotFoundError("Observation not found")
        results = await self.results_repo.list_for_observation(observation_id)
        return {"observation": observation, "results": results}

    async def export_excel(self, params: DemoPlotObservationListParams):
        export_params = params.model_copy(update={"page": 1, "page_size": 100000})
        payload = await self.list_demo_plot_observations(export_params)

        wb = Workbook()
        ws = wb.active
        ws.title = "Demo Plot Observations"
        ws.append([
            "Observation Date", "Observation Type", "Training Group", "Observer", "Trainer", "Results Count",
            "Female Attendees", "Male Attendees", "Total Attendees", "GPS Latitude", "GPS Longitude", "GPS Altitude",
        ])
        for item in payload["data"]:
            ws.append([
                item.get("observation_date"), item.get("observation_type"), item.get("training_group_name"),
                item.get("observer_name"), item.get("trainer_name"), item.get("results_count"),
                item.get("female_attendees"), item.get("male_attendees"), item.get("total_attendees"),
                item.get("location_gps_latitude"), item.get("location_gps_longitude"), item.get("location_gps_altitude"),
            ])
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    @staticmethod
    def export_filename(project_id: UUID) -> str:
        return f"demo_plot_observations_{project_id}_{datetime.now().strftime('%Y%m%d')}.xlsx"
