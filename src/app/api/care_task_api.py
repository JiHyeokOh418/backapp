from fastapi import APIRouter, Depends
from app.service.care_task_service import get_care_task_service, CareTaskService
from app.schema.user_schema import UserClaimDTO
from app.dependencie.auth_dependency import get_current_user


router = APIRouter()

# TODO: 오늘의 작은 돌봄 / 나만의 돌봄 (미션과 같은 개념으로 묶어서 처리) 엔드포인트 추가
