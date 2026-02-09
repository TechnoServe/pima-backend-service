from __future__ import annotations

from sqlalchemy import Table
from app.db.reflection import get_table

TABLE_NAME = "farmers"

def table() -> Table:
    return get_table(TABLE_NAME)

import uuid
from datetime import datetime
from sqlalchemy import (
    Column,
    String,
    DateTime,
    Boolean,
    Integer,
    Text,
    ForeignKey,
    Enum,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.db.base import Base

UploadStatusEnum = Enum(
    "uploading",
    "validating",
    "processing",
    "validation_errored",
    "completed",
    "failed",
    "cancelled",
    name="upload_status_enum",
    create_type=False,
)

DB_SCHEMA = "pima"  # ✅ hardcode to what your screenshot shows

class UploadRun(Base):
    __tablename__ = "upload_runs"                 # ✅ changed
    __table_args__ = {"schema": DB_SCHEMA}        # ✅ added

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    filename = Column(String, nullable=False)
    content_type = Column(String, nullable=True)
    file_size_bytes = Column(Integer, nullable=True)

    gcs_bucket = Column(String, nullable=True)
    gcs_object_name = Column(String, nullable=True)
    gcs_uri = Column(String, nullable=True)

    error_gcs_object_name = Column(String, nullable=True)
    error_gcs_uri = Column(String, nullable=True)

    status = Column(String, nullable=False, default="uploading")
    progress = Column(Integer, nullable=False, default=0)

    total_rows = Column(Integer, nullable=False, default=0)
    success_count = Column(Integer, nullable=False, default=0)
    failed_count = Column(Integer, nullable=False, default=0)
    remaining_count = Column(Integer, nullable=False, default=0)

    uploaded_by_id = Column(UUID(as_uuid=True),nullable=True)
    uploaded_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    parent_upload_id = Column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.upload_runs.id"),  # ✅ schema-prefixed
        nullable=True
    )

    meta = Column(JSONB, nullable=True)

    errors = relationship("UploadRowError", back_populates="upload_run", cascade="all, delete-orphan")


class UploadRowError(Base):
    __tablename__ = "upload_row_errors"           # ✅ changed
    __table_args__ = {"schema": DB_SCHEMA}        # ✅ added

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    upload_run_id = Column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.upload_runs.id"),  # ✅ schema-prefixed
        nullable=False,
        index=True
    )

    row_number = Column(Integer, nullable=False)
    farmer_id = Column(UUID(as_uuid=True), nullable=True)
    tns_id = Column(String, nullable=True)

    error_type = Column(String, nullable=False)
    error_message = Column(Text, nullable=False)

    raw_row = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    upload_run = relationship("UploadRun", back_populates="errors")


Index("ix_upload_runs_project_status", UploadRun.project_id, UploadRun.status)
Index("ix_upload_row_errors_run_row", UploadRowError.upload_run_id, UploadRowError.row_number)