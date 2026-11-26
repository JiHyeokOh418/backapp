from fastapi import Depends
from app.repository.care_task_repository import CareTaskRepository, get_care_task_repository


# 오늘의 작은 돌봄 / 나만의 돌봄 (미션과 같은 개념으로 묶어서 처리) 비즈니스 로직, 예외 처리, 트랜잭션 관리
class CareTaskService:

    def __init__(self, repo: CareTaskRepository):
        self.repo = repo

    # TODO: 서비스 메서드 추가


def get_care_task_service(repo: CareTaskRepository = Depends(get_care_task_repository)) -> CareTaskService:
    return CareTaskService(repo)
