"""
의사 웹 API 통합 테스트 (실제 DB·Redis 사용)

실행 (backapp/src 에서):
    python ../tests/doctor_api_test.py

흐름: 서버 시작(lifespan) -> 테스트 데이터 넣기(seed_doctor_test_data) -> HTTP로 API 호출 -> DB 행 확인
     -> 테스트 데이터·블랙리스트 키 정리. 실패한 케이스가 있으면 종료 코드 1.
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
from app.infrastructure.redis import redis_client  # noqa: E402
from app.service.auth_service import TOKEN_BLACKLIST_PREFIX  # noqa: E402
from app.schema.user_schema import UserClaimDTO  # noqa: E402
from app.util import jwt_token_util  # noqa: E402
import seed_doctor_test_data as seed_module  # noqa: E402

KST = timezone(timedelta(hours=9))
engine.echo = False  # SQL 로그 끄기

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  -> {detail}"))


def token_for(user, extra_seconds: int = 0) -> str:
    claims = UserClaimDTO(id=user.id, email=user.email, role=user.role, social_provider=user.social_provider).model_dump(mode="json")
    exp = datetime.now(timezone.utc) + timedelta(days=1, seconds=extra_seconds)
    return jwt.encode({**claims, "exp": exp}, jwt_token_util.SECRET_KEY, algorithm=jwt_token_util.ALGORITHM)


async def scalar(sql: str, **params):
    async with AsyncSessionLocal() as db:
        return (await db.execute(text(sql), params)).scalar()


async def run(c: httpx.AsyncClient, users: dict) -> None:
    a, b, x = users["doctor_a"], users["doctor_b"], users["patient_x"]
    p1, p2, p3, p4, p5 = (users[k] for k in ("p1", "p2", "p3", "p4", "p5"))
    A = {"access_token": token_for(a)}
    B = {"access_token": token_for(b)}
    X = {"access_token": token_for(x)}
    now = datetime.now(KST)
    today = now.date()

    async def get(path, cookies=A, **params):
        r = await c.get(path, cookies=cookies, params=params)
        return r.status_code, (r.json().get("data") if r.headers.get("content-type", "").startswith("application/json") else None)

    async def send(method, path, body=None, cookies=A):
        r = await c.request(method, path, cookies=cookies, json=body)
        return r.status_code, r.json().get("data")

    # ===== 공통 권한 =====
    r = await c.get("/doctor/patients")
    check("권한: 쿠키 없음 -> 401", r.status_code == 401, r.status_code)
    s, _ = await get("/doctor/patients", cookies=X)
    check("권한: 환자 계정 -> 403", s == 403, s)
    logged_out = token_for(a, extra_seconds=5)
    blacklist_key = f"{TOKEN_BLACKLIST_PREFIX}{logged_out}"
    await redis_client.set(blacklist_key, "blacklisted", ex=60)
    s, _ = await get("/doctor/patients", cookies={"access_token": logged_out})
    check("권한: 로그아웃(블랙리스트) 토큰 -> 401", s == 401, s)
    await redis_client.delete(blacklist_key)
    for name, path in [
        ("다른 의사 환자(P4) 경과 그래프", f"/doctor/patients/{p4.id}/assessments"),
        ("담당 끝난 환자(P3) 상담 기록", f"/doctor/patients/{p3.id}/records"),
        ("다른 의사 환자(P4) 감정 리포트", f"/doctor/patients/{p4.id}/emotion-report"),
        ("다른 의사 환자(P4) 예약", f"/doctor/patients/{p4.id}/appointments"),
    ]:
        s, _ = await get(path)
        check(f"권한: {name} -> 403", s == 403, s)

    # ===== F-02 의사 메인 =====
    s, d = await get("/doctor/dashboard/summary")
    check("요약: 오늘 4 / 완료 1 / 대기 2 / 위험 3",
          s == 200 and (d["todayCount"], d["completedCount"], d["waitingCount"], d["openRiskCount"]) == (4, 1, 2, 3), d)

    s, d = await get("/doctor/rooms")
    check("진료실: 내 병원 사용 중 2개", s == 200 and sorted(r["name"] for r in d) == ["검사실", "진료실 1"], d)

    s, d = await get("/doctor/patients")
    check("환자 목록: 위험 순 김민준 -> 이서연 -> 정하은 (P3·P4 없음)",
          s == 200 and [p["id"] for p in d] == [p1.id, p2.id, p5.id], [p.get("name") for p in d or []])
    check("환자 목록: 김민준 high, 10시 waiting 예약",
          d[0]["riskLevel"] == "high" and d[0]["appointment"]["status"] == "waiting"
          and d[0]["appointment"]["scheduledAt"].startswith(f"{today}T10:00"), d[0])
    check("환자 목록: 정하은 위험 없음", d[2]["riskLevel"] is None, d[2])

    s, d = await get("/doctor/patients", tab="waiting")
    check("대기 탭: 김민준, 이서연(15시 예약 표시)",
          s == 200 and [p["id"] for p in d] == [p1.id, p2.id] and d[1]["appointment"]["scheduledAt"].startswith(f"{today}T15:00"), d)
    s, d = await get("/doctor/patients", tab="booked")
    check("예약 탭: 이서연(11시)", s == 200 and [p["id"] for p in d] == [p2.id], d)
    s, d = await get("/doctor/patients", q="민준")
    check("이름 검색 '민준' -> 김민준", s == 200 and [p["id"] for p in d] == [p1.id], d)

    s, d = await get("/doctor/appointments")
    check("오늘 예약: 4건 시각순 (취소·다른 의사·담당 끝 제외)",
          s == 200 and [x["scheduledAt"][11:16] for x in d] == ["09:00", "10:00", "11:00", "15:00"], d)

    s, d = await get("/doctor/risk-events")
    check("위험 알림 open: high -> medium(최근) -> medium, P4 없음",
          s == 200 and [(e["level"], e["patient"]["id"]) for e in d] == [("high", p1.id), ("medium", p2.id), ("medium", p1.id)], d)
    s, d = await get("/doctor/risk-events", status="reviewed")
    check("위험 알림 reviewed: 1건", s == 200 and len(d) == 1 and d[0]["level"] == "low", d)

    s, d = await get("/doctor/calendar")
    days = {x["date"]: x for x in (d or {}).get("days", [])}
    check("캘린더: 오늘 진료 4건", s == 200 and days.get(str(today), {}).get("treatmentCount") == 4, days.get(str(today)))
    tomorrow = today + timedelta(days=1)
    if tomorrow.month == today.month:
        check("캘린더: 내일 검사 1건", days.get(str(tomorrow), {}).get("psychTestCount") == 1, days.get(str(tomorrow)))
    s, _ = await get("/doctor/calendar", month="2026-13")
    check("캘린더: month=2026-13 -> 422", s == 422, s)

    s, d = await get(f"/doctor/patients/{p1.id}/assessments")
    check("경과 그래프: 3개월 안 4점 (16, 14, 12, 9), latest 9 / previous 12",
          s == 200 and [p["totalScore"] for p in d["points"]] == [16, 14, 12, 9]
          and d["latest"]["totalScore"] == 9 and d["previous"]["totalScore"] == 12, d)

    s, d = await get(f"/doctor/patients/{p1.id}/records")
    check("AI 상담 기록: 시작된 세션 2개, 최신 상담 hasRisk", s == 200 and len(d) == 2 and d[0]["hasRisk"] is True
          and d[0]["sessionType"] == "counselling" and d[0]["preview"] and d[1]["sessionType"] == "intake", d)
    s, _ = await get(f"/doctor/patients/{p1.id}/records", tab="diary")
    check("AI 상담 기록: 일기 탭 -> 501", s == 501, s)
    counsel_id = d[0]["id"]

    # ===== F-06 상담 내역 =====
    s, d = await get(f"/doctor/patients/{p1.id}/chat-sessions", limit=1)
    check("세션 목록: 총 2개, limit 1 -> 2페이지", s == 200 and d["totalCount"] == 2 and d["totalPages"] == 2 and len(d["items"]) == 1, d)
    s, d = await get(f"/doctor/chat-sessions/{counsel_id}")
    msgs = (d or {}).get("messages", [])
    check("세션 상세: 메시지 16개 seq 순", s == 200 and [m["seq"] for m in msgs] == list(range(1, 17)), len(msgs))
    check("세션 상세: 7번 메시지 위험 high, 감정은 v2(sadness)",
          msgs[6]["riskLevel"] == "high" and msgs[6]["emotion"]["dominant"] == "sadness", msgs[6])
    check("세션 상세: AI 메시지 감정 없음, 요약 태그", msgs[1]["emotion"] is None and d["summary"]["topics"] == ["불면", "무기력", "대인관계"], d.get("summary"))
    s, _ = await get(f"/doctor/chat-sessions/{counsel_id}", cookies=B)
    check("세션 상세: 다른 의사 -> 403", s == 403, s)
    s, _ = await get("/doctor/chat-sessions/999999999")
    check("세션 상세: 없는 세션 -> 404", s == 404, s)

    # ===== F-05 위험 감지 상세 =====
    s, d = await get(f"/doctor/patients/{p1.id}/risk-events")
    check("환자별 감지: 2건 최신순 (high, medium)", s == 200 and [e["level"] for e in d] == ["high", "medium"], d)
    high_id, p1_medium_id = d[0]["id"], d[1]["id"]
    s, d = await get(f"/doctor/risk-events/{high_id}")
    ctx = (d or {}).get("context", [])
    check("감지 상세: 앞뒤 6개 -> seq 1~13, 7번이 trigger",
          s == 200 and [m["seq"] for m in ctx] == list(range(1, 14)) and [m["seq"] for m in ctx if m["isTrigger"]] == [7], [m["seq"] for m in ctx])
    check("감지 상세: sessionId·걸린 단어·조치 2건",
          d["sessionId"] == counsel_id and d["matchedTerms"] == ["그만두고 싶다"] and len(d["actions"]) == 2, d.get("actions"))

    s, _ = await send("POST", f"/doctor/risk-events/{high_id}/actions", {"action": "note"})
    check("조치: note 메모 없음 -> 422", s == 422, s)
    s, d = await send("POST", f"/doctor/risk-events/{high_id}/actions", {"action": "note", "memo": "보호자 연락 보류"})
    check("조치: note -> 201, 상태 open 유지, 이력 3건(의사 이름)",
          s == 201 and d["status"] == "open" and len(d["actions"]) == 3 and d["actions"][-1]["actorName"] == "이은솔", d)
    s, d = await send("POST", f"/doctor/risk-events/{high_id}/actions", {"action": "escalate", "memo": "위기 대응 연결"})
    check("조치: escalate -> escalated", s == 201 and d["status"] == "escalated", d)
    s, _ = await send("POST", f"/doctor/risk-events/{high_id}/actions", {"action": "escalate"})
    check("조치: escalate 두 번 -> 409", s == 409, s)
    s, _ = await send("POST", f"/doctor/risk-events/{high_id}/review")
    check("확인: escalated 알림 review -> 409", s == 409, s)
    n = await scalar("select count(*) from risk_event_actions where risk_event_id = :i", i=high_id)
    check("DB: 조치 이력 4행 (ai, system, note, escalate)", n == 4, n)

    s, d = await get("/doctor/risk-events")
    p2_medium_id = next(e["id"] for e in d if e["patient"]["id"] == p2.id)
    s, d = await send("POST", f"/doctor/risk-events/{p2_medium_id}/review")
    check("확인: review -> reviewed", s == 200 and d["status"] == "reviewed" and d["reviewedAt"], d)
    s, _ = await send("POST", f"/doctor/risk-events/{p2_medium_id}/review")
    check("확인: 두 번 -> 409", s == 409, s)
    r1, r2 = await asyncio.gather(
        c.post(f"/doctor/risk-events/{p1_medium_id}/review", cookies=A),
        c.post(f"/doctor/risk-events/{p1_medium_id}/review", cookies=A),
    )
    check("확인: 동시에 2번 -> 1번만 성공", sorted([r1.status_code, r2.status_code]) == [200, 409], (r1.status_code, r2.status_code))
    n = await scalar("select count(*) from risk_event_actions where risk_event_id = :i and action = 'review'", i=p1_medium_id)
    check("DB: 동시 확인 이력 1행", n == 1, n)

    # ===== F-04 감정 리포트 =====
    s, d = await get(f"/doctor/patients/{p1.id}/emotion-report", period="week")
    sm = (d or {}).get("summary", {})
    check("감정 리포트: 평균 4.17, 변화 +1.33, 기록 6/7일, 최다 sadness",
          s == 200 and (sm["avgMoodScore"], sm["moodChange"], sm["recordedDays"], sm["totalDays"], sm["topEmotion"]) == (4.17, 1.33, 6, 7, "sadness"), sm)
    check("감정 리포트: 주별 비율 합 1", all(abs(sum(w["ratios"].values()) - 1) < 0.01 for w in d["weeklyEmotions"]) and d["weeklyEmotions"], d["weeklyEmotions"])
    check("감정 리포트: 키워드 불안2·피곤2 먼저", [(k["keyword"], k["count"]) for k in d["keywords"][:2]] in ([("불안", 2), ("피곤", 2)], [("피곤", 2), ("불안", 2)]), d["keywords"])
    check("감정 리포트: 시간대 합 6, 일별 기분 6건", sum(t["count"] for t in d["timeSlots"]) == 6 and len(d["dailyMoods"]) == 6, d["timeSlots"])

    # ===== F-03 설문 결과 =====
    s, d = await get(f"/doctor/patients/{p1.id}/intake")
    check("문진: 점수 phq9 12 / gad7 없음 / isi 17",
          s == 200 and [(x["instrument"], x["totalScore"]) for x in d["scores"]] == [("phq9", 12), ("gad7", None), ("isi", 17)], d.get("scores"))
    check("문진: 문항 순서와 상태",
          [(x["itemKey"], x["status"]) for x in d["answers"]] == [("test_phq9_1", "done"), ("test_phq9_2", "done"), ("test_gad7_1", "skipped"), ("test_sleep_note", "pending")]
          and d["chiefComplaint"] == "잠을 못 잠, 무기력" and len(d["history"]) == 1, d.get("answers"))
    s, _ = await get(f"/doctor/patients/{p1.id}/intake", sessionId=counsel_id)
    check("문진: 상담 세션 id -> 404", s == 404, s)
    s, _ = await get(f"/doctor/patients/{p5.id}/intake")
    check("문진: 문진 없는 환자 -> 404", s == 404, s)

    # ===== F-08 메모 (회귀) =====
    s, d = await get(f"/doctor/patients/{p1.id}/memos")
    check("메모(회귀): 2건, 고정 1, 고정이 위", s == 200 and d["totalCount"] == 2 and d["pinnedCount"] == 1 and d["items"][0]["isPinned"], d)

    # ===== F-07 예약 =====
    s, d = await get(f"/doctor/patients/{p2.id}/appointments", month=today.strftime("%Y-%m"))
    check("환자별 예약: 이서연 변경 1회, 이력 붙음",
          s == 200 and d["rescheduleCount"] == 1 and any(x["changes"] for x in d["items"]), d and {k: d[k] for k in ("rescheduleCount", "cancelCount", "noShowCount")})
    s, d = await get(f"/doctor/patients/{p1.id}/appointments", month=today.strftime("%Y-%m"))
    check("환자별 예약: 김민준 노쇼 1회", s == 200 and d["noShowCount"] == 1, d and d["noShowCount"])

    room1 = await scalar("select r.id from rooms r join hospitals h using (hospital_id) where h.name = '[TEST] 마음병원' and r.name = '진료실 1'")
    other_room = await scalar("select r.id from rooms r join hospitals h using (hospital_id) where h.name = '[TEST] 다른병원'")
    day3 = (today + timedelta(days=3)).isoformat()
    day4 = (today + timedelta(days=4)).isoformat()

    s, new = await send("POST", "/doctor/appointments", {"patientId": p2.id, "scheduledAt": f"{day3}T10:00:00+09:00", "roomId": room1})
    check("예약 추가: 201, 30분, 초진, booked", s == 201 and new["endAt"].startswith(f"{day3}T10:30") and new["visitType"] == "first" and new["status"] == "booked", new)
    new_id = new["appointmentId"]
    n = await scalar("select count(*) from schedules where appointment_id = :i", i=new_id)
    check("DB: 캘린더 일정 2건 생성", n == 2, n)
    s, d = await send("POST", "/doctor/appointments", {"patientId": p1.id, "scheduledAt": f"{day3}T10:15:00+09:00"})
    check("예약 추가: 시간 겹침 -> 409", s == 409, s)
    s, _ = await send("POST", "/doctor/appointments", {"patientId": p1.id, "scheduledAt": (now - timedelta(hours=1)).isoformat()})
    check("예약 추가: 지난 시각 -> 400", s == 400, s)
    s, _ = await send("POST", "/doctor/appointments", {"patientId": p1.id, "scheduledAt": f"{day4}T10:00:00"})
    check("예약 추가: 시간대 없는 시각 -> 422", s == 422, s)
    s, _ = await send("POST", "/doctor/appointments", {"patientId": p1.id, "scheduledAt": f"{day4}T10:00:00+09:00", "roomId": other_room})
    check("예약 추가: 다른 병원 진료실 -> 400", s == 400, s)
    s, _ = await send("POST", "/doctor/appointments", {"patientId": p4.id, "scheduledAt": f"{day4}T10:00:00+09:00"})
    check("예약 추가: 담당 아닌 환자 -> 403", s == 403, s)
    s, p1_new = await send("POST", "/doctor/appointments", {"patientId": p1.id, "scheduledAt": f"{day4}T10:00:00+09:00", "kind": "psych_test"})
    check("예약 추가: 김민준 재진(지난달 완료 있음)", s == 201 and p1_new["visitType"] == "return", p1_new)
    n = await scalar("select count(*) from schedules where appointment_id = :i and schedule_type = 'exam'", i=p1_new["appointmentId"])
    check("DB: 검사 예약 -> exam 일정 2건", n == 2, n)

    s, d = await send("PUT", f"/doctor/appointments/{new_id}", {"scheduledAt": f"{day3}T14:00:00+09:00", "reason": "의사 일정"})
    check("일정 변경: 14:00, 30분 유지, 이력 1건", s == 200 and d["scheduledAt"].startswith(f"{day3}T14:00") and d["endAt"].startswith(f"{day3}T14:30") and len(d["changes"]) == 1, d)
    start_at = await scalar("select min(start_at) from schedules where appointment_id = :i", i=new_id)
    check("DB: 캘린더 일정도 14:00으로 이동", start_at and start_at.astimezone(KST).strftime("%H:%M") == "14:00", start_at)
    s, _ = await send("PUT", f"/doctor/appointments/{new_id}", {"scheduledAt": f"{day4}T10:00:00+09:00"})
    check("일정 변경: 다른 예약과 겹침 -> 409", s == 409, s)

    s, _ = await send("PUT", f"/doctor/appointments/{new_id}/status", {"status": "completed"})
    check("상태: booked -> completed 바로 -> 409", s == 409, s)
    s, _ = await send("PUT", f"/doctor/appointments/{new_id}/status", {"status": "cancelled"})
    check("상태: cancelled는 이 API로 불가 -> 422", s == 422, s)
    ok = True
    for st in ("waiting", "in_progress", "completed"):
        s, d = await send("PUT", f"/doctor/appointments/{new_id}/status", {"status": st})
        ok = ok and s == 200 and d["status"] == st
    check("상태: waiting -> in_progress -> completed, completedAt 기록", ok and d["completedAt"], d)
    s, _ = await send("POST", f"/doctor/appointments/{new_id}/cancel", {})
    check("취소: 완료된 예약 -> 409", s == 409, s)

    p1_new_id = p1_new["appointmentId"]
    s, _ = await send("POST", f"/doctor/appointments/{p1_new_id}/cancel", {}, cookies=B)
    check("취소: 다른 의사 -> 403", s == 403, s)
    s, d = await send("POST", f"/doctor/appointments/{p1_new_id}/cancel", {"reason": "환자 요청"})
    check("취소: cancelled, 이력 cancel", s == 200 and d["status"] == "cancelled" and d["changes"][-1]["changeType"] == "cancel", d)
    n = await scalar("select count(*) from schedules where appointment_id = :i", i=p1_new_id)
    check("DB: 취소하면 캘린더 일정 삭제", n == 0, n)
    s, _ = await send("POST", f"/doctor/appointments/{p1_new_id}/cancel", {})
    check("취소: 두 번 -> 409", s == 409, s)
    s, _ = await send("POST", "/doctor/appointments/999999999/cancel", {})
    check("취소: 없는 예약 -> 404", s == 404, s)


async def main() -> int:
    async with app.router.lifespan_context(app):
        async with AsyncSessionLocal() as db:
            await seed_module.reset(db)
            users = await seed_module.seed(db)
        try:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                await run(client, users)
        except Exception as e:  # 테스트 코드 자체가 깨져도 정리는 한다
            import traceback
            traceback.print_exc()
            check("테스트 실행 중 예외", False, repr(e))
        finally:
            async with AsyncSessionLocal() as db:
                await seed_module.reset(db)
            leftover = [k async for k in redis_client.scan_iter(f"{TOKEN_BLACKLIST_PREFIX}*")]
            print(f"\n정리: 테스트 데이터 삭제, 남은 블랙리스트 키 {len(leftover)}개")

    failed = [r for r in results if not r[1]]
    print(f"\n결과: {len(results) - len(failed)}/{len(results)} 통과, 실패 {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
