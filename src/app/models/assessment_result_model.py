from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, String, Integer, DateTime, Identity, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.enums.common_enum import Instrument
from app.enums.assessment_result_enum import AssessmentResultSource

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.user_model import User
    from app.models.chat_session_model import ChatSession

KST = timezone(timedelta(hours=9)) # UTC+9

class AssessmentResult(Base):
    __tablename__ = "assessment_results"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)  # PK
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )  # 환자
    session_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("chat_sessions.id", ondelete="SET NULL")
    )  # 문진 세션
    instrument: Mapped[Instrument] = mapped_column(
        SQLEnum(Instrument, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )  # 척도
    total_score: Mapped[int] = mapped_column(Integer, nullable=False)  # 총점
    severity: Mapped[str] = mapped_column(String(20), nullable=False)  # 예: 중등도
    source: Mapped[AssessmentResultSource] = mapped_column(
        SQLEnum(AssessmentResultSource, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )  # 측정 방식
    assessed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(KST)
    )  # 측정 시각

    # 관계
    user: Mapped["User"] = relationship("User", back_populates="assessment_results")
    session: Mapped["ChatSession | None"] = relationship("ChatSession", back_populates="assessment_results")
