import uuid
from sqlalchemy import String, DateTime
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(50))
    role: Mapped[str] = mapped_column(String(20))  # "patient" | "guardian"
    guardian_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    profile: Mapped[dict] = mapped_column(JSONB, default={})
    # profile 예시: {"medications": ["혈압약"], "family": ["딸 민지"], "conditions": ["고혈압"]}
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)