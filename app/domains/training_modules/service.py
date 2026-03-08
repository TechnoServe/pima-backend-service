from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.rbac import is_admin
from app.core.pagination import compute_pages
from app.shared.api_errors import ConflictError, NotFoundError, ValidationError

from .repository import TrainingModulesRepository
from .schemas import CreateTrainingModuleRequest


_ALLOWED_CURRENT_PREVIOUS = {"Current", "Previous"}


class TrainingModulesService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = TrainingModulesRepository(db)

    @staticmethod
    def _normalize_current_previous(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if normalized == "":
            return None
        if normalized not in _ALLOWED_CURRENT_PREVIOUS:
            raise ValidationError(
                "Invalid current_previous value",
                details={"allowed": ["Current", "Previous", ""]},
            )
        return normalized

    async def list_training_modules(
        self,
        *,
        project_id: UUID,
        page: int,
        page_size: int,
        search: str | None,
        status: str | None,
        current_previous: str | None,
        current_module: bool | None,
    ) -> dict:
        normalized_current_previous = self._normalize_current_previous(current_previous)

        rows, total = await self.repo.list_training_modules(
            project_id=project_id,
            page=page,
            page_size=page_size,
            search=search,
            status=status,
            current_previous=normalized_current_previous,
            current_module=current_module,
        )
        items = [self._module_response_item(r) for r in rows]
        return {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": compute_pages(total, page_size),
        }

    async def get_training_module_details(self, *, module_id: UUID, project_id: UUID | None, current_user: dict) -> dict:
        module_row = await self.repo.get_module_details(module_id)
        if not module_row:
            raise NotFoundError("Training module not found")

        if project_id and module_row.get("project_id") != project_id:
            raise ValidationError("Training module does not belong to the provided project")

        if not is_admin(current_user.get("user_role")) and not project_id:
            raise ValidationError("project_id is required for non-admin users")

        sessions = await self.repo.get_module_sessions(module_id)
        return {
            "module": self._module_response_item(module_row),
            "sessions": [self._session_response_item(r) for r in sessions],
        }

    async def create_training_module(self, *, payload: CreateTrainingModuleRequest, current_user: dict) -> dict:
        project = await self.repo.get_project(payload.project_id)
        if not project:
            raise NotFoundError("Project not found")

        existing = await self.repo.get_module_by_project_and_number(payload.project_id, payload.module_number)
        if existing:
            raise ConflictError("Training module already exists for this project and module number")

        normalized_current_previous = self._normalize_current_previous(payload.current_previous)

        async with self.db.begin():
            user_id = UUID(str(current_user["id"]))
            if normalized_current_previous == "Current":
                await self.repo.normalize_project_current_previous_for_current(
                    project_id=payload.project_id,
                    current_user_id=user_id,
                )

            payload_data = payload.model_dump()
            payload_data["current_previous"] = normalized_current_previous
            module_data = self.repo.build_module_create_data(payload_data, user_id)
            created_module = await self.repo.create_module(module_data)

            groups = await self.repo.list_project_farmer_groups(payload.project_id)
            group_ids = [g["id"] for g in groups]
            existing_group_ids = await self.repo.existing_session_farmer_group_ids(created_module["id"], group_ids)

            sessions_payload = []
            for group in groups:
                if group["id"] in existing_group_ids:
                    continue
                sessions_payload.append(
                    self.repo.build_training_session_create_data(
                        module_id=created_module["id"],
                        farmer_group_id=group["id"],
                        trainer_id=group.get("responsible_staff_id"),
                        current_user_id=user_id,
                    )
                )

            created_sessions_count = await self.repo.create_training_sessions_for_module(
                module_id=created_module["id"],
                sessions_payload=sessions_payload,
            )

        return {
            "module": self._module_response_item(created_module),
            "created_sessions_count": created_sessions_count,
            "message": "Training module created successfully.",
        }

    async def change_current_previous(self, *, module_id: UUID, current_previous: str | None, current_user: dict) -> dict:
        normalized_current_previous = self._normalize_current_previous(current_previous)

        module = await self.repo.get_module_by_id(module_id)
        if not module:
            raise NotFoundError("Training module not found")

        async with self.db.begin():
            user_id = UUID(str(current_user["id"]))
            if normalized_current_previous == "Current":
                await self.repo.normalize_project_current_previous_for_current(
                    project_id=module["project_id"],
                    current_user_id=user_id,
                    exclude_module_id=module_id,
                )

            await self.repo.update_module_current_previous(
                module_id,
                normalized_current_previous,
                user_id,
            )

        return {
            "success": True,
            "module_id": module_id,
            "current_previous": normalized_current_previous,
            "message": "Training module current_previous updated successfully.",
        }

    async def send_training_sessions_to_commcare(self, *, module_id: UUID, current_user: dict) -> dict:
        module = await self.repo.get_module_by_id(module_id)
        if not module:
            raise NotFoundError("Training module not found")

        project_id = module.get("project_id")
        if not project_id:
            raise ValidationError("Training module is missing project_id")

        async with self.db.begin():
            affected_sessions = await self.repo.mark_module_sessions_for_commcare(
                module_id=module_id,
                current_user_id=UUID(str(current_user["id"])),
            )
            affected_project_roles = await self.repo.mark_project_roles_for_commcare(
                project_id=project_id,
                current_user_id=UUID(str(current_user["id"])),
            )

        return {
            "success": True,
            "module_id": module_id,
            "project_id": project_id,
            "affected_sessions": affected_sessions,
            "affected_project_roles": affected_project_roles,
            "message": "Training sessions and project roles marked for CommCare sync.",
        }

    @staticmethod
    def _module_response_item(row: dict) -> dict:
        return {
            "id": row.get("id"),
            "project_id": row.get("project_id"),
            "module_name": row.get("module_name"),
            "module_number": row.get("module_number"),
            "current_module": row.get("current_module"),
            "sample_fv_aa_households": row.get("sample_fv_aa_households"),
            "sample_fv_aa_households_status": row.get("sample_fv_aa_households_status"),
            "status": row.get("status"),
            "current_previous": row.get("current_previous"),
            "module_date": row.get("module_date"),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
            "sessions_count": row.get("sessions_count"),
        }

    @staticmethod
    def _session_response_item(row: dict) -> dict:
        return {
            "id": row.get("id"),
            "module_id": row.get("module_id"),
            "farmer_group_id": row.get("farmer_group_id"),
            "farmer_group_name": row.get("farmer_group_name"),
            "trainer_id": row.get("trainer_id"),
            "trainer_name": row.get("trainer_name"),
            "commcare_case_id": row.get("commcare_case_id"),
            "date_session_1": row.get("date_session_1"),
            "date_session_2": row.get("date_session_2"),
            "male_attendees_session_1": row.get("male_attendees_session_1"),
            "female_attendees_session_1": row.get("female_attendees_session_1"),
            "total_attendees_session_1": row.get("total_attendees_session_1"),
            "male_attendees_session_2": row.get("male_attendees_session_2"),
            "female_attendees_session_2": row.get("female_attendees_session_2"),
            "total_attendees_session_2": row.get("total_attendees_session_2"),
            "male_attendees_agg": row.get("male_attendees_agg"),
            "female_attendees_agg": row.get("female_attendees_agg"),
            "total_attendees_agg": row.get("total_attendees_agg"),
            "send_to_commcare": row.get("send_to_commcare"),
            "send_to_commcare_status": row.get("send_to_commcare_status"),
            "sampled": row.get("sampled"),
            "review_status": row.get("review_status"),
        }
