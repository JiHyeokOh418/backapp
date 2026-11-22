import os
import secrets
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from app.repository.redis_repository import get_redis_repository, RedisRepository
from app.service.user_service import get_user_service, UserService
from app.util.jwt_token_util import (
    parse_token, generate_access_token, generate_refresh_token, reissue_access_token
)
from app.schema.auth_schema import JwtTokenDTO, SocialLoginRequestDTO
from app.schema.user_schema import UserClaimDTO, UserCreateDTO

load_dotenv()
TOKEN_BLACKLIST_PREFIX = os.getenv("TOKEN_BLACKLIST_PREFIX", "blacklist:")
REFRESH_TOKEN_PREFIX = os.getenv("REFRESH_TOKEN_PREFIX", "refresh_token:")
OAUTH_STATE_PREFIX = os.getenv("OAUTH_STATE_PREFIX", "oauth_state:")

# 예외처리
# 트랜잭션 관리
class AuthService:

    def __init__(
            self,
            redis_repo: RedisRepository,
            user_service: UserService
        ):
        self.redis_repo = redis_repo
        self.user_service = user_service


    # redis에 refresh_token 저장
    # key - 콜론 체이닝
    async def save_refresh_token(self, user_id: int, refresh_token: str) -> None:
        try:
            key = f"{REFRESH_TOKEN_PREFIX}{user_id}"
            ex = 60 * 60 * 24 * 30 # 30일
            await self.redis_repo.set(key, refresh_token, ex=ex)

        except Exception:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="save_refresh_token 오류"
            )


    # redis에 등록된 refresh_token이 유효한지 검사
    async def validate_refresh_token(self, user_id: int, refresh_token: str) -> bool:
        key = f"{REFRESH_TOKEN_PREFIX}{user_id}"
        saved_token = await self.redis_repo.get(key)
        return refresh_token == saved_token


    # redis에 등록된 refresh_token 삭제
    async def delete_refresh_token(self, user_id: int) -> None:
        key = f"{REFRESH_TOKEN_PREFIX}{user_id}"
        await self.redis_repo.delete(key)


    # access_token 무효화 -> 블랙리스트로 등록(로그아웃)
    async def save_blacklisted_token(self, access_token: str) -> None:
        try:
            key = f"{TOKEN_BLACKLIST_PREFIX}{access_token}"
            ex = 60 * 60 * 24 # access_token 만료시간과 동일

            await self.redis_repo.set(key, "blacklisted", ex=ex)

        except Exception:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="save_blacklisted_token 오류"
            )


    # 블랙리스트로 등록되어 있는지 확인
    async def is_blacklisted_token(self, access_token: str) -> bool:
        key = f"{TOKEN_BLACKLIST_PREFIX}{access_token}"
        # True -> 블랙리스트
        # False -> 사용가능
        return await self.redis_repo.exists(key)


    # 소셜 로그인 state 발급 (CSRF 방지, 네이버는 필수)
    async def issue_oauth_state(self) -> str:
        state = secrets.token_urlsafe(16)
        key = f"{OAUTH_STATE_PREFIX}{state}"
        await self.redis_repo.set(key, "1", ex=60 * 5) # 5분
        return state


    # 콜백으로 돌아온 state 검증 (1회용)
    async def validate_oauth_state(self, state: str | None) -> None:
        key = f"{OAUTH_STATE_PREFIX}{state}"
        if not state or not await self.redis_repo.exists(key):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="validate_oauth_state 유효하지 않은 요청입니다."
            )
        await self.redis_repo.delete(key)


    # 소셜 로그인 (없으면 회원가입)
    async def social_login_or_join(self, social_user: SocialLoginRequestDTO) -> JwtTokenDTO:
        user_in_db = await self.user_service.get_user_by_social(
            social_user.social_provider,
            social_user.social_id
        )

        # 1. 비회원 -> 회원가입
        if not user_in_db:
            new_user = UserCreateDTO(
                email=social_user.email,
                social_provider=social_user.social_provider,
                social_id=social_user.social_id
            )
            claims = await self.user_service.join(new_user)

        # 2. 기존 회원
        else:
            claims = UserClaimDTO.model_validate(user_in_db, from_attributes=True)

        # 3. JWT 토큰 만들기 + refresh를 redis에 저장
        access_token = generate_access_token(claims)
        refresh_token = generate_refresh_token(claims)
        await self.save_refresh_token(claims.id, refresh_token)

        return JwtTokenDTO(
            access_token=access_token,
            refresh_token=refresh_token
        )


    # 로그아웃
    async def logout(self, user_id: int, tokens: JwtTokenDTO) -> None:
        if tokens.access_token:
            await self.save_blacklisted_token(tokens.access_token)
        await self.delete_refresh_token(user_id)


    # refresh -> access 재발급
    async def refresh(self, refresh_token: str | None) -> str:
        if not refresh_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="refresh Refresh Token이 없습니다."
            )

        try:
            payload = parse_token(refresh_token)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="refresh 유효하지 않은 Refresh Token"
            )

        is_valid: bool = await self.validate_refresh_token(payload.id, refresh_token)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="refresh 유효하지 않은 Refresh Token"
            )

        return reissue_access_token(refresh_token)



# 레포지토리 주입 팩토리 함수
def get_auth_service(
    redis_repo: RedisRepository = Depends(get_redis_repository),
    user_service: UserService = Depends(get_user_service)
):
    return AuthService(redis_repo, user_service)
