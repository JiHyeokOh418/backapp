from fastapi import APIRouter, Query, Depends
from app.service.default_service import get_default_service, DefaultService
from app.schema.common_schema import ApiResponseDTO

router = APIRouter()
