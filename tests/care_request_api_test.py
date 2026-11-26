"""
진료 연결 API 통합 테스트 (실제 DB·Redis 사용)

실행 (backapp 에서):
    python tests/care_request_api_test.py

흐름: 서버 시작(lifespan) -> 테스트 데이터 넣기(seed_care_request_test_data) -> HTTP로 API 호출 -> DB 행 확인
     -> 테스트 데이터 정리. 실패한 케이스가 있으면 종료 코드 1.
"""
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import httpx  # noqa: E402
from jose import jwt  # noqa: E402
from sqlalchemy import text  # noqa: E402

from main import app  # noqa: E402
from app.infrastructure.postgresql import engine, AsyncSessionLocal  # noqa: E402
from app.schema.user_schema import UserClaimDTO  # noqa: E402
from app.util import jwt_token_util  # noqa: E402
from app.repository.care_request_repository import CareRequestRepository  # noqa: E402
from app.service.care_request_service import CareRequestExpireService, CARE_REQUEST_TIMEOUT_SECONDS  # noqa: E402
import seed_care_request_test_data as seed_module  # noqa: E402

KST = timezone(timedelta(hours=9))
engine.echo = False  # SQL 로그 끄기

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail="") -> None:
    results.append((name, bool(ok), str(detail)))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  -> {detail}"))


def token_for(user) -> str:
    claims = UserClaimDTO(id=user.id, email=user.email, role=user.role, social_provider=user.social_provider).model_dump(mode="json")
    exp = datetime.now(timezone.utc) + timedelta(days=1)
    return jwt.encode({**claims, "exp": exp}, jwt_token_util.SECRET_KEY, algorithm=jwt_token_util.ALGORITHM)


async def scalar(sql: str, **params):
    async with AsyncSessionLocal() as db:
        return (await db.execute(text(sql), params)).scalar()


async def rows(sql: str, **params):
    async with AsyncSessionLocal() as db:
        return (await db.execute(text(sql), params)).all()


# 스케줄러 1회 직접 실행 (서버의 10초 루프가 lock을 잡고 있으면 잠깐 뒤 다시)
async def run_expire_once(now: datetime):
    for _ in range(20):
        async with AsyncSessionLocal() as db:
            result = await CareRequestExpireService(CareRequestRepository(db)).run_once(now=now)
        if result.lock_acquired:
            return result
        await asyncio.sleep(0.1)
    raise RuntimeError("스케줄러 lock을 잡지 못했습니다.")


def request_body(lat=seed_module.BASE_LAT, lon=seed_module.BASE_LON, **extra) -> dict:
    return {
        "requestType": "consult", "address": "테스트 상세 주소", "sido": "테스트도", "sigungu": "테스트구",
        "latitude": str(lat), "longitude": str(lon), "preferredTime": "오늘 오후", "memo": "잠이 안 와요",
        **extra,
    }


