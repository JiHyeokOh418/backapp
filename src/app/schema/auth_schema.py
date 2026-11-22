from pydantic import BaseModel
from app.enum.user_enum import SocialProvider


# 소셜 로그인 콜백에서 서버가 제공자(카카오/네이버/구글)에게 직접 받아온 사용자 정보
# (클라이언트가 보내는 값이 아니라 서버 내부에서만 만든다.)
class SocialLoginRequestDTO(BaseModel):
    email: str
    social_provider: SocialProvider
    social_id: str


# 쿠키에서 꺼낸 토큰 묶음
class JwtTokenDTO(BaseModel):
    access_token: str | None = None
    refresh_token: str | None = None
