from datetime import date, datetime
from pydantic import Field
from app.schema.common_schema import BaseDTO

# 마음 일기 요청/응답 DTO
# 규칙: BaseDTO 상속, XxxCreateDTO / XxxUpdateDTO / XxxResponseDTO 이름 사용


# 일기 작성 요청
class DiaryCreateDTO(BaseDTO):
    # 일기 날짜 (보내지 않으면 오늘, 한국 시간 기준)
    diary_date: date | None = None
    content: str = Field(min_length=1, max_length=5000)


# 일기 수정 요청 (보낸 값만 수정)
class DiaryUpdateDTO(BaseDTO):
    diary_date: date | None = None
    content: str | None = Field(default=None, min_length=1, max_length=5000)


# 일기 응답 (AI 분석 결과는 환자에게 노출하지 않는다.)
class DiaryResponseDTO(BaseDTO):
    diary_id: int
    diary_date: date
    content: str
    created_at: datetime
    updated_at: datetime
