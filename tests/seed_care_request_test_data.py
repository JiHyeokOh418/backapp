"""
진료 연결 API 테스트 데이터 넣기 / 지우기

실행 (backapp 에서, 서버와 같은 .env 설정으로 연결된다):
    python tests/seed_care_request_test_data.py          # 지우고 다시 넣기
    python tests/seed_care_request_test_data.py --reset  # 지우기만

- 테스트 데이터 표시: 이메일 '@test-cr.mindbridge', 병원 이름 '[TEST-CR]'
  (seed_doctor_test_data.py의 '@test.mindbridge'·'[TEST]'와 겹치지 않게 따로 둔다)
- 위치: 실제 병원과 겹치지 않도록 동해 한가운데(북위 36도, 동경 131.5도)를 기준점으로 쓴다.
  병원은 기준점에서 정북쪽으로 떨어뜨려 놓아서, 위도 차이만으로 거리가 정해진다.
- 지우기: 표시가 붙은 사용자 -> 병원 순. 요청·연락·알림·위험 기록은 사용자와 함께 CASCADE로 지워진다.
"""
import asyncio
import sys
from datetime import timedelta, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import delete, select  # noqa: E402

import app.models  # noqa: E402,F401  (모든 모델 등록)
from app.infrastructure.postgresql import engine, Base, AsyncSessionLocal  # noqa: E402
from app.models.user_model import User  # noqa: E402
from app.models.hospital_model import Hospital  # noqa: E402
from app.models.doctor_profile_model import DoctorProfile  # noqa: E402
from app.models.risk_event_model import RiskEvent  # noqa: E402
from app.models.appointment_change_model import AppointmentChange  # noqa: E402
from app.models.schedule_model import Schedule  # noqa: E402
from app.models.request_message_model import RequestMessage  # noqa: E402
from app.enums.risk_event_enum import RiskEventLevel, RiskEventSource, RiskEventStatus  # noqa: E402
from app.schema.user_schema import UserClaimDTO  # noqa: E402
from app.util.jwt_token_util import generate_access_token  # noqa: E402
from app.util.geo_util import KM_PER_LAT_DEGREE  # noqa: E402

KST = timezone(timedelta(hours=9))
EMAIL_DOMAIN = "@test-cr.mindbridge"
HOSPITAL_PREFIX = "[TEST-CR]"

# 요청 기준점 (동해, 주변에 실제 병원 없음)
BASE_LAT = Decimal("36.0000000")
BASE_LON = Decimal("131.5000000")
# 반경 안 병원이 하나도 없는 위치 (기준점에서 남쪽으로 약 111km)
FAR_LAT = Decimal("35.0000000")
FAR_LON = Decimal("131.5000000")


def north_of_base(km: float) -> Decimal:
    return (BASE_LAT + Decimal(km / KM_PER_LAT_DEGREE)).quantize(Decimal("0.0000001"))


async def reset(db) -> None:
    # ON DELETE RESTRICT인 FK가 있어서 참조하는 행부터 지운다.
    # (request_messages.sender_id·schedules.created_by·appointment_changes.changed_by -> users,
    #  doctor_profiles·request_contacts·appointments -> hospitals)
    test_users = select(User.id).where(User.email.like(f"%{EMAIL_DOMAIN}"))
    test_hospitals = select(Hospital.hospital_id).where(Hospital.name.like(f"{HOSPITAL_PREFIX}%"))

    await db.execute(delete(RequestMessage).where(RequestMessage.sender_id.in_(test_users)))  # sender_id RESTRICT
    await db.execute(delete(Schedule).where(Schedule.created_by.in_(test_users)))
    await db.execute(delete(AppointmentChange).where(AppointmentChange.changed_by.in_(test_users)))
    await db.execute(delete(User).where(User.id.in_(test_users)))  # 요청·연락·알림·프로필 등은 CASCADE
    await db.execute(delete(Hospital).where(Hospital.hospital_id.in_(test_hospitals)))
    await db.commit()


