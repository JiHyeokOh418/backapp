from fastapi import Depends
from app.repository.llm_repository import LlmRepository, get_llm_repository


# 예외처리
# 트랜잭션 관리
class LlmService:

    def __init__(self, repo: LlmRepository):
        self.repo = repo



# 레포지토리 주입 팩토리 함수
def get_default_service(repo: LlmRepository = Depends(get_llm_repository)):
    return LlmService(repo)