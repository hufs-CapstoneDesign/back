import uuid
from sqlalchemy import Text, DateTime, Integer, Date, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, date
from app.database import Base


class RawArchive(Base):
    __tablename__ = "raw_archive"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sessions.id"))
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    speaker: Mapped[str] = mapped_column(Text)
    raw_text: Mapped[str] = mapped_column(Text)
    audio_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SlotResult(Base):
    __tablename__ = "slot_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sessions.id"))
    medication: Mapped[dict] = mapped_column(JSONB, default={})
    meal: Mapped[dict] = mapped_column(JSONB, default={})
    status: Mapped[dict] = mapped_column(JSONB, default={})
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DailyReport(Base):
    __tablename__ = "daily_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    report_date: Mapped[date] = mapped_column(Date)
    medication_summary: Mapped[dict] = mapped_column(JSONB, default={})
    meal_summary: Mapped[dict] = mapped_column(JSONB, default={})
    status_summary: Mapped[dict] = mapped_column(JSONB, default={})
    session_count: Mapped[int] = mapped_column(Integer, default=0)
    last_updated: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)