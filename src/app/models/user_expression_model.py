from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.user_model import User
    from app.models.expression_model import Expression

KST = timezone(timedelta(hours=9)) # UTC+9

class UserExpression(Base):
    __tablename__ = "user_expressions"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )  # 회원 ID
    expression_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("expressions.expression_id", ondelete="RESTRICT"), primary_key=True
    )  # 표정 ID
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(KST)
    )  # 처음 본 날
    seen_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)  # 본 횟수

    # 관계
    user: Mapped["User"] = relationship("User", back_populates="user_expressions")
    expression: Mapped["Expression"] = relationship("Expression")
