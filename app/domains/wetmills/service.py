from __future__ import annotations

import csv
import io

from openpyxl import Workbook
from sqlalchemy.ext.asyncio import AsyncSession

from .repository import WetmillsRepository
from .schemas import PaginatedWetmillsResponse, WetmillsFilterOptionsResponse


class WetmillsService:
    ALLOWED_SURVEYS = [
        "manager_needs_assessment",
        "cpqi",
        "employees",
        "financials",
        "infrastructure",
        "kpis",
        "wet_mill_training",
        "waste_water_management",
        "water_and_energy_use",
    ]

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

        for survey_type in self.ALLOWED_SURVEYS:
            rows_for_sheet = await self.repo.list_survey_data_for_export(
                programme=programme,
                country=country,
                search=search,
                exporting_status=exporting_status,
                mill_status=mill_status,
                survey_type=survey_type,
            )
            sheet = wb.create_sheet(title=survey_type[:31])

            question_names = sorted({str(r.get("question_name") or "").strip() for r in rows_for_sheet if str(r.get("question_name") or "").strip()})
            headers = [
                "Wetmill Name",
                "Visit Date",
                "Submitted By",
                "Completed Date",
                "General Feedback",
                *question_names,
            ]
            sheet.append(headers)

            base_map: dict[tuple[str, str, str, str, str], dict] = {}
            for row in rows_for_sheet:
                visit_date = row.get("visit_date")
                completed_date = row.get("completed_date")
                visit_date_str = visit_date.isoformat() if visit_date else ""
                completed_date_str = completed_date.isoformat() if completed_date else ""
                key = (
                    str(row.get("wetmill_name") or ""),
                    visit_date_str,
                    str(row.get("submitted_by") or ""),
                    completed_date_str,
                    str(row.get("general_feedback") or ""),
                )
                if key not in base_map:
                    payload = {
                        "Wetmill Name": key[0],
                        "Visit Date": key[1],
                        "Submitted By": key[2],
                        "Completed Date": key[3],
                        "General Feedback": key[4],
                    }
                    for question in question_names:
                        payload[question] = ""
                    base_map[key] = payload

                question_name = str(row.get("question_name") or "").strip()
                if question_name:
                    question_value = row.get("value_text")
                    if question_value is None:
                        question_value = row.get("value_number")
                    if question_value is None:
                        question_value = row.get("value_boolean")
                    if question_value is None:
                        question_value = row.get("value_date")
                    if question_value is None:
                        question_value = row.get("value_gps")
                    base_map[key][question_name] = "" if question_value is None else str(question_value)

            for row_data in base_map.values():
                sheet.append([row_data.get(h, "") for h in headers])

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
