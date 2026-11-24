from fastapi import Depends
from app.repository.reflection_repository import ReflectionRepository, get_reflection_repository


# 마음 돌아보기 (주간/월간 감정 분석 집계) 비즈니스 로직, 예외 처리, 트랜잭션 관리
class ReflectionService:

    def __init__(self, repo: ReflectionRepository):
        self.repo = repo

    # TODO: 서비스 메서드 추가


def get_reflection_service(repo: ReflectionRepository = Depends(get_reflection_repository)) -> ReflectionService:
    return ReflectionService(repo)
