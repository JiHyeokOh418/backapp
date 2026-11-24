from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, String, DateTime, Identity, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.enums.risk_event_action_enum import RiskEventActionActorType, RiskEventActionAction

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.risk_event_model import RiskEvent
    from app.models.user_model import User

KST = timezone(timedelta(hours=9)) # UTC+9

class RiskEventAction(Base):
    __tablename__ = "risk_event_actions"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)  # PK
    risk_event_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("risk_events.id", ondelete="CASCADE"), nullable=False
    )  # 위험 이벤트
    actor_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )  # doctor일 때만
    actor_type: Mapped[RiskEventActionActorType] = mapped_column(
        SQLEnum(RiskEventActionActorType, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )  # 행위자 종류
    action: Mapped[RiskEventActionAction] = mapped_column(
        SQLEnum(RiskEventActionAction, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )  # 조치
    memo: Mapped[str | None] = mapped_column(String(500))  # 조치 메모
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(KST)
    )  # 기록 시각 (append-only)

    # 관계
    risk_event: Mapped["RiskEvent"] = relationship("RiskEvent", back_populates="actions")
    actor: Mapped["User | None"] = relationship("User", back_populates="risk_event_actions")
