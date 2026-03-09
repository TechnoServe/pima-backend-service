from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from .repository import SustainabilityRepository
from .schemas import (
    DistributionResponse,
    SustainabilitySummaryOverviewResponse,
    WetmillVisitsPerWeekItem,
    WetmillVisitsPerWeekResponse,
)


class SustainabilityService:
    def __init__(self, db: AsyncSession):
        self.repo = SustainabilityRepository(db)

    @staticmethod
    def _week_label(week_start: date) -> str:
        week_of_month = ((week_start.day - 1) // 7) + 1
        return f"{week_start.strftime('%b')} W{week_of_month}"

    async def overview(self, *, programme: str, country: str | None) -> SustainabilitySummaryOverviewResponse:
        total_wetmills, total_bas = await self.repo.overview_counts(programme=programme, country=country)
        # `total_bas` is computed as distinct non-null wetmills.user_id for the filtered wetmills dataset.
        return SustainabilitySummaryOverviewResponse(
            total_registered_wetmills=total_wetmills,
            total_bas=total_bas,
        )

    async def wetmill_visits_per_week(
        self,
        *,
        programme: str,
        country: str | None,
        date_from: date | None,
        date_to: date | None,
    ) -> WetmillVisitsPerWeekResponse:
        rows = await self.repo.visits_per_week(
            programme=programme,
            country=country,
            date_from=date_from,
            date_to=date_to,
        )

        items = [
            WetmillVisitsPerWeekItem(
                label=self._week_label(row["week_start"].date()),
                week_start=row["week_start"].date(),
                week_end=(row["week_start"] + timedelta(days=6)).date(),
                visits_count=int(row["visits_count"] or 0),
            )
            for row in rows
            if row.get("week_start") is not None
        ]
        return WetmillVisitsPerWeekResponse(items=items)

    async def ownership_distribution(self, *, programme: str, country: str | None) -> DistributionResponse:
        rows = await self.repo.ownership_distribution(programme=programme, country=country)
        return DistributionResponse(
            items=[{"label": row["label"], "value": int(row["value"] or 0)} for row in rows]
        )

    async def exporter_status_distribution(self, *, programme: str, country: str | None) -> DistributionResponse:
        rows = await self.repo.exporter_distribution(programme=programme, country=country)
        return DistributionResponse(
            items=[{"label": row["label"], "value": int(row["value"] or 0)} for row in rows]
        )