async def seed(db) -> dict:
    # ===== 병원 (기준점에서 북쪽으로 km) =====
    def hospital(key: str, km: float, accepting: bool = True) -> Hospital:
        return Hospital(
            name=f"{HOSPITAL_PREFIX} {key}", phone="02-0000-0000", address=f"테스트 주소 {key}",
            sido="테스트도", sigungu="테스트구",
            latitude=north_of_base(km), longitude=BASE_LON, is_accepting=accepting
        )

    hospitals = {
        "h1": hospital("1km병원", 1),
        "h2": hospital("3km병원", 3),
        "h3": hospital("5km병원", 5),
        "h4": hospital("8km병원", 8),              # 반경 안이지만 4번째라 연락 안 함
        "h5": hospital("15km병원", 15),            # 반경 밖
        "h_closed": hospital("2km휴진병원", 2, accepting=False),  # 요청 안 받음
        "h_empty": hospital("2.5km의사없는병원", 2.5),             # 소속 의사 없음
    }
    db.add_all(hospitals.values())
    await db.flush()

    # ===== 사용자 =====
    def user(key: str, name: str, role: str) -> User:
        return User(
            email=f"{key}{EMAIL_DOMAIN}", name=name, role=role,
            social_provider="google", social_id=f"test-cr-{key}"
        )

    users = {
        "d1": user("d1", "김일번", "doctor"),        # h1
        "d1b": user("d1b", "김일번B", "doctor"),     # h1 (같은 병원 두 번째 의사)
        "d2": user("d2", "이이번", "doctor"),        # h2
        "d3": user("d3", "박삼번", "doctor"),        # h3
        "d4": user("d4", "최사번", "doctor"),        # h4
        "d5": user("d5", "정오번", "doctor"),        # h5
        "d_closed": user("d_closed", "한휴진", "doctor"),  # h_closed
        "d_noprofile": user("d_noprofile", "윤프로필없음", "doctor"),  # 의사 프로필 없음
        "p1": user("p1", "홍길동", "patient"),       # 일반 환자
        "p2": user("p2", "성춘향", "patient"),       # 일반 환자 (다른 환자 확인용)
        "p_crisis": user("p_crisis", "이몽룡", "patient"),  # open high 위험 기록
        "p_far": user("p_far", "변학도", "patient"),  # 주변 병원 없는 위치에서 요청
    }
    db.add_all(users.values())
    await db.flush()

    profiles = [
        ("d1", "h1"), ("d1b", "h1"), ("d2", "h2"), ("d3", "h3"),
        ("d4", "h4"), ("d5", "h5"), ("d_closed", "h_closed"),
    ]
    db.add_all(
        DoctorProfile(user_id=users[u].id, hospital_id=hospitals[h].hospital_id, specialty="정신건강의학과")
        for u, h in profiles
    )

    # ===== 위험 기록 =====
    db.add_all([
        RiskEvent(user_id=users["p_crisis"].id, level=RiskEventLevel.HIGH,
                  source=RiskEventSource.RULE, status=RiskEventStatus.OPEN, evidence="테스트"),
        # p1은 확인 끝난 high와 open medium만 있어서 crisis가 아니어야 한다
        RiskEvent(user_id=users["p1"].id, level=RiskEventLevel.HIGH,
                  source=RiskEventSource.RULE, status=RiskEventStatus.REVIEWED, evidence="테스트"),
        RiskEvent(user_id=users["p1"].id, level=RiskEventLevel.MEDIUM,
                  source=RiskEventSource.RULE, status=RiskEventStatus.OPEN, evidence="테스트"),
    ])
    await db.commit()

    return {"users": users, "hospitals": hospitals}


async def main(reset_only: bool) -> None:
    # 서버 시작 때와 같이 테이블이 없으면 만든다.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        await reset(db)
        if reset_only:
            print("테스트 데이터를 지웠습니다.")
            await engine.dispose()
            return
        data = await seed(db)

    users = data["users"]
    print("테스트 데이터를 넣었습니다. (Swagger: 브라우저 쿠키 access_token에 아래 값을 넣고 호출)")
    print(f"요청 위치: latitude={BASE_LAT}, longitude={BASE_LON} (주변 병원 없는 위치: {FAR_LAT}, {FAR_LON})")
    for key in ("p1", "p_crisis", "d1", "d2"):
        u = users[key]
        token = generate_access_token(UserClaimDTO(id=u.id, email=u.email, role=u.role, social_provider=u.social_provider))
        print(f"\n[{key}] id={u.id} {u.name}\n{token}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main("--reset" in sys.argv))
