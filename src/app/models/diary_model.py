from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, Text, DateTime, Identity, ForeignKey, Index, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.user_model import User
    from app.models.diary_analysis_model import DiaryAnalysis

KST = timezone(timedelta(hours=9)) # UTC+9

class Diary(Base):
    __tablename__ = "diaries"

    diary_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)  # 일기 ID
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )  # 작성자 ID
    diary_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)  # 일기 날짜 (지난 날짜는 최근 7일까지)
    content: Mapped[str] = mapped_column(Text, nullable=False)  # 본문
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(KST)
    )  # 작성 시각
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        onupdate=lambda: datetime.now(KST)
    )  # 수정 시각
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # 삭제 시각

    __table_args__ = (
        # 지운 날 다시 쓰기 허용: 삭제되지 않은 줄에만 (user_id, diary_date) UNIQUE
        Index(
            "uix_diaries_user_date_alive", "user_id", "diary_date",
            unique=True, postgresql_where=text("deleted_at IS NULL")
        ),
    )

    # 관계
    # cascade: Diary가 삭제되면 참조된 테이블을 모두 같이 연쇄삭제
    user: Mapped["User"] = relationship("User", back_populates="diaries")
    analyses: Mapped[list["DiaryAnalysis"]] = relationship(
        "DiaryAnalysis", back_populates="diary",
        cascade="all, delete-orphan", passive_deletes=True
    )
