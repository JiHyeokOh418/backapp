from datetime import timedelta, timezone
from sqlalchemy import BigInteger, String, Text, Identity
from sqlalchemy.orm import Mapped, mapped_column, relationship

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.model.mood_collection_model import MoodCollection

KST = timezone(timedelta(hours=9)) # UTC+9

# 캐릭터_기본 (표정 마스터)
class Mood(Base):
    __tablename__ = "moods"

    mood_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    mood_description: Mapped[str | None] = mapped_column(Text)
    mood_img: Mapped[str | None] = mapped_column(String(255))

    # 관계
    # cascade: Mood가 삭제되면 참조된 테이블을 모두 같이 연쇄삭제
    collections: Mapped[list["MoodCollection"]] = relationship(
        "MoodCollection", back_populates="mood", cascade="all, delete-orphan"
    )
