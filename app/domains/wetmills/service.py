from __future__ import annotations

import csv
import io

from openpyxl import Workbook
from sqlalchemy.ext.asyncio import AsyncSession

from .repository import WetmillsRepository
from .schemas import PaginatedWetmillsResponse, WetmillsFilterOptionsResponse


class WetmillsService:
    def __init__(self, db: AsyncSession):
        self.repo = WetmillsRepository(db)

    async def list_wetmills(
        self,
        *,
        programme: str,
        country: str | None,
        search: str | None,
        exporting_status: str | None,
        mill_status: str | None,
        page: int,
        page_size: int,
    ) -> PaginatedWetmillsResponse:
        rows, total, has_ownership = await self.repo.list_wetmills(
            programme=programme,
            country=country,
            search=search,
            exporting_status=exporting_status,
            mill_status=mill_status,
            page=page,
            page_size=page_size,
        )

        items = []
        for row in rows:
            payload = dict(row)
            if not has_ownership:
                payload["ownership_type"] = None
            items.append(payload)

        return PaginatedWetmillsResponse(items=items, total=total, page=page, page_size=page_size)

    async def filter_options(self, *, programme: str, country: str | None) -> WetmillsFilterOptionsResponse:
        return WetmillsFilterOptionsResponse(**(await self.repo.filter_options(programme=programme, country=country)))

    @staticmethod
    def _export_headers() -> list[str]:
        return [
            "Wetmill ID",
            "Wetmill Name",
            "Country",
            "Programme",
            "Ownership",
            "Exporting Status",
            "Mill Status",
            "Manager Name",
            "Manager Role",
            "Registered On",
            "Created At",
            "Updated At",
        ]

    @staticmethod
    def _export_row(row: dict, has_ownership: bool) -> list[str]:
        return [
            str(row.get("wet_mill_unique_id") or ""),
            str(row.get("name") or ""),
            str(row.get("country") or ""),
            str(row.get("programme") or ""),
            str(row.get("ownership_type") or "") if has_ownership else "",
            str(row.get("exporting_status") or ""),
            str(row.get("mill_status") or ""),
            str(row.get("manager_name") or ""),
            str(row.get("manager_role") or ""),
            row.get("registration_date").isoformat() if row.get("registration_date") else "",
            row.get("created_at").isoformat() if row.get("created_at") else "",
            row.get("updated_at").isoformat() if row.get("updated_at") else "",
        ]

    async def export_excel(
        self,
        *,
        programme: str,
        country: str | None,
        search: str | None,
        exporting_status: str | None,
        mill_status: str | None,
    ) -> bytes:
        rows, has_ownership = await self.repo.list_for_export(
            programme=programme,
            country=country,
            search=search,
            exporting_status=exporting_status,
            mill_status=mill_status,
        )

        wb = Workbook()
        ws = wb.active
        ws.title = "Wetmills"
        ws.append(self._export_headers())
        for row in rows:
            ws.append(self._export_row(dict(row), has_ownership))

        out = io.BytesIO()
        wb.save(out)
        out.seek(0)
        return out.getvalue()

    async def export_csv(
        self,
        *,
        programme: str,
        country: str | None,
        search: str | None,
        exporting_status: str | None,
        mill_status: str | None,
    ) -> bytes:
        rows, has_ownership = await self.repo.list_for_export(
            programme=programme,
            country=country,
            search=search,
            exporting_status=exporting_status,
            mill_status=mill_status,
        )

        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(self._export_headers())
        for row in rows:
            writer.writerow(self._export_row(dict(row), has_ownership))
        return out.getvalue().encode("utf-8")
