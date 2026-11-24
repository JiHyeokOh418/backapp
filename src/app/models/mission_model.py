from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, String, Integer, SmallInteger, Boolean, DateTime, Identity, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column
from app.enums.mission_enum import MissionType, MissionCategory

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base

KST = timezone(timedelta(hours=9)) # UTC+9

class Mission(Base):
    __tablename__ = "missions"

    mission_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)  # 미션 ID
    name: Mapped[str] = mapped_column(String(50), nullable=False)  # 미션 이름
    mission_type: Mapped[MissionType] = mapped_column(
        SQLEnum(MissionType, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )  # 미션 종류
    reward_point: Mapped[int] = mapped_column(Integer, nullable=False)  # 보상 포인트
    daily_limit: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)  # 하루 최대 횟수
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)  # 사용 여부
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 표시 순서
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(KST)
    )  # 등록 시각
    description: Mapped[str | None] = mapped_column(String(255))  # 설명
    target_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)  # 목표 횟수
    category: Mapped[MissionCategory | None] = mapped_column(
        SQLEnum(MissionCategory, native_enum=False, values_callable=lambda e: [m.value for m in e])
    )  # body=몸, habit=습관, mind=마음. 분류 없는 미션은 NULL

    # 관계
    # 기준 데이터 테이블이라 역방향 relationship은 두지 않는다.
