from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, String, DateTime, Identity, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.model.care_request_model import CareRequest
    from app.model.user_model import User

KST = timezone(timedelta(hours=9)) # UTC+9

# 예약채팅
class RequestMessage(Base):
    __tablename__ = "request_messages"

    message_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    request_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("care_requests.request_id", ondelete="CASCADE"), nullable=False, index=True
    )
    sender_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content: Mapped[str] = mapped_column(String(1000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(KST)
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # 관계
    request: Mapped["CareRequest"] = relationship("CareRequest", back_populates="messages")
    sender: Mapped["User"] = relationship("User", back_populates="request_messages")
