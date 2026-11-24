from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, String, DateTime, Identity, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.enums.notification_enum import NotificationType

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.user_model import User
    from app.models.schedule_model import Schedule
    from app.models.risk_event_model import RiskEvent
    from app.models.care_request_model import CareRequest
    from app.models.appointment_model import Appointment

KST = timezone(timedelta(hours=9)) # UTC+9

class Notification(Base):
    __tablename__ = "notifications"

    notification_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)  # 알림 ID
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )  # 받는 회원 ID
    schedule_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("schedules.schedule_id", ondelete="SET NULL")
    )  # 관련 일정 ID
    risk_event_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("risk_events.id", ondelete="SET NULL")
    )  # 관련 위험 이벤트
    request_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("care_requests.request_id", ondelete="SET NULL")
    )  # 관련 진료 요청
    appointment_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("appointments.appointment_id", ondelete="SET NULL")
    )  # 관련 예약
    notification_type: Mapped[NotificationType] = mapped_column(
        SQLEnum(NotificationType, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )  # 알림 종류
    title: Mapped[str] = mapped_column(String(100), nullable=False)  # 제목
    content: Mapped[str | None] = mapped_column(String(255))  # 내용
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # 보낸 시각
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # 읽은 시각
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(KST)
    )  # 생성 시각

    # 관계
    user: Mapped["User"] = relationship("User", back_populates="notifications")
    schedule: Mapped["Schedule | None"] = relationship("Schedule", back_populates="notifications")
    risk_event: Mapped["RiskEvent | None"] = relationship("RiskEvent", back_populates="notifications")
    request: Mapped["CareRequest | None"] = relationship("CareRequest", back_populates="notifications")
    appointment: Mapped["Appointment | None"] = relationship("Appointment", back_populates="notifications")
