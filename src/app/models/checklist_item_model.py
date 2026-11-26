from sqlalchemy import BigInteger, String, Text, Integer, Boolean, Identity, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.enums.checklist_item_enum import ChecklistItemAnswerType
from app.enums.common_enum import Instrument

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base

class ChecklistItem(Base):
    __tablename__ = "checklist_items"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)  # PK
    item_key: Mapped[str] = mapped_column(String(64), nullable=False)  # 불변 식별자. 예: sleep_hours
    label: Mapped[str] = mapped_column(String(100), nullable=False)  # 화면·의사용 이름
    instruction: Mapped[str] = mapped_column(Text, nullable=False)  # LLM 질문 지침
    answer_type: Mapped[ChecklistItemAnswerType] = mapped_column(
        SQLEnum(ChecklistItemAnswerType, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )  # 답 형태
    # 응답 범위 (answer_type별 형식, llm_service._check_value가 이 형식으로 검증한다)
    # - boolean: null / number: {"min": 1, "max": 30} / scale: {"min": 0, "max": 9}
    # - choice: {"label": ["a", "b", "c"]} / text: null (도메인 검증 없음)
    options: Mapped[dict | None] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)  # 사용 여부
    instrument: Mapped[Instrument | None] = mapped_column(
        SQLEnum(Instrument, native_enum=False, values_callable=lambda e: [m.value for m in e])
    )  # 척도 문항일 때만. 보기별 점수는 options에
    item_no: Mapped[int | None] = mapped_column(Integer)  # 척도 문항 번호

    # 관계
    # 기준 데이터 테이블이라 역방향 relationship은 두지 않는다.
