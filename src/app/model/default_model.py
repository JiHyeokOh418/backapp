from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, Text, Integer, DateTime, Identity, UniqueConstraint, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

KST = timezone(timedelta(hours=9)) # UTC+9

class Default(Base):
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    __tablename__ = "defaults"


