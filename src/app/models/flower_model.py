from sqlalchemy import BigInteger, String, Text, Integer, Identity, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column
from app.enums.common_enum import Season

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base

class Flower(Base):
    __tablename__ = "flowers"

    flower_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)  # 꽃 ID
    flower_language: Mapped[str | None] = mapped_column(Text)  # 꽃말
    image_url: Mapped[str | None] = mapped_column(String(255))  # 이미지 주소
    flower_no: Mapped[int] = mapped_column(Integer, nullable=False)  # 도감 번호
    name: Mapped[str] = mapped_column(String(50), nullable=False)  # 꽃 이름
    season: Mapped[Season] = mapped_column(
        SQLEnum(Season, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )  # 계절 (다음 꽃은 오늘 계절 꽃 중에서 고름)

    # 관계
    # 기준 데이터 테이블이라 역방향 relationship은 두지 않는다.
