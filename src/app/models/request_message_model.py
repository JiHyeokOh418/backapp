from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, String, DateTime, Identity, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.care_request_model import CareRequest
    from app.models.user_model import User

KST = timezone(timedelta(hours=9)) # UTC+9

class RequestMessage(Base):
    __tablename__ = "request_messages"

    message_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)  # 메시지 ID
    request_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("care_requests.request_id", ondelete="CASCADE"), nullable=False
    )  # 요청 ID
    sender_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )  # 보낸 회원 ID
    content: Mapped[str] = mapped_column(String(1000), nullable=False)  # 내용
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(KST)
    )  # 보낸 시각
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # 읽은 시각

    # 관계
    request: Mapped["CareRequest"] = relationship("CareRequest", back_populates="messages")
    sender: Mapped["User"] = relationship("User", back_populates="sent_request_messages")
