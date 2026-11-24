import os
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, Response, Request, HTTPException, status
from app.schema.common_schema import ApiResponseDTO
from app.schema.user_schema import UserClaimDTO
from app.enums.user_enum import UserSocialProvider
from app.schema.auth_schema import JwtTokenDTO, SocialLoginRequestDTO
from app.service.auth_service import AuthService, get_auth_service
from app.dependencie.auth_dependency import get_current_user, get_tokens

# 소셜 로그인용
import httpx # 추가 요청
from fastapi.responses import RedirectResponse # 페이지 전환
from urllib.parse import urlencode # 요청주소를 조합하기 위한 라이브러리


load_dotenv()
router = APIRouter()

FRONTEND_URL = os.getenv("FRONTEND_URL")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true" # 운영(HTTPS)에서는 true

ACCESS_TOKEN_MAX_AGE = 60 * 60 * 24       # 1일 (jwt_token_util과 동일)
REFRESH_TOKEN_MAX_AGE = 60 * 60 * 24 * 30 # 30일 (jwt_token_util과 동일)


# 구글 로그인
GOOGLE_AUTH_URL = os.getenv("GOOGLE_AUTH_URL")
GOOGLE_TOKEN_URL = os.getenv("GOOGLE_TOKEN_URL")
GOOGLE_USERINFO_URL = os.getenv("GOOGLE_USERINFO_URL")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")

# /auth/google
@router.get("/google", summary="구글 로그인 리다이렉트")
async def google_login(auth_service: AuthService = Depends(get_auth_service)):
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": await auth_service.issue_oauth_state()
    }

    url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"
    return RedirectResponse(url)


# /auth/google/callback
@router.get("/google/callback", summary="구글 로그인 콜백")
async def google_login_callback(
    code: str,
    state: str | None = None,
    auth_service: AuthService = Depends(get_auth_service)
):
    await auth_service.validate_oauth_state(state)

    async with httpx.AsyncClient() as client:
        token_res = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code"
            }
        )
        access_token = token_res.json().get("access_token")

        user_res = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"}
        )

    user = user_res.json()
    user_params = {
        "email": user.get("email"),
        "social_provider": UserSocialProvider.GOOGLE.value,
        "social_id": user.get("sub")
    }

    return await _handle_social_login_or_join(user_params, auth_service)


# 카카오 로그인
KAKAO_CLIENT_ID = os.getenv("KAKAO_CLIENT_ID")
KAKAO_CLIENT_SECRET = os.getenv("KAKAO_CLIENT_SECRET")
KAKAO_REDIRECT_URI = os.getenv("KAKAO_REDIRECT_URI")
KAKAO_AUTH_URL = os.getenv("KAKAO_AUTH_URL")
KAKAO_TOKEN_URL = os.getenv("KAKAO_TOKEN_URL")
KAKAO_USERINFO_URL = os.getenv("KAKAO_USERINFO_URL")

# /auth/kakao
@router.get("/kakao", summary="카카오 로그인 리다이렉트")
async def kakao_login(auth_service: AuthService = Depends(get_auth_service)):
    params = {
        "client_id": KAKAO_CLIENT_ID,
        "redirect_uri": KAKAO_REDIRECT_URI,
        "response_type": "code",
        "state": await auth_service.issue_oauth_state()
    }

    url = f"{KAKAO_AUTH_URL}?{urlencode(params)}"
    return RedirectResponse(url)


# /auth/kakao/callback
@router.get("/kakao/callback", summary="카카오 로그인 콜백")
async def kakao_login_callback(
    code: str,
    state: str | None = None,
    auth_service: AuthService = Depends(get_auth_service)
):
    await auth_service.validate_oauth_state(state)

    async with httpx.AsyncClient() as client:
        token_res = await client.post(
            KAKAO_TOKEN_URL,
            data={
                "code": code,
                "client_id": KAKAO_CLIENT_ID,
                "client_secret": KAKAO_CLIENT_SECRET,
                "redirect_uri": KAKAO_REDIRECT_URI,
                "grant_type": "authorization_code"
            }
        )
        access_token = token_res.json().get("access_token")

        user_res = await client.get(
            KAKAO_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"}
        )

    user = user_res.json()
    user_params = {
        "email": (user.get("kakao_account") or {}).get("email"),
        "social_provider": UserSocialProvider.KAKAO.value,
        "social_id": str(user.get("id"))
    }

    return await _handle_social_login_or_join(user_params, auth_service)


