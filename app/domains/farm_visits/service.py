from __future__ import annotations

import io
from datetime import datetime
from uuid import UUID

from openpyxl import Workbook
from sqlalchemy.ext.asyncio import AsyncSession

from .repository import FarmVisitFilters, FarmVisitsRepository
from .schemas import FarmVisitsListParams


class FarmVisitsService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = FarmVisitsRepository(db)

    @staticmethod
    def _normalize_sort(sort_by: str, sort_dir: str):
        allowed = FarmVisitsRepository.SORT_ALLOWLIST
        safe_sort = sort_by if sort_by in allowed else "date_visited"
        safe_dir = "asc" if (sort_dir or "").lower() == "asc" else "desc"
        return safe_sort, safe_dir

    @staticmethod
    def _to_filters(params: FarmVisitsListParams) -> FarmVisitFilters:
        return FarmVisitFilters(
            project_id=params.project_id,
            date_from=params.date_from,
            date_to=params.date_to,
            farm_visit_type=params.farm_visit_type,
            search=params.search,
        )

    async def list_farm_visits(self, params: FarmVisitsListParams):
        sort_by, sort_dir = self._normalize_sort(params.sort_by, params.sort_dir)
        filters = self._to_filters(params)
        data, total = await self.repo.list(
            filters=filters,
            page=params.page,
            page_size=params.page_size,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )
        return {"data": data, "pagination": {"page": params.page, "page_size": params.page_size, "total": total}}

    async def stats(self, *, project_id: UUID, date_from=None, date_to=None, farm_visit_type=None, search=None):
        filters = FarmVisitFilters(
            project_id=project_id,
            date_from=date_from,
            date_to=date_to,
            farm_visit_type=farm_visit_type,
            search=search,
        )
        return await self.repo.stats(filters=filters)

    async def filter_options(self, *, project_id: UUID, date_from=None, date_to=None, farm_visit_type=None, search=None):
        filters = FarmVisitFilters(
            project_id=project_id,
            date_from=date_from,
            date_to=date_to,
            farm_visit_type=farm_visit_type,
            search=search,
        )
        return {"farm_visit_types": await self.repo.filter_types(filters=filters)}

    async def export_excel(self, params: FarmVisitsListParams):
        export_params = params.model_copy(update={"page": 1, "page_size": 100000})
        payload = await self.list_farm_visits(export_params)

        wb = Workbook()
        ws = wb.active
        ws.title = "Farm Visits"

        headers = [
            "Date Visited", "Farm Visit Type", "Visit Comments", "GPS Latitude", "GPS Longitude", "GPS Altitude",
            "Number of Cuerdas", "Separate Coffee Fields", "Field Age", "Field Size", "Training Group",
            "Farmer TNS ID", "Farmer Full Name", "Farmer Gender", "Visiting Staff",
        ]
        ws.append(headers)

        for item in payload["data"]:
            ws.append([
                item.get("date_visited"), item.get("farm_visit_type"), item.get("visit_comments"),
                item.get("location_gps_latitude"), item.get("location_gps_longitude"), item.get("location_gps_altitude"),
                item.get("number_of_cuerdas"), item.get("number_of_separate_coffee_fields"), item.get("field_age"),
                item.get("field_size"), item.get("training_group_name"), item.get("farmer_tns_id"),
                item.get("farmer_full_name"), item.get("farmer_gender"), item.get("visiting_staff_name"),
            ])

        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    @staticmethod
    def export_filename(project_id: UUID) -> str:
        return f"farm_visits_{project_id}_{datetime.now().strftime('%Y%m%d')}.xlsx"
