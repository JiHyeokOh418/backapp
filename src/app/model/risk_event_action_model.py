from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, String, DateTime, Identity, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.enum.risk_enum import ActorType, RiskAction

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.model.risk_event_model import RiskEvent

KST = timezone(timedelta(hours=9)) # UTC+9

# 위험 조치 이력
class RiskEventAction(Base):
    __tablename__ = "risk_event_actions"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    risk_event_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("risk_events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_type: Mapped[ActorType] = mapped_column(
        SQLEnum(ActorType, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )
    # FK 없음: actor_type이 ai/system이면 비어 있음
    actor_id: Mapped[int | None] = mapped_column(BigInteger)
    action: Mapped[RiskAction] = mapped_column(
        SQLEnum(RiskAction, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )
    memo: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(KST)
    )

    # 관계
    risk_event: Mapped["RiskEvent"] = relationship("RiskEvent", back_populates="actions")
