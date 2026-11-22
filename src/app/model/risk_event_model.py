from datetime import datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy import BigInteger, String, Text, Numeric, DateTime, Identity, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.enum.risk_enum import RiskLevel, RiskSource, RiskStatus, RiskOrigin

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.model.user_model import User
    from app.model.risk_event_action_model import RiskEventAction

KST = timezone(timedelta(hours=9)) # UTC+9

# 위험분석
class RiskEvent(Base):
    __tablename__ = "risk_events"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    message_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("messages.id", ondelete="SET NULL"), index=True
    )
    level: Mapped[RiskLevel] = mapped_column(
        SQLEnum(RiskLevel, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )
    source: Mapped[RiskSource] = mapped_column(
        SQLEnum(RiskSource, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )
    evidence: Mapped[str | None] = mapped_column(Text)
    status: Mapped[RiskStatus] = mapped_column(
        SQLEnum(RiskStatus, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=RiskStatus.OPEN
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    origin: Mapped[RiskOrigin] = mapped_column(
        SQLEnum(RiskOrigin, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )
    # FK 없음: origin에 따라 다른 테이블을 가리키므로 ERD대로 String(36) 유지
    origin_id: Mapped[str | None] = mapped_column(String(36)) # 출처 행 ID
    category: Mapped[str | None] = mapped_column(String(50))
    score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    model_version: Mapped[str | None] = mapped_column(String(50))
    matched_terms: Mapped[dict | list | None] = mapped_column(JSONB)
    context_judgement: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(KST),
        index=True
    )

    # 관계 (users를 2번 참조하므로 foreign_keys 지정)
    # cascade: RiskEvent가 삭제되면 참조된 테이블을 모두 같이 연쇄삭제
    user: Mapped["User"] = relationship("User", back_populates="risk_events", foreign_keys=[user_id])
    actions: Mapped[list["RiskEventAction"]] = relationship(
        "RiskEventAction", back_populates="risk_event", cascade="all, delete-orphan"
    )
