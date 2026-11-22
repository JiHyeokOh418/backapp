import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, String, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.enum.notification_enum import NotificationType

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.model.user_model import User

KST = timezone(timedelta(hours=9)) # UTC+9

# 알림
class Notification(Base):
    __tablename__ = "notifications"

    notification_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    ) # ERD: CHAR(36) -> 참조 PK에 맞춰 BIGINT로 변경
    notification_type: Mapped[NotificationType] = mapped_column(
        SQLEnum(NotificationType, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    content: Mapped[str | None] = mapped_column(String(255))
    schedule_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("schedules.schedule_id", ondelete="SET NULL")
    ) # ERD: CHAR(36) -> 참조 PK에 맞춰 BIGINT로 변경
    risk_event_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("risk_events.id", ondelete="SET NULL")
    ) # ERD: CHAR(36) -> 참조 PK에 맞춰 BIGINT로 변경
    request_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("care_requests.request_id", ondelete="SET NULL")
    ) # ERD: CHAR(36) -> 참조 PK에 맞춰 BIGINT로 변경
    appointment_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("appointments.appointment_id", ondelete="SET NULL")
    ) # ERD: CHAR(36) -> 참조 PK에 맞춰 BIGINT로 변경
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(KST),
        index=True
    )

    # 관계
    user: Mapped["User"] = relationship("User", back_populates="notifications")
