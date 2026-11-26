from fastapi import Depends
from app.repository.mood_record_repository import MoodRecordRepository, get_mood_record_repository


# 마음 기록 (마음 날씨/키워드/한 줄) 비즈니스 로직, 예외 처리, 트랜잭션 관리
class MoodRecordService:

    def __init__(self, repo: MoodRecordRepository):
        self.repo = repo

    # TODO: 서비스 메서드 추가


def get_mood_record_service(repo: MoodRecordRepository = Depends(get_mood_record_repository)) -> MoodRecordService:
    return MoodRecordService(repo)
