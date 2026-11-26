from fastapi import APIRouter, Depends
from app.service.mood_record_service import get_mood_record_service, MoodRecordService
from app.schema.user_schema import UserClaimDTO
from app.dependencie.auth_dependency import get_current_user


router = APIRouter()

# TODO: 마음 기록 (마음 날씨/키워드/한 줄) 엔드포인트 추가
