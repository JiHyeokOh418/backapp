"""
환자 캘린더 API 통합 테스트 (실제 DB·Redis 사용)

실행 (backapp/src 에서):
    python ../tests/calendar_api_test.py

흐름: 서버 시작(lifespan) -> 테스트 데이터 넣기 -> HTTP로 API 호출 -> DB 행 확인 -> 테스트 데이터 정리.
결과 출력·토큰·DB 조회 도우미는 doctor_api_test.py의 것을 같이 쓴다.
"""
import asyncio
import calendar as month_calendar
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import httpx  # noqa: E402
from doctor_api_test import app, AsyncSessionLocal, KST, results, check, token_for, scalar  # noqa: E402
import seed_doctor_test_data as seed_module  # noqa: E402


async def run(c: httpx.AsyncClient, users: dict) -> None:
    p1, p2 = users["p1"], users["p2"]
    P1 = {"access_token": token_for(p1)}
    today = datetime.now(KST).date()
    day = lambda offset: (today + timedelta(days=offset)).isoformat()

    async def call(method, path, body=None, cookies=P1, **params):
        r = await c.request(method, path, cookies=cookies, json=body, params=params)
        return r.status_code, r.json().get("data")

    goal_total = await scalar("select count(*) from missions where mission_type = 'daily_goal' and is_active")

    # ===== 권한 =====
    r = await c.get("/calendar")
    check("권한: 쿠키 없음 -> 401", r.status_code == 401, r.status_code)

    # ===== 날짜 상세 =====
    s, d = await call("GET", f"/calendar/days/{day(0)}")
    check("오늘 상세: isToday, 기분 5점 good·태그", s == 200 and d["isToday"] and d["mood"] == {"score": 5, "level": "good", "tag": "불안"}, d and d.get("mood"))
    goals = {g["name"].replace("[TEST] ", ""): g for g in d["goals"]["items"]}
    check("오늘 목표: 완료 2 / 사용 중 목표 전체 (보너스·사용 중지 제외)",
          d["goals"]["completed"] == 2 and d["goals"]["total"] == goal_total and "모두 완료 보너스" not in goals and "사용 중지 목표" not in goals,
          {k: d["goals"][k] for k in ("completed", "total")})
    check("오늘 목표: 물 6잔 6/6 완료, 일기 0 미완료",
          (goals["물 6잔 마시기"]["progressCount"], goals["물 6잔 마시기"]["targetCount"], goals["물 6잔 마시기"]["completed"]) == (6, 6, True)
          and (goals["한 줄 일기 쓰기"]["progressCount"], goals["한 줄 일기 쓰기"]["completed"]) == (0, False), goals.get("물 6잔 마시기"))
    check("오늘 목표: 표시 순서(sort_order)", [g["name"].replace("[TEST] ", "") for g in d["goals"]["items"]][:3] == ["마음이와 대화하기", "마음 기록", "한 줄 일기 쓰기"], [g["name"] for g in d["goals"]["items"]])
    check("오늘 일기: 미리보기 50자", d["diary"] and len(d["diary"]["preview"]) == 50, d.get("diary"))
    check("오늘 일정: 공지(수정 불가) -> 개인(수정 가능), 다른 환자 일정 없음",
          [(x["scheduleType"], x["editable"]) for x in d["schedules"]] == [("notice", False), ("personal", True)], d["schedules"])

    s, d = await call("GET", f"/calendar/days/{day(-1)}")
    goals = {g["name"].replace("[TEST] ", ""): g for g in d["goals"]["items"]}
    check("어제 목표: 취소한 산책은 미완료, 약 완료, 물 3/6 진행 중",
          d["goals"]["completed"] == 1 and goals["산책 10분"]["completed"] is False and goals["약 챙겨 먹기"]["completed"]
          and (goals["물 6잔 마시기"]["progressCount"], goals["물 6잔 마시기"]["completed"]) == (3, False), d["goals"]["completed"])
    check("어제: 기분 4점 good(경계), 일기 없음", d["mood"]["level"] == "good" and d["mood"]["score"] == 4 and d["diary"] is None, d.get("mood"))
    s, d = await call("GET", f"/calendar/days/{day(-2)}")
    check("2일 전: 기분 3점 neutral(경계), 지운 일기 안 나옴", d["mood"] == {"score": 3, "level": "neutral", "tag": "무기력"} and d["diary"] is None, d)
    s, d = await call("GET", f"/calendar/days/{day(-8)}")
    check("8일 전: 기분 2점 bad", d["mood"]["level"] == "bad", d.get("mood"))
    s, d = await call("GET", f"/calendar/days/{day(-4)}")
    check("4일 전: 의사에게 공유 안 한 기록도 본인 화면에는 나옴", d["mood"] is not None, d.get("mood"))
    s, d = await call("GET", f"/calendar/days/{day(1)}")
    check("내일: 검사 일정", [x["scheduleType"] for x in d["schedules"]] == ["exam"] and d["isToday"] is False, d["schedules"])
    s, _ = await call("GET", "/calendar/days/2026-02-30")
    check("날짜 상세: 없는 날짜 -> 422", s == 422, s)

    # ===== 월 달력 =====
    month = today.strftime("%Y-%m")
    s, d = await call("GET", "/calendar", month=month)
    days = {x["date"]: x for x in (d or {}).get("days", [])}
    check("월 달력: 그 달 모든 날짜", s == 200 and len(days) == month_calendar.monthrange(today.year, today.month)[1] and d["today"] == day(0), len(days))
    t = days.get(day(0), {})
    check("월 달력 오늘: 일기 있음, 목표 2/전체, 일정 2, 병원 가는 날 아님(공지)",
          (t.get("hasDiary"), t.get("goalCompleted"), t.get("goalTotal"), t.get("scheduleCount"), t.get("hasHospitalVisit"), t.get("moodLevel"))
          == (True, 2, goal_total, 2, False, "good"), t)
    if (today + timedelta(days=1)).month == today.month:
        check("월 달력 내일: 병원 가는 날(검사)", days[day(1)]["hasHospitalVisit"] is True, days[day(1)])
    if (today - timedelta(days=2)).month == today.month:
        check("월 달력 2일 전: 지운 일기 -> hasDiary false", days[day(-2)]["hasDiary"] is False, days[day(-2)])
    s, d = await call("GET", "/calendar", month="2026-13")
    check("월 달력: month=2026-13 -> 422", s == 422, s)
    s, d = await call("GET", "/calendar", cookies={"access_token": token_for(p2)}, month=month)
    t2 = {x["date"]: x for x in d["days"]}.get(day(0), {})
    check("다른 환자 달력: 김민준 데이터 없음, 자기 목표 1개", (t2.get("hasDiary"), t2.get("goalCompleted"), t2.get("scheduleCount")) == (False, 1, 1), t2)

    # ===== 개인 일정 =====
    body = {"title": "  치과  ", "startAt": f"{day(5)}T10:00:00+09:00", "endAt": f"{day(5)}T11:00:00+09:00", "memo": "스케일링"}
    s, d = await call("POST", "/calendar/schedules", body)
    check("일정 등록: 201, 개인, 제목 공백 제거, 수정 가능", s == 201 and d["scheduleType"] == "personal" and d["title"] == "치과" and d["editable"], d)
    new_id = d["scheduleId"]
    created_by = await scalar("select created_by from schedules where schedule_id = :i", i=new_id)
    check("DB: 등록자 = 본인", created_by == p1.id, created_by)
    s, d = await call("GET", f"/calendar/days/{day(5)}")
    check("등록한 일정이 그날 상세에 나옴", [x["scheduleId"] for x in d["schedules"]] == [new_id], d["schedules"])

    for name, bad, code in [
        ("끝 <= 시작 -> 400", {"title": "x", "startAt": f"{day(5)}T10:00:00+09:00", "endAt": f"{day(5)}T10:00:00+09:00"}, 400),
        ("알림 >= 시작 -> 400", {"title": "x", "startAt": f"{day(5)}T10:00:00+09:00", "remindAt": f"{day(5)}T10:30:00+09:00"}, 400),
        ("시간대 없는 시각 -> 422", {"title": "x", "startAt": f"{day(5)}T10:00:00"}, 422),
        ("빈 제목 -> 422", {"title": "   ", "startAt": f"{day(5)}T10:00:00+09:00"}, 422),
        ("제목 101자 -> 422", {"title": "가" * 101, "startAt": f"{day(5)}T10:00:00+09:00"}, 422),
    ]:
        s, _ = await call("POST", "/calendar/schedules", bad)
        check(f"일정 등록: {name}", s == code, s)

    s, d = await call("PUT", f"/calendar/schedules/{new_id}", {"title": "치과 정기검진", "endAt": None})
    check("일정 수정: 보낸 값만 (제목 변경, 끝 시각 지움, 메모 유지)", s == 200 and d["title"] == "치과 정기검진" and d["endAt"] is None and d["memo"] == "스케일링", d)
    s, _ = await call("PUT", f"/calendar/schedules/{new_id}", {"startAt": f"{day(5)}T12:00:00+09:00", "endAt": f"{day(5)}T11:00:00+09:00"})
    check("일정 수정: 끝 <= 시작 -> 400", s == 400, s)
    s, _ = await call("PUT", f"/calendar/schedules/{new_id}", {"title": None})
    check("일정 수정: 제목 null -> 400", s == 400, s)

    notice_id = await scalar("select schedule_id from schedules where title = '병원 휴진 안내' and user_id = :u", u=p1.id)
    other_id = await scalar("select schedule_id from schedules where title = '다른 환자 일정'")
    s, _ = await call("PUT", f"/calendar/schedules/{notice_id}", {"title": "바꿈"})
    check("일정 수정: 병원 공지 -> 403", s == 403, s)
    s, _ = await call("PUT", f"/calendar/schedules/{other_id}", {"title": "바꿈"})
    check("일정 수정: 다른 환자 일정 -> 404", s == 404, s)
    s, _ = await call("DELETE", f"/calendar/schedules/{notice_id}")
    check("일정 삭제: 병원 공지 -> 403", s == 403, s)
    s, _ = await call("DELETE", f"/calendar/schedules/{other_id}")
    check("일정 삭제: 다른 환자 일정 -> 404", s == 404, s)
    n = await scalar("select count(*) from schedules where schedule_id in (:a, :b)", a=notice_id, b=other_id)
    check("DB: 거절된 일정은 그대로", n == 2, n)

    s, _ = await call("DELETE", f"/calendar/schedules/{new_id}")
    check("일정 삭제: 내 개인 일정 -> 200", s == 200, s)
    n = await scalar("select count(*) from schedules where schedule_id = :i", i=new_id)
    check("DB: 삭제됨", n == 0, n)
    s, _ = await call("DELETE", f"/calendar/schedules/{new_id}")
    check("일정 삭제: 두 번 -> 404", s == 404, s)


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
            print("\n정리: 테스트 데이터 삭제")

    failed = [r for r in results if not r[1]]
    print(f"\n결과: {len(results) - len(failed)}/{len(results)} 통과, 실패 {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