async def run(c: httpx.AsyncClient, data: dict) -> None:
    u, h = data["users"], data["hospitals"]
    cookie = {key: {"access_token": token_for(user)} for key, user in u.items()}

    async def send(method, path, body=None, who="p1"):
        r = await c.request(method, path, cookies=cookie[who], json=body)
        return r.status_code, r.json().get("data")

    # ===== 1단계: 권한·검증 =====
    r = await c.post("/care-requests", json=request_body())
    check("권한: 쿠키 없음 -> 401", r.status_code == 401, r.status_code)
    s, _ = await send("POST", "/care-requests", request_body(), who="d1")
    check("권한: 의사 계정 -> 403", s == 403, s)
    s, _ = await send("POST", "/care-requests", {k: v for k, v in request_body().items() if k != "latitude"})
    check("검증: 위도 없음 -> 422", s == 422, s)

    # ===== 1단계: 주변 병원 연락 =====
    s, d = await send("POST", "/care-requests", request_body())
    check("요청: 201, contacting, 연락 3곳, mode nearby",
          s == 201 and d["status"] == "contacting" and d["contactCount"] == 3 and d["requestMode"] == "nearby", (s, d))
    check("요청: 응답에 위험·주소·위치 필드 없음, 연결 전 hospital null",
          d and not ({"riskLevel", "risk", "address", "latitude", "longitude"} & set(d)) and d["hospital"] is None, d)
    req1 = d["requestId"]

    contacts = await rows("select hospital_id, status from request_contacts where request_id = :r", r=req1)
    contacted = sorted(hid for hid, _ in contacts)
    expected = sorted(h[k].hospital_id for k in ("h1", "h2", "h3"))
    check("DB: 가까운 3곳(1·3·5km)에만 연락, 병원마다 1건, 모두 sent",
          contacted == expected and all(st == "sent" for _, st in contacts), contacts)

    notified = sorted(uid for (uid,) in await rows(
        "select user_id from notifications where request_id = :r and notification_type = 'request'", r=req1))
    expected_doctors = sorted(u[k].id for k in ("d1", "d1b", "d2", "d3"))
    check("DB: 연락한 병원 소속 의사 전원(4명)에게 알림, 8km·15km·휴진 병원 의사는 없음",
          notified == expected_doctors, notified)

    sent_at = await scalar("select max(sent_at) from request_contacts where request_id = :r", r=req1)
    expected_expires = (sent_at + timedelta(seconds=CARE_REQUEST_TIMEOUT_SECONDS)).astimezone(KST)
    check("요청: expiresAt = sent_at + 60초 (KST)",
          d["expiresAt"] == expected_expires.isoformat(), (d["expiresAt"], expected_expires.isoformat()))

    s, _ = await send("POST", "/care-requests", request_body())
    check("요청: 진행 중 요청이 있으면 409", s == 409, s)

    s, d = await send("GET", "/care-requests/me")
    check("내 요청: 진행 중 요청 반환", s == 200 and d and d["requestId"] == req1, d)
    s, d = await send("GET", "/care-requests/me", who="p2")
    check("내 요청: 없으면 data null", s == 200 and d is None, d)

    # ===== 1단계: 위기 =====
    s, d = await send("POST", "/care-requests", request_body(), who="p_crisis")
    check("위기: open high 위험 기록 -> crisis, 연락 0", s == 201 and d["status"] == "crisis" and d["contactCount"] == 0, d)
    n = await scalar("select count(*) from request_contacts where request_id = :r", r=d["requestId"])
    check("DB: 위기 요청은 연락 내역 0건", n == 0, n)

    # ===== 1단계: 주변 병원 없음 =====
    s, d = await send("POST", "/care-requests",
                      request_body(seed_module.FAR_LAT, seed_module.FAR_LON), who="p_far")
    check("병원 없음: expired, 연락 0", s == 201 and d["status"] == "expired" and d["contactCount"] == 0, d)
    titles = [t for (t,) in await rows(
        "select title from notifications where user_id = :u and request_id = :r", u=u["p_far"].id, r=d["requestId"])]
    check("병원 없음: 환자 알림 1건 '주변에 연락 가능한 병원이 없어요'",
          titles == ["주변에 연락 가능한 병원이 없어요"], titles)

    # ===== 1단계: 무응답 스케줄러 =====
    await run_expire_once(sent_at + timedelta(seconds=59))
    n = await scalar("select count(*) from request_contacts where request_id = :r and status = 'sent'", r=req1)
    check("스케줄러: 59초 뒤에는 그대로 sent", n == 3, n)

    result = await run_expire_once(sent_at + timedelta(seconds=61))
    statuses = [st for (st,) in await rows("select status from request_contacts where request_id = :r", r=req1)]
    req_status = await scalar("select status from care_requests where request_id = :r", r=req1)
    check("스케줄러: 61초 뒤 연락 3건 no_response, 요청 expired",
          statuses == ["no_response"] * 3 and req_status == "expired"
          and result.expired_contact_count >= 3 and result.expired_request_count >= 1, (statuses, req_status, result))
    titles = [t for (t,) in await rows(
        "select title from notifications where user_id = :u and request_id = :r", u=u["p1"].id, r=req1)]
    check("스케줄러: 환자 알림 1건 '연락 가능한 병원을 찾지 못했어요'",
          titles == ["연락 가능한 병원을 찾지 못했어요"], titles)

    s, d = await send("GET", "/care-requests/me")
    check("내 요청: 만료되면 data null", s == 200 and d is None, d)

    # ===== 1단계: 취소 =====
    s, d = await send("POST", "/care-requests", request_body())
    check("만료 뒤 다시 요청 가능 -> contacting", s == 201 and d["status"] == "contacting", (s, d))
    req2 = d["requestId"]

    s, _ = await send("POST", f"/care-requests/{req2}/cancel", who="p2")
    check("취소: 다른 환자 -> 404", s == 404, s)
    s, _ = await send("POST", "/care-requests/999999999/cancel")
    check("취소: 없는 요청 -> 404", s == 404, s)
    s, d = await send("POST", f"/care-requests/{req2}/cancel")
    check("취소: cancelled", s == 200 and d["status"] == "cancelled", d)
    n = await scalar("select count(*) from request_contacts where request_id = :r", r=req2)
    check("DB: 취소해도 연락 내역 3건은 그대로", n == 3, n)
    s, _ = await send("POST", f"/care-requests/{req2}/cancel")
    check("취소: 두 번 -> 409", s == 409, s)
    s, _ = await send("POST", f"/care-requests/{req1}/cancel")
    check("취소: 만료된 요청 -> 409", s == 409, s)

    req3, winner, loser = await run_stage2(send, u, h, req_cancelled=req2)
    await run_stage3(send, u, req3, winner, loser)
    winner_hospital = h["h1"] if winner == "d1" else h["h2"]
    appointment_id = await run_stage4(send, u, req3, winner, loser, winner_hospital)
    await run_stage5(send, u, h, appointment_id, winner, winner_hospital)