# 네이버 로그인
NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")
NAVER_REDIRECT_URI = os.getenv("NAVER_REDIRECT_URI")
NAVER_AUTH_URL = os.getenv("NAVER_AUTH_URL")
NAVER_TOKEN_URL = os.getenv("NAVER_TOKEN_URL")
NAVER_USERINFO_URL = os.getenv("NAVER_USERINFO_URL")

# /auth/naver
@router.get("/naver", summary="네이버 로그인 리다이렉트")
async def naver_login(auth_service: AuthService = Depends(get_auth_service)):
    params = {
        "client_id": NAVER_CLIENT_ID,
        "redirect_uri": NAVER_REDIRECT_URI,
        "response_type": "code",
        "state": await auth_service.issue_oauth_state() # 네이버는 state 필수
    }

    url = f"{NAVER_AUTH_URL}?{urlencode(params)}"
    return RedirectResponse(url)


# /auth/naver/callback
@router.get("/naver/callback", summary="네이버 로그인 콜백")
async def naver_login_callback(
    code: str,
    state: str | None = None,
    auth_service: AuthService = Depends(get_auth_service)
):
    await auth_service.validate_oauth_state(state)

    async with httpx.AsyncClient() as client:
        token_res = await client.post(
            NAVER_TOKEN_URL,
            data={
                "code": code,
                "state": state,
                "client_id": NAVER_CLIENT_ID,
                "client_secret": NAVER_CLIENT_SECRET,
                "redirect_uri": NAVER_REDIRECT_URI,
                "grant_type": "authorization_code"
            }
        )
        access_token = token_res.json().get("access_token")

        user_res = await client.get(
            NAVER_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"}
        )

    user = user_res.json().get("response") or {}
    user_params = {
        "email": user.get("email"),
        "social_provider": UserSocialProvider.NAVER.value,
        "social_id": str(user.get("id"))
    }

    return await _handle_social_login_or_join(user_params, auth_service)


# 로그아웃
@router.post(
    "/logout",
    summary="로그아웃",
    response_model=ApiResponseDTO,
)
async def logout(
    response: Response,
    current_user: UserClaimDTO = Depends(get_current_user),
    tokens: JwtTokenDTO = Depends(get_tokens),
    auth_service: AuthService = Depends(get_auth_service)
):
    await auth_service.logout(current_user.id, tokens)
    _delete_token_cookies(response)

    return ApiResponseDTO(
        success=True,
        message="로그아웃 성공"
    )


# 토큰 재발급
@router.post(
    "/refresh",
    summary="Access Token 재발급",
    response_model=ApiResponseDTO,
    responses={
        401: {
            "description": "Refresh Token 만료 또는 로그아웃된 토큰",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "refresh 유효하지 않은 Refresh Token"
                    }
                }
            }
        }
    }
)
async def refresh(
    request: Request,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service)
):
    # access_token이 만료된 상태에서도 호출되므로 get_tokens를 쓰지 않는다.
    refresh_token = request.cookies.get("refresh_token")
    access_token = await auth_service.refresh(refresh_token)

    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        max_age=ACCESS_TOKEN_MAX_AGE
    )

    return ApiResponseDTO(
        success=True,
        message="Access Token 재발급 성공"
    )



# 소셜 로그인 공통 처리: 회원 조회/가입 -> 토큰 쿠키 -> 프론트로 이동
async def _handle_social_login_or_join(user_params: dict, auth_service: AuthService):
    if not user_params.get("email") or not user_params.get("social_id"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="소셜 계정 정보를 가져오지 못했습니다. 이메일 제공 동의를 확인해주세요."
        )

    social_user = SocialLoginRequestDTO.model_validate(user_params)
    tokens = await auth_service.social_login_or_join(social_user)

    redirect_response = RedirectResponse(url=FRONTEND_URL)
    _set_token_cookies(redirect_response, tokens)
    return redirect_response


def _set_token_cookies(response: Response, tokens: JwtTokenDTO) -> None:
    response.set_cookie(
        key="access_token",
        value=tokens.access_token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        max_age=ACCESS_TOKEN_MAX_AGE
    )

    response.set_cookie(
        key="refresh_token",
        value=tokens.refresh_token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        max_age=REFRESH_TOKEN_MAX_AGE
    )


def _delete_token_cookies(response: Response) -> None:
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
