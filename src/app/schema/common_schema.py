from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel # JS 카멜 <-> Python 스네이크 변환
from typing import Generic, TypeVar, List

T = TypeVar("T")


# 모든 요청/응답 DTO의 공통 부모
# - 프론트(JS)와는 camelCase로 주고받고, 파이썬 코드에서는 snake_case로 사용한다.
# - populate_by_name: snake_case 이름으로도 값을 넣을 수 있다.
# - from_attributes: ORM 객체 -> DTO 변환 (model_validate(orm_obj))
class BaseDTO(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


# 공통 응답 래퍼
class ApiResponseDTO(BaseDTO, Generic[T]):
    success: bool
    message: str
    data: T | None = None


# 페이지네이션 요청 (쿼리 파라미터: Depends()로 받는다)
class PageRequestDTO(BaseDTO):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)


# 페이지네이션 응답
class PageResponseDTO(BaseDTO, Generic[T]):
    total_count: int
    total_pages: int
    offset: int
    limit: int
    items: List[T] | None = None
