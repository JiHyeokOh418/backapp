from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, String, DateTime, Identity
from sqlalchemy.orm import Mapped, mapped_column

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base

KST = timezone(timedelta(hours=9)) # UTC+9

class RagDocument(Base):
    __tablename__ = "rag_documents"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)  # PK
    title: Mapped[str] = mapped_column(String(200), nullable=False)  # 문서 제목
    source: Mapped[str | None] = mapped_column(String(500))  # 출처
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(KST)
    )  # 등록 시각

    # 관계
    # 기준 데이터 테이블이라 역방향 relationship은 두지 않는다.
