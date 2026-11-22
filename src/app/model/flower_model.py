from datetime import timedelta, timezone
from sqlalchemy import BigInteger, String, Text, Identity
from sqlalchemy.orm import Mapped, mapped_column, relationship

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.model.flower_collection_model import FlowerCollection

KST = timezone(timedelta(hours=9)) # UTC+9

# 꽃
class Flower(Base):
    __tablename__ = "flowers"

    flower_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    flower_description: Mapped[str | None] = mapped_column(Text)
    flower_img: Mapped[str | None] = mapped_column(String(255))

    # 관계
    # cascade: Flower가 삭제되면 참조된 테이블을 모두 같이 연쇄삭제
    collections: Mapped[list["FlowerCollection"]] = relationship(
        "FlowerCollection", back_populates="flower", cascade="all, delete-orphan"
    )
