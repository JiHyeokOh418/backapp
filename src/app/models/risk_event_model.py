from datetime import datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy import BigInteger, String, Text, Numeric, Boolean, DateTime, Identity, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.enums.risk_event_enum import RiskEventLevel, RiskEventSource, RiskEventStatus, RiskEventOrigin

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.message_model import Message
    from app.models.user_model import User
    from app.models.risk_event_action_model import RiskEventAction
    from app.models.notification_model import Notification

KST = timezone(timedelta(hours=9)) # UTC+9

class RiskEvent(Base):
    __tablename__ = "risk_events"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)  # PK
    message_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("messages.id", ondelete="SET NULL")
    )  # 발생 메시지
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )  # 환자
    reviewed_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )  # 확인한 의사
    level: Mapped[RiskEventLevel] = mapped_column(
        SQLEnum(RiskEventLevel, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )  # 위험 단계
    source: Mapped[RiskEventSource] = mapped_column(
        SQLEnum(RiskEventSource, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )  # 감지 주체: classifier=KcELECTRA, guard=게이트 A, rule=규칙
    evidence: Mapped[str | None] = mapped_column(Text)  # 근거 문장
    status: Mapped[RiskEventStatus] = mapped_column(
        SQLEnum(RiskEventStatus, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=RiskEventStatus.OPEN
    )  # 처리 상태
    origin: Mapped[RiskEventOrigin] = mapped_column(
        SQLEnum(RiskEventOrigin, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=RiskEventOrigin.CHAT
    )  # 출처: chat=AI 상담, assessment=자가검사 급상승, trend·inactive=F5
    origin_id: Mapped[int | None] = mapped_column(BigInteger)  # chat 외 출처의 행 ID (여러 테이블이라 FK 없음)
    category: Mapped[str | None] = mapped_column(String(50))  # 예: 무망감·소진
    score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))  # 모델 신뢰도
    model_version: Mapped[str | None] = mapped_column(String(50))  # 모델·규칙 버전
    matched_terms: Mapped[dict | None] = mapped_column(JSONB)  # 감지 표현
    context_judgement: Mapped[str | None] = mapped_column(Text)  # 문맥 판단
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # 확인 시각
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(KST)
    )  # 감지 시각
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # medium이면 감지 시각 + 24시간
    is_repeated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # 최근 30일 같은 category 3번째 이상
    is_uncertain: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # 모델 점수 0.4~0.6

    # 관계
    # cascade: RiskEvent가 삭제되면 참조된 테이블을 모두 같이 연쇄삭제
    message: Mapped["Message | None"] = relationship("Message", back_populates="risk_events")
    patient: Mapped["User"] = relationship(
        "User", back_populates="patient_risk_events", foreign_keys=[user_id]
    )
    reviewer: Mapped["User | None"] = relationship(
        "User", back_populates="reviewed_risk_events", foreign_keys=[reviewed_by]
    )
    actions: Mapped[list["RiskEventAction"]] = relationship(
        "RiskEventAction", back_populates="risk_event",
        cascade="all, delete-orphan", passive_deletes=True
    )
    notifications: Mapped[list["Notification"]] = relationship(
        "Notification", back_populates="risk_event"
    )
