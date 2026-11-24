from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base

KST = timezone(timedelta(hours=9)) # UTC+9


# 사용자 설정 (마이페이지 > 설정). 행이 없으면 기본값으로 간주하고 처음 저장할 때 만든다.
class UserSetting(Base):
    __tablename__ = "user_settings"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    # 숫자·기록 현황 숨기기 (화면 토글)
    hide_stats: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 담당 의사에게 마음 기록 공유 (내 정보 > 공유 설정)
    share_with_doctor: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(KST),
        onupdate=lambda: datetime.now(KST)
    )
