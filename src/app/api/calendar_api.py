from fastapi import APIRouter, Depends
from app.service.calendar_service import get_calendar_service, CalendarService
from app.schema.user_schema import UserClaimDTO
from app.dependencie.auth_dependency import get_current_user


router = APIRouter()

# TODO: 캘린더 엔드포인트 추가
