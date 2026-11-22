from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, String, Integer, DateTime, Identity, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.enum.common_enum import Instrument
from app.enum.checklist_enum import AssessmentSource

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.model.user_model import User

KST = timezone(timedelta(hours=9)) # UTC+9

# 척도 결과
class AssessmentResult(Base):
    __tablename__ = "assessment_results"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("chat_sessions.id", ondelete="SET NULL"), index=True
    )
    instrument: Mapped[Instrument] = mapped_column(
        SQLEnum(Instrument, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )
    total_score: Mapped[int] = mapped_column(Integer, nullable=False)
    severity: Mapped[str | None] = mapped_column(String(20))
    source: Mapped[AssessmentSource] = mapped_column(
        SQLEnum(AssessmentSource, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )
    assessed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(KST),
        index=True
    )

    # 관계
    user: Mapped["User"] = relationship("User", back_populates="assessment_results")
