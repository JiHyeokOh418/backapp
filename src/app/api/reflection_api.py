from fastapi import APIRouter, Depends
from app.service.reflection_service import get_reflection_service, ReflectionService
from app.schema.user_schema import UserClaimDTO
from app.dependencie.auth_dependency import get_current_user


router = APIRouter()

# TODO: 마음 돌아보기 (주간/월간 감정 분석 집계) 엔드포인트 추가
