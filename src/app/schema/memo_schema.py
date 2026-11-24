from datetime import datetime, timedelta, timezone
from pydantic import Field, field_validator, field_serializer
from app.enums.doctor_memo_enum import DoctorMemoCategory
from app.schema.common_schema import BaseDTO

KST = timezone(timedelta(hours=9)) # UTC+9


# 메모 작성 요청
class MemoCreateDTO(BaseDTO):
    category: DoctorMemoCategory
    content: str = Field(max_length=1000)
    is_pinned: bool = False

    # 앞뒤 공백 제거, 빈 내용은 거절
    @field_validator("content")
    @classmethod
    def strip_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("메모 내용을 입력하세요.")
        return value


# 메모 수정·고정 요청 (보낸 값만 수정: model_dump(exclude_unset=True))
# - 고정만 바꿀 때는 {"isPinned": true} 만 보내면 된다.
class MemoUpdateDTO(BaseDTO):
    category: DoctorMemoCategory | None = None
    content: str | None = Field(default=None, max_length=1000)
    is_pinned: bool | None = None

    @field_validator("content")
    @classmethod
    def strip_content(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("메모 내용을 입력하세요.")
        return value


# 메모 1건 응답
class MemoResponseDTO(BaseDTO):
    id: int
    patient_id: int
    doctor_id: int
    doctor_name: str | None = None  # 작성자 이름 (예: 이은솔)
    category: DoctorMemoCategory
    content: str
    is_pinned: bool
    is_edited: bool                 # 내용을 고친 적이 있으면 true -> "수정됨" 표시
    created_at: datetime
    updated_at: datetime

    # 시각은 KST(+09:00)로 내려준다
    @field_serializer("created_at", "updated_at")
    def to_kst(self, value: datetime) -> datetime:
        return value.astimezone(KST)


# 메모 팝업 헤더용 환자 정보
class MemoPatientResponseDTO(BaseDTO):
    id: int
    name: str | None = None


# 메모 목록 응답
# - 헤더 "김민준 환자 · 3건 · 고정 1", 탭 "전체 3 / 고정 1"
# - total_count, pinned_count는 pinned 필터와 상관없이 항상 전체 기준
class MemoListResponseDTO(BaseDTO):
    patient: MemoPatientResponseDTO
    total_count: int
    pinned_count: int
    items: list[MemoResponseDTO]
