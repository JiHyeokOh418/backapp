from sqlalchemy import BigInteger, String, Identity, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column
from app.enums.expression_enum import ExpressionCategory

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base

class Expression(Base):
    __tablename__ = "expressions"

    expression_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)  # 표정 ID
    condition_text: Mapped[str | None] = mapped_column(String(255))  # 나오는 조건
    image_url: Mapped[str | None] = mapped_column(String(255))  # 이미지 주소
    name: Mapped[str] = mapped_column(String(30), nullable=False)  # 표정 이름
    category: Mapped[ExpressionCategory] = mapped_column(
        SQLEnum(ExpressionCategory, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )  # mood=오늘의 기분 후보, care=돌볼 때, season=계절

    # 관계
    # 기준 데이터 테이블이라 역방향 relationship은 두지 않는다.