async def run_stage2(send, u: dict, h: dict, req_cancelled: int) -> None:
    def find(items, request_id):
        return next((x for x in items or [] if x["requestId"] == request_id), None)

    # ===== 2단계: 권한 =====
    s, _ = await send("GET", "/doctor/care-requests", who="p1")
    check("병원 목록: 환자 계정 -> 403", s == 403, s)
    s, _ = await send("GET", "/doctor/care-requests", who="d_noprofile")
    check("병원 목록: 의사 프로필 없음 -> 404", s == 404, s)
    s, _ = await send("GET", "/doctor/care-requests?tab=wrong", who="d1")
    check("병원 목록: 잘못된 탭 -> 422", s == 422, s)

    # ===== 2단계: 연결 전 목록 =====
    s, d = await send("POST", "/care-requests", request_body(), who="p2")
    req3 = d["requestId"]
    check("2단계 준비: p2 요청 contacting", s == 201 and d["status"] == "contacting", d)

    s, d = await send("GET", "/doctor/care-requests?tab=pending", who="d1")
    item = find(d, req3)
    check("pending: d1(1km 병원)에 요청 보임, requestCode R-000000 형식",
          s == 200 and item and item["requestCode"] == f"R-{req3:06d}" and item["contactStatus"] == "sent", item)
    check("pending: 연결 전 patient null, 상세 주소·위치 없음",
          item and item["patient"] is None and not ({"address", "latitude", "longitude"} & set(item)), item)
    s, d = await send("GET", "/doctor/care-requests?tab=pending", who="d4")
    check("pending: 연락 안 간 d4(8km 병원)에는 없음", s == 200 and find(d, req3) is None, d)
    s, _ = await send("POST", f"/doctor/care-requests/{req3}/respond", {"response": "available"}, who="d4")
    check("respond: 우리 병원 연락 없음 -> 404", s == 404, s)

    # ===== 2단계: 동시에 available =====
    (s1, d1), (s2, d2) = await asyncio.gather(
        send("POST", f"/doctor/care-requests/{req3}/respond", {"response": "available"}, who="d1"),
        send("POST", f"/doctor/care-requests/{req3}/respond", {"response": "available"}, who="d2"),
    )
    check("동시 available: 1곳만 200, 다른 쪽 409", sorted([s1, s2]) == [200, 409], (s1, s2))
    winner, loser = ("d1", "d2") if s1 == 200 else ("d2", "d1")
    winner_hospital = h["h1"] if winner == "d1" else h["h2"]
    winner_data = d1 if s1 == 200 else d2

    matched, req_status = (await rows(
        "select matched_hospital_id, status from care_requests where request_id = :r", r=req3))[0]
    check("DB: 요청 connected, 연결 병원 1곳", req_status == "connected" and matched == winner_hospital.hospital_id,
          (matched, req_status))
    contact_statuses = dict(await rows(
        "select hospital_id, status from request_contacts where request_id = :r", r=req3))
    loser_hospital = h["h2"] if winner == "d1" else h["h1"]
    check("DB: 이긴 병원 available, 진 병원은 rollback되어 sent 그대로",
          contact_statuses[winner_hospital.hospital_id] == "available"
          and contact_statuses[loser_hospital.hospital_id] == "sent", contact_statuses)
    check("respond 응답: 연결 후 patient 이름 있음",
          winner_data and winner_data["patient"] and winner_data["patient"]["name"] == u["p2"].name, winner_data)

    titles = [t for (t,) in await rows(
        "select title from notifications where user_id = :u and request_id = :r", u=u["p2"].id, r=req3)]
    check("DB: 환자 알림 1건 '병원이 연락 가능해요'", titles == ["병원이 연락 가능해요"], titles)

    s, d = await send("GET", "/doctor/care-requests?tab=connected", who=winner)
    item = find(d, req3)
    check("connected 탭: 이긴 병원, patient 이름 있음",
          s == 200 and item and item["patient"]["name"] == u["p2"].name, item)
    s, d = await send("GET", "/doctor/care-requests?tab=closed", who=loser)
    item = find(d, req3)
    check("closed 탭: 진 병원, patient null", s == 200 and item and item["patient"] is None, item)
    s, d = await send("GET", "/doctor/care-requests?tab=pending", who="d3")
    check("pending 탭: 연결된 요청은 남은 병원(d3)에서 빠짐", s == 200 and find(d, req3) is None, d)

    s, _ = await send("POST", f"/doctor/care-requests/{req3}/respond", {"response": "available"}, who="d3")
    check("respond: 이미 연결된 요청 -> 409", s == 409, s)
    s, _ = await send("POST", f"/doctor/care-requests/{req3}/respond", {"response": "declined"}, who=winner)
    check("respond: 이긴 병원이 다시 응답 -> 409", s == 409, s)

    s, d = await send("GET", "/care-requests/me", who="p2")
    check("환자 내 요청: connected, 연결 병원 정보",
          s == 200 and d["status"] == "connected" and d["hospital"]["hospitalId"] == winner_hospital.hospital_id, d)

    # ===== 2단계: 취소된 요청 =====
    s, d = await send("GET", "/doctor/care-requests?tab=closed", who="d1")
    item = find(d, req_cancelled)
    check("closed 탭: 취소된 요청 보임", s == 200 and item and item["requestStatus"] == "cancelled", item)
    s, _ = await send("POST", f"/doctor/care-requests/{req_cancelled}/respond", {"response": "available"}, who="d1")
    check("respond: 취소된 요청 -> 409", s == 409, s)

    # ===== 2단계: 60초 지난 연락, 불가 응답으로 만료 (D-57) =====
    s, d = await send("POST", "/care-requests", request_body(), who="p1")
    req4 = d["requestId"]
    async with AsyncSessionLocal() as db:
        await db.execute(text(
            "update request_contacts set sent_at = sent_at - interval '61 seconds' "
            "where request_id = :r and hospital_id = :h"), {"r": req4, "h": h["h1"].hospital_id})
        await db.commit()
    s, _ = await send("POST", f"/doctor/care-requests/{req4}/respond", {"response": "available"}, who="d1")
    check("respond: 60초 지난 연락 (스케줄러 처리 전이어도) -> 409", s == 409, s)
    s, d = await send("GET", "/doctor/care-requests?tab=pending", who="d1")
    check("pending 탭: 기한 지난 연락은 빠짐", s == 200 and find(d, req4) is None, d)

    await run_expire_once(datetime.now(KST))  # 1km 병원 연락 no_response
    s, d = await send("POST", f"/doctor/care-requests/{req4}/respond", {"response": "declined"}, who="d2")
    check("declined: d2 불가, 남은 병원(d3) 있어서 요청 contacting 유지",
          s == 200 and d["contactStatus"] == "declined" and d["requestStatus"] == "contacting", d)
    s, d = await send("POST", f"/doctor/care-requests/{req4}/respond", {"response": "declined"}, who="d3")
    check("declined: 마지막 병원 불가 -> 요청 바로 expired", s == 200 and d["requestStatus"] == "expired", d)
    titles = [t for (t,) in await rows(
        "select title from notifications where user_id = :u and request_id = :r", u=u["p1"].id, r=req4)]
    check("DB: 환자 알림 1건 '연락 가능한 병원을 찾지 못했어요'",
          titles == ["연락 가능한 병원을 찾지 못했어요"], titles)
    s, d = await send("GET", "/doctor/care-requests?tab=closed", who="d2")
    item = find(d, req4)
    check("closed 탭: 불가 응답한 요청, respondedAt 있음",
          s == 200 and item and item["contactStatus"] == "declined" and item["respondedAt"], item)

    return req3, winner, loser


