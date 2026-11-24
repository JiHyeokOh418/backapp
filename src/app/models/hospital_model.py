from datetime import datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy import BigInteger, String, Numeric, Boolean, DateTime, Identity
from sqlalchemy.orm import Mapped, mapped_column

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base

KST = timezone(timedelta(hours=9)) # UTC+9

class Hospital(Base):
    __tablename__ = "hospitals"

    hospital_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)  # 병원 ID
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # 병원 이름
    phone: Mapped[str | None] = mapped_column(String(20))  # 전화번호
    address: Mapped[str] = mapped_column(String(255), nullable=False)  # 주소
    sido: Mapped[str] = mapped_column(String(20), nullable=False)  # 시·도
    sigungu: Mapped[str] = mapped_column(String(30), nullable=False)  # 시·군·구
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))  # 위도
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))  # 경도
    is_accepting: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)  # 요청 받기 여부
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(KST)
    )  # 등록 시각
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        onupdate=lambda: datetime.now(KST)
    )  # 수정 시각

    # 관계
    # 기준 데이터 테이블이라 역방향 relationship은 두지 않는다.
