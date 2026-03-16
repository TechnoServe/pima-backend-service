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

        return PaginatedWetmillsResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )

    async def filter_options(self, *, programme: str, country: str | None) -> WetmillsFilterOptionsResponse:
        return WetmillsFilterOptionsResponse(
            **(await self.repo.filter_options(programme=programme, country=country))
        )

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

    @staticmethod
    def _question_value(question: dict):
        if question.get("value_text") is not None:
            return question["value_text"]
        if question.get("value_number") is not None:
            return question["value_number"]
        if question.get("value_boolean") is not None:
            return question["value_boolean"]
        if question.get("value_date") is not None:
            value = question["value_date"]
            return value.isoformat() if hasattr(value, "isoformat") else str(value)
        if question.get("value_gps") is not None:
            return question["value_gps"]
        return ""

    async def export_excel(
        self,
        *,
        programme: str,
        country: str | None,
        search: str | None,
        exporting_status: str | None,
        mill_status: str | None,
    ) -> bytes:
        wb = Workbook()
        wb.remove(wb.active)

        main_rows, has_ownership = await self.repo.list_for_export(
            programme=programme,
            country=country,
            search=search,
            exporting_status=exporting_status,
            mill_status=mill_status,
        )

        main_sheet = wb.create_sheet(title="Wetmills")
        main_sheet.append(self._export_headers())
        for row in main_rows:
            main_sheet.append(self._export_row(dict(row), has_ownership))

        for survey_type in self.ALLOWED_SURVEYS:
            responses = await self.repo.list_survey_export_payload(
                programme=programme,
                country=country,
                search=search,
                exporting_status=exporting_status,
                mill_status=mill_status,
                survey_type=survey_type,
            )

            question_names: list[str] = []
            for response in responses:
                for question in response["question_responses"]:
                    question_name = (question.get("question_name") or "").strip()
                    if question_name and question_name not in question_names:
                        question_names.append(question_name)

            sheet = wb.create_sheet(title=survey_type[:31])
            headers = [
                "Wetmill Name",
                "Visit Date",
                "Submitted By",
                "Completed Date",
                "General Feedback",
                *question_names,
            ]
            sheet.append(headers)

            for response in responses:
                row_data = {
                    "Wetmill Name": response.get("wetmill_name") or "",
                    "Visit Date": response.get("visit_date").isoformat() if response.get("visit_date") else "",
                    "Submitted By": str(response.get("first_name")) + " " + str(response.get("last_name")),
                    "Completed Date": response.get("completed_date").isoformat() if response.get("completed_date") else "",
                    "General Feedback": response.get("general_feedback") or "",
                }

                for question in response["question_responses"]:
                    question_name = (question.get("question_name") or "").strip()
                    if question_name:
                        row_data[question_name] = self._question_value(question)

                sheet.append([row_data.get(header, "") for header in headers])

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