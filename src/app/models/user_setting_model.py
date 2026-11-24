from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.user_model import User

KST = timezone(timedelta(hours=9)) # UTC+9

class UserSetting(Base):
    __tablename__ = "user_settings"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )  # 회원 1명당 1줄, 가입 시 기본값으로 생성
    share_report: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)  # 리포트 공개 (기록별은 emotion_records.is_shared)
    share_diary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # 일기 의사 공개
    diary_ai_consent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # 동의한 경우에만 일기 분석
    hide_stats: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # 통계 숨기기
    consent_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # 동의 변경 시각
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        onupdate=lambda: datetime.now(KST)
    )  # 수정 시각

    # 관계
    user: Mapped["User"] = relationship("User", back_populates="setting")