# req3: p2의 connected 요청, winner: 연결된 병원 의사, loser: 다른 병원 의사
async def run_stage3(send, u: dict, req3: int, winner: str, loser: str) -> None:
    path = f"/care-requests/{req3}/messages"

    async def read_at(message_id):
        return await scalar("select read_at from request_messages where message_id = :m", m=message_id)

    async def chat_notifications(user_key):
        return await scalar(
            "select count(*) from notifications where user_id = :u and request_id = :r and notification_type = 'chat'",
            u=u[user_key].id, r=req3)

    # ===== 3단계: 제3자 =====
    for who, label in [(loser, "다른 병원 의사"), ("p1", "다른 환자")]:
        s, _ = await send("GET", path, who=who)
        check(f"채팅 목록: {label} -> 403", s == 403, s)
        s, _ = await send("POST", path, {"content": "안녕하세요"}, who=who)
        check(f"채팅 전송: {label} -> 403", s == 403, s)
    s, _ = await send("GET", "/care-requests/999999999/messages", who="p2")
    check("채팅 목록: 없는 요청 -> 404", s == 404, s)

    # ===== 3단계: 검증 =====
    s, _ = await send("POST", path, {"content": "   "}, who="p2")
    check("채팅 전송: 공백만 -> 422", s == 422, s)
    s, _ = await send("POST", path, {"content": "가" * 1001}, who="p2")
    check("채팅 전송: 1001자 -> 422", s == 422, s)

    # ===== 3단계: 환자 -> 의사 =====
    s, d = await send("POST", path, {"content": "  내일 오후 괜찮을까요?  "}, who="p2")
    check("채팅 전송: 환자 201, senderRole patient, 앞뒤 공백 제거",
          s == 201 and d["senderRole"] == "patient" and d["content"] == "내일 오후 괜찮을까요?" and d["readAt"] is None, d)
    m1 = d["messageId"]
    n = await chat_notifications(winner)
    check("DB: 연결을 수락한 의사에게 chat 알림 1건", n == 1, n)

    s, d = await send("GET", path, who=winner)
    check("채팅 목록: 의사가 조회 -> 환자 메시지 readAt 채워짐",
          s == 200 and [m["messageId"] for m in d] == [m1] and d[0]["readAt"], d)

    # ===== 3단계: 의사 -> 환자 =====
    s, d = await send("POST", path, {"content": "내일 15시 가능합니다."}, who=winner)
    check("채팅 전송: 의사 201, senderRole doctor", s == 201 and d["senderRole"] == "doctor", d)
    m2 = d["messageId"]
    n = await chat_notifications("p2")
    check("DB: 환자에게 chat 알림 1건", n == 1, n)
    check("DB: 환자가 읽기 전 의사 메시지 read_at 없음", await read_at(m2) is None, await read_at(m2))

    s, d = await send("GET", f"{path}?afterId={m1}", who="p2")
    check("채팅 목록: afterId 뒤 메시지만, 환자가 조회 -> 의사 메시지 readAt 채워짐",
          s == 200 and [m["messageId"] for m in d] == [m2] and d[0]["readAt"], d)

    s, d = await send("GET", path, who="p2")
    check("채팅 목록: 오래된 순", s == 200 and [m["messageId"] for m in d] == [m1, m2], d)

    # ===== 3단계: 연결 안 된 요청 =====
    req_expired = await scalar(
        "select request_id from care_requests where patient_id = :p and status = 'expired' "
        "order by request_id desc limit 1", p=u["p1"].id)
    s, _ = await send("POST", f"/care-requests/{req_expired}/messages", {"content": "안녕하세요"}, who="p1")
    check("채팅 전송: 만료된 요청 -> 409", s == 409, s)
    s, d = await send("GET", f"/care-requests/{req_expired}/messages", who="p1")
    check("채팅 목록: 만료된 요청도 본인은 조회 가능 (빈 목록)", s == 200 and d == [], d)


