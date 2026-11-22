# CLAUDE.md

이 파일은 Claude Code가 이 저장소에서 작업할 때 참고하는 프로젝트 가이드입니다.
응답과 설명은 한국어로 작성합니다.

## 프로젝트 개요

- FastAPI 기반 Python 백엔드 (`backapp`)
- 인프라: PostgreSQL (SQLAlchemy 2.x async), Redis (redis.asyncio), AWS S3 (aioboto3)
- 인증: JWT 쿠키 (`access_token`, `refresh_token`), 소셜 로그인 (Google, Kakao, Naver)
- Python 3.12, conda 환경 기준 (`environment.yaml`)

## 디렉터리 구조

```
src/
├── main.py                  # FastAPI 앱 진입점, lifespan에서 DB/Redis/S3 연결
└── app/
    ├── api/                 # 라우터 (APIRouter), main.py에서 prefix와 함께 include
    ├── service/             # 비즈니스 로직 (DefaultService)
    ├── repository/          # DB/Redis 접근 (생성자 주입, get_*_repository 팩토리)
    ├── model/               # SQLAlchemy ORM 모델 (Base 상속)
    ├── schema/              # Pydantic DTO (요청/응답/claims)
    ├── enum/                # Enum 정의
    ├── dependencie/         # FastAPI Depends용 인증 의존성 (get_current_member 등)
    ├── infrastructure/      # postgresql.py, redis.py, s3.py 클라이언트 설정
    ├── security/            # CORS, 보안 헤더 미들웨어
    ├── util/                # JWT, 이미지 변환, 보안 유틸
    └── weight/              # 모델 가중치 파일 (__weight.pth)
```

계층 흐름: `api → service → repository → infrastructure`

## 실행 방법

`app.*` 형태로 import하므로 `src/`를 기준으로 실행합니다.

```bash
conda env create -f environment.yaml   # 최초 1회
conda activate backapp
cd src
uvicorn main:app --reload
```

- Swagger: `http://localhost:10000/docs`
- 환경 변수는 프로젝트 루트의 `.env`에서 로드합니다 (`load_dotenv()`).
- 서버 시작 시 `Base.metadata.create_all`로 테이블을 자동 생성합니다.

## 코딩 컨벤션

- 계층 분리를 지킵니다. 라우터에 DB 로직을 넣지 말고, 서비스가 레포지토리를 통해 접근합니다.
- 의존성은 생성자 주입(`__init__`)과 `Depends` 팩토리 함수(`get_xxx_repository`, `get_xxx_service`)로 연결합니다.
- DTO는 `pydantic.BaseModel`을 상속하고, ORM과 연결이 필요한 경우 `from_attributes = True`를 사용합니다.
- 비동기 DB 세션은 `AsyncSession`과 `async_sessionmaker`를 사용합니다 (`expire_on_commit=False`).
- ORM 모델은 반드시 `app.infrastructure.postgresql.Base`를 상속합니다.
- 주석과 docstring은 기존 코드처럼 한국어로 작성합니다.
- 설정값(환경 변수)은 하드코딩하지 않고 `os.getenv`로 읽습니다.

## 보안 주의사항

- `.env`에는 DB 접속 정보, JWT 시크릿, AWS 키, OAuth 클라이언트 시크릿이 들어 있습니다. 내용을 출력하거나 커밋하거나 외부로 전송하지 마세요. `.claude/settings.json`에서 읽기가 차단되어 있습니다.
- 현재 CORS는 `allow_origins=["*"]`와 `allow_credentials=True`를 함께 쓰고 있습니다. 운영 배포 전에 허용 origin을 명시적으로 좁히는 것을 검토하세요.
- JWT 생성은 `python-jose`를 사용합니다 (`app/util/jwt_token_util.py`).

## 알려진 상태 (작업 전 확인)

- `app/api/default_api.py`, `app/service/default_service.py`, `app/repository/default_repository.py`는 아직 엔드포인트와 메서드가 비어 있는 뼈대 상태입니다.
- 사용자 도메인 명칭은 `member`가 아니라 `user`로 통일합니다 (`User` 모델, `UserClaimDTO`, `get_current_user`, `SocialProvider`).
- 스키마 규칙: 요청/응답 DTO는 `app.schema.common_schema.BaseDTO`를 상속합니다 (camelCase alias, `from_attributes`). 파일명은 `{도메인}_schema.py`, 클래스명은 `XxxCreateDTO` / `XxxUpdateDTO` / `XxxResponseDTO` 형식입니다. 예시는 `user_schema.py`를 참고하세요.
- API 작성 예시는 `user_api.py` → `user_service.py` → `user_repository.py`입니다. commit은 레포지토리에서 하고, 로그인 사용자는 `Depends(get_current_user)`로 받습니다 (로그아웃 블랙리스트 확인 포함).
- `environment.yaml`과 `environment_memo.txt`는 내용이 동일합니다. 한쪽을 수정하면 다른 쪽도 맞춰 주세요.
- `src/app/weight/__weight.pth`는 3바이트짜리 파일로, `main.py`의 주석에 있는 전이학습 모델 로드와 연결되어 있지 않습니다.

## Git

- 기본 브랜치는 `main`입니다. 작업은 `feat/`, `fix/`, `refactor/`, `chore/` 접두사의 브랜치에서 진행합니다.
- 커밋 메시지는 Conventional Commits 형식을 따릅니다 (`feat:`, `fix:`, `refactor:` 등). 기존 이력: `feat: init`, `fix: model`
- `.env`, `__pycache__/`, `.vscode/*` (단, `settings.json`은 제외) 등은 `.gitignore`로 제외되어 있습니다.
