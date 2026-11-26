from datetime import datetime
from app.schema.common_schema import BaseDTO
from app.enums.point_history_enum import PointHistoryType

#포인트 요청/응답 DTO
#규칙: BaseDTO 상속, XxxCreateDTO/XxxUpdateDTO/XxxResponseDTO 이름 사용

#내 포인트 요약(포인트샵&마이룸 잔액, 포인트 기록 상단'이번 달 +320p')
class PointSummaryResponseDTO(BaseDTO):
    point_balance: int  #지금 잔액
    earned_today: int   #오늘 모은 포인트(얻음 - 취소)
    earned_this_month: int  #이번 달 모은 포인트(얻음 - 취소)

#포인트 내역 1줄 (포인트 기록 화면)
class PointHistoryResponseDTO(BaseDTO):
    history_id: int
    history_type: PointHistoryType  #earn, spend, cancel
    amount: int #얻음은 +, 씀 & 취소는 -로 보낸다
    balance_after: int  #처리 후 잔액
    reason: str |None=None  #'산책 10분'. '붕어빵 2개 구매'
    mission_id: int |None=None  
    item_id: int |None=None 
    created_at: datetime

#포인트 내역 목록(최신순, 더보기)
class PointHistoryListResponseDTO(BaseDTO):
    items: list[PointHistoryResponseDTO] 
    next_cursor: int | None = None  # 다음 요청에 넣을 값, 없으면 마지막 페이지