async def execute(sql: str, **params) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(text(sql), params)
        await db.commit()


# 4단계: req3(p2, winner 병원과 connected)를 예약 확정 -> 예약 id
async def run_stage4(send, u: dict, req3: int, winner: str, loser: str, winner_hospital) -> int:
    path = f"/doctor/care-requests/{req3}/appointment"
    tomorrow = (datetime.now(KST) + timedelta(days=1)).date()
    start = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 15, 0, tzinfo=KST)
    body = {"scheduledAt": start.isoformat(), "contactMethod": "chat"}

    # ===== 4단계: 권한·검증 =====
    s, _ = await send("POST", path, body, who=loser)
    check("예약 확정: 다른 병원 의사 -> 403", s == 403, s)
    s, _ = await send("POST", path, body, who="d_noprofile")
    check("예약 확정: 의사 프로필 없음 -> 404", s == 404, s)
    s, _ = await send("POST", path, body, who="p2")
    check("예약 확정: 환자 계정 -> 403", s == 403, s)
    s, _ = await send("POST", "/doctor/care-requests/999999999/appointment", body, who=winner)
    check("예약 확정: 없는 요청 -> 404", s == 404, s)
    s, _ = await send("POST", path, {"scheduledAt": start.isoformat()}, who=winner)
    check("예약 확정: contactMethod 없음 -> 422", s == 422, s)
    past = datetime.now(KST) - timedelta(hours=1)
    s, _ = await send("POST", path, {**body, "scheduledAt": past.isoformat()}, who=winner)
    check("예약 확정: 지난 시각 -> 400", s == 400, s)

    # 같은 시간 내 다른 예약 (결정-48)
    await execute(
        "insert into appointments (patient_id, doctor_id, hospital_id, contact_method, scheduled_at, end_at, status, "
        "kind, booking_source, created_at) values (:p, :d, :h, 'phone', :s, :e, 'booked', 'treatment', 'doctor', now())",
        p=u["p1"].id, d=u[winner].id, h=winner_hospital.hospital_id, s=start + timedelta(minutes=10),
        e=start + timedelta(minutes=40))
    s, _ = await send("POST", path, body, who=winner)
    check("예약 확정: 같은 시간 내 예약과 겹침 -> 409", s == 409, s)
    await execute("delete from appointments where patient_id = :p and doctor_id = :d", p=u["p1"].id, d=u[winner].id)
    n = await scalar("select count(*) from appointments where request_id = :r", r=req3)
    check("DB: 실패한 확정은 예약을 남기지 않음", n == 0, n)

    # ===== 4단계: 확정 =====
    s, d = await send("POST", path, body, who=winner)
    expected_end = (start + timedelta(minutes=30)).isoformat()
    check("예약 확정: 201, booked, chat, 끝 시각 +30분",
          s == 201 and d["status"] == "booked" and d["contactMethod"] == "chat" and d["endAt"] == expected_end
          and d["patient"]["id"] == u["p2"].id, (s, d))
    appointment_id = d["appointmentId"] if d else None

    n = await scalar("select count(*) from appointments where request_id = :r", r=req3)
    check("DB: 예약 1건 (request_id 연결)", n == 1, n)
    schedule_users = sorted(uid for (uid,) in await rows(
        "select user_id from schedules where appointment_id = :a", a=appointment_id))
    check("DB: 일정 2건 (환자·의사)", schedule_users == sorted([u["p2"].id, u[winner].id]), schedule_users)
    notes = await rows(
        "select user_id, request_id from notifications where appointment_id = :a and notification_type = 'appointment'",
        a=appointment_id)
    check("DB: 환자 알림 1건 (appointment_id·request_id 연결)", [tuple(n) for n in notes] == [(u["p2"].id, req3)], notes)
    req_status = await scalar("select status from care_requests where request_id = :r", r=req3)
    check("DB: 요청 booked", req_status == "booked", req_status)

    s, _ = await send("POST", path, {**body, "scheduledAt": (start + timedelta(hours=2)).isoformat()}, who=winner)
    check("예약 확정: 이미 booked (connected 아님) -> 409", s == 409, s)

    s, d = await send("GET", "/doctor/care-requests?tab=connected", who=winner)
    item = next((x for x in d or [] if x["requestId"] == req3), None)
    check("connected 탭: booked도 보임, patient 이름 있음",
          item and item["requestStatus"] == "booked" and item["patient"]["name"] == u["p2"].name, item)

    # ===== 4단계: booked 채팅은 예약 진료일(KST)까지 (결정-47) =====
    s, _ = await send("POST", f"/care-requests/{req3}/messages", {"content": "내일 뵐게요"}, who="p2")
    check("채팅: booked, 진료일 전 -> 201", s == 201, s)
    await execute(
        "update appointments set scheduled_at = :s, end_at = :e where appointment_id = :a",
        s=start - timedelta(days=3), e=start - timedelta(days=3) + timedelta(minutes=30), a=appointment_id)
    s, _ = await send("POST", f"/care-requests/{req3}/messages", {"content": "안녕하세요"}, who="p2")
    check("채팅: booked, 진료일 지남 -> 409", s == 409, s)
    s, d = await send("GET", f"/care-requests/{req3}/messages", who="p2")
    check("채팅: 진료일 지나도 목록은 조회 가능", s == 200 and len(d) == 3, d)

    return appointment_id


