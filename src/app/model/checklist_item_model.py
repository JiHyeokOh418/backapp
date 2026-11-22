from datetime import timedelta, timezone
from sqlalchemy import BigInteger, String, Text, Integer, Boolean, Identity, UniqueConstraint, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.enum.common_enum import Instrument
from app.enum.checklist_enum import AnswerType

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.model.session_checklist_model import SessionChecklist

KST = timezone(timedelta(hours=9)) # UTC+9

# 체크리스트 목록
class ChecklistItem(Base):
    __tablename__ = "checklist_items"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    item_key: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    instruction: Mapped[str | None] = mapped_column(Text)
    answer_type: Mapped[AnswerType] = mapped_column(
        SQLEnum(AnswerType, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )
    options: Mapped[dict | list | None] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    instrument: Mapped[Instrument | None] = mapped_column(
        SQLEnum(Instrument, native_enum=False, values_callable=lambda e: [m.value for m in e])
    )
    item_no: Mapped[int | None] = mapped_column(Integer) # 척도 문항 번호

    __table_args__ = (
        UniqueConstraint("item_key", name="uq_checklist_items_item_key"),
    )

    # 관계
    # cascade: ChecklistItem이 삭제되면 참조된 테이블을 모두 같이 연쇄삭제
    session_checklists: Mapped[list["SessionChecklist"]] = relationship(
        "SessionChecklist", back_populates="item", cascade="all, delete-orphan"
    )
