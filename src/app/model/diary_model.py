from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, Text, DateTime, Identity, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.model.user_model import User
    from app.model.diary_analysis_model import DiaryAnalysis

KST = timezone(timedelta(hours=9)) # UTC+9

# 일기
class Diary(Base):
    __tablename__ = "diaries"

    diary_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    diary_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(KST)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(KST),
        onupdate=lambda: datetime.now(KST)
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # 관계
    # cascade: Diary가 삭제되면 참조된 테이블을 모두 같이 연쇄삭제
    user: Mapped["User"] = relationship("User", back_populates="diaries")
    analysis: Mapped["DiaryAnalysis | None"] = relationship(
        "DiaryAnalysis", back_populates="diary", uselist=False, cascade="all, delete-orphan"
    )