# 5단계: 진료 완료(F-07) -> 담당 등록 -> 담당 의사에게 직접 요청
async def run_stage5(send, u: dict, h: dict, appointment_id: int, winner: str, winner_hospital) -> None:
    register = f"/care-requests/appointments/{appointment_id}/register"

    s, _ = await send("POST", register, {"choice": "register"}, who="p2")
    check("담당 등록: 진료 전(booked) -> 409", s == 409, s)

    # ===== 연결-08: 기존 F-07 상태 변경 API (담당 관계 없는 첫 진료 환자) =====
    ok = True
    for st in ("waiting", "in_progress", "completed"):
        s, d = await send("PUT", f"/doctor/appointments/{appointment_id}/status", {"status": st}, who=winner)
        ok = ok and s == 200 and d["status"] == st
    check("F-07 상태 변경: 진료 연결 예약은 담당 관계 없이도 completed까지", ok, (s, d))

    s, _ = await send("POST", register, {"choice": "register"}, who="p1")
    check("담당 등록: 다른 환자 -> 404", s == 404, s)
    s, _ = await send("POST", "/care-requests/appointments/999999999/register", {"choice": "register"}, who="p2")
    check("담당 등록: 없는 예약 -> 404", s == 404, s)
    s, _ = await send("POST", register, {"choice": "maybe"}, who="p2")
    check("담당 등록: 잘못된 choice -> 422", s == 422, s)

    # ===== 연결-09: once =====
    s, d = await send("POST", register, {"choice": "once"}, who="p2")
    n = await scalar("select count(*) from care_relations where patient_id = :p", p=u["p2"].id)
    check("once: data null, 담당 관계 생기지 않음", s == 200 and d is None and n == 0, (s, d, n))

    # ===== 연결-09: register (기존 담당 d5는 끝남) =====
    await execute(
        "insert into care_relations (patient_id, doctor_id, started_at, created_at) "
        "values (:p, :d, now() - interval '30 days', now())", p=u["p2"].id, d=u["d5"].id)
    s, d = await send("POST", register, {"choice": "register"}, who="p2")
    check("register: 예약 의사가 담당", s == 200 and d and d["doctorId"] == u[winner].id and d["doctorName"], d)
    relations = {doctor_id: ended for doctor_id, ended in await rows(
        "select doctor_id, ended_at is not null from care_relations where patient_id = :p", p=u["p2"].id)}
    check("DB: 담당 관계 1건 추가, 기존 관계(d5)는 ended_at 채워짐",
          relations == {u["d5"].id: True, u[winner].id: False}, relations)
    first_relation = d["relationId"] if d else None
    s, d = await send("POST", register, {"choice": "register"}, who="p2")
    n = await scalar("select count(*) from care_relations where patient_id = :p", p=u["p2"].id)
    check("register: 이미 그 의사가 담당이면 그대로 (새 관계 없음)",
          s == 200 and d["relationId"] == first_relation and n == 2, (d, n))

    # ===== 연결-10: 담당 의사에게 직접 =====
    direct = {"requestType": "treatment", "preferredTime": "이번 주", "memo": "약이 떨어졌어요"}
    s, _ = await send("POST", "/care-requests/direct", direct, who="p1")
    check("직접 요청: 담당 의사 없음 -> 409", s == 409, s)
    s, _ = await send("POST", "/care-requests/direct", direct, who=winner)
    check("직접 요청: 의사 계정 -> 403", s == 403, s)

    s, d = await send("POST", "/care-requests/direct", direct, who="p2")
    check("직접 요청: 201, direct, contacting, 연락 1곳",
          s == 201 and d["requestMode"] == "direct" and d["status"] == "contacting" and d["contactCount"] == 1, d)
    req5 = d["requestId"]
    contacts = [hid for (hid,) in await rows("select hospital_id from request_contacts where request_id = :r", r=req5)]
    check("DB: 담당 의사 병원에만 연락", contacts == [winner_hospital.hospital_id], contacts)
    target = await scalar("select target_doctor_id from care_requests where request_id = :r", r=req5)
    notified = [uid for (uid,) in await rows(
        "select user_id from notifications where request_id = :r and notification_type = 'request'", r=req5)]
    check("DB: target_doctor_id = 담당 의사, 알림은 그 의사에게만",
          target == u[winner].id and notified == [u[winner].id], (target, notified))
    s, _ = await send("POST", "/care-requests/direct", direct, who="p2")
    check("직접 요청: 진행 중 요청이 있으면 409", s == 409, s)

    # 60초 무응답 규칙도 같다 (D-59)
    sent_at = await scalar("select sent_at from request_contacts where request_id = :r", r=req5)
    await run_expire_once(sent_at + timedelta(seconds=61))
    req_status = await scalar("select status from care_requests where request_id = :r", r=req5)
    check("직접 요청: 60초 무응답 -> expired", req_status == "expired", req_status)

    # 이후는 2단계와 같다
    s, d = await send("POST", "/care-requests/direct", direct, who="p2")
    req6 = d["requestId"]
    s, d = await send("POST", f"/doctor/care-requests/{req6}/respond", {"response": "available"}, who=winner)
    check("직접 요청: 담당 의사 available -> connected", s == 200 and d["requestStatus"] == "connected", d)

    # 위기 확인도 같다
    await execute(
        "insert into care_relations (patient_id, doctor_id, started_at, created_at) values (:p, :d, now(), now())",
        p=u["p_crisis"].id, d=u["d1"].id)
    s, d = await send("POST", "/care-requests/direct", direct, who="p_crisis")
    check("직접 요청: open high 위험 기록 -> crisis, 연락 0",
          s == 201 and d["status"] == "crisis" and d["contactCount"] == 0, d)


async def main() -> int:
    async with app.router.lifespan_context(app):
        async with AsyncSessionLocal() as db:
            await seed_module.reset(db)
            data = await seed_module.seed(db)
        try:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                await run(client, data)
        except Exception as e:  # 테스트 코드 자체가 깨져도 정리는 한다
            import traceback
            traceback.print_exc()
            check("테스트 실행 중 예외", False, repr(e))
        finally:
            async with AsyncSessionLocal() as db:
                await seed_module.reset(db)
            print("\n정리: 테스트 데이터 삭제")

    failed = [r for r in results if not r[1]]
    print(f"\n결과: {len(results) - len(failed)}/{len(results)} 통과, 실패 {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
