from fastapi import Depends
from app.repository.calendar_repository import CalendarRepository, get_calendar_repository


# 캘린더 비즈니스 로직, 예외 처리, 트랜잭션 관리
class CalendarService:

    def __init__(self, repo: CalendarRepository):
        self.repo = repo

    # TODO: 서비스 메서드 추가


def get_calendar_service(repo: CalendarRepository = Depends(get_calendar_repository)) -> CalendarService:
    return CalendarService(repo)
