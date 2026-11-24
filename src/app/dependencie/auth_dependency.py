import os
from dotenv import load_dotenv
from fastapi import Response, Request, HTTPException, status, Depends

from app.schema.user_schema import UserClaimDTO
from app.enums.user_enum import UserRole
from app.schema.auth_schema import JwtTokenDTO
from app.util.jwt_token_util import parse_token
from app.service.auth_service import AuthService, get_auth_service

# 매 번 로그인이 필요한 페이지들은 토큰 가져와야한다.
# 토큰을 디코드해서 payload가 필요하다.
# 한 번에 처리하자!
# 1. request -> access_token -> 블랙리스트 확인 -> decode -> user_claims
async def get_current_user(
    request: Request,
    auth_service: AuthService = Depends(get_auth_service)
) -> UserClaimDTO:
    access_token = request.cookies.get("access_token")

    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="get_current_user 로그인 세션이 만료되었습니다."
        )

    # 로그아웃된 토큰은 사용 불가
    if await auth_service.is_blacklisted_token(access_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="get_current_user 로그아웃된 토큰입니다."
        )

    try:
        claims = parse_token(access_token)
        return claims

    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="get_current_user parse_token 유효하지 않은 토큰입니다."
        )


# 2. 의사 전용 API: get_current_user + role == doctor 확인 -> 아니면 403
# - role은 JWT에 담겨 있어 DB 조회 없이 확인한다.
# - 관리자가 의사 승인(POST /admin/doctor-verifications/{id}/approve)하면 users.role=doctor가 된다.
#   토큰의 role은 로그인할 때 정해지므로 승인 후 다시 로그인해야 doctor로 바뀐다. (팀 결정)
async def get_current_doctor(
    current_user: UserClaimDTO = Depends(get_current_user)
) -> UserClaimDTO:
    if current_user.role != UserRole.DOCTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="get_current_doctor 의사만 사용할 수 있습니다."
        )

    return current_user


# 3. request -> access_token, refresh_token(JwtTokenDTO)
def get_tokens(request: Request) -> JwtTokenDTO:
    access_token = request.cookies.get("access_token")
    refresh_token = request.cookies.get("refresh_token")

    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="get_tokens 로그인 세션이 만료되었습니다."
        )

    return JwtTokenDTO(
        access_token=access_token,
        refresh_token=refresh_token
    )