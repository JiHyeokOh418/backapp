# 일정-03 다음 진료일 API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 환자 앱에서 "다음 진료일"(가장 가까운 앞으로의 진료 예약 1건)을 보여 주는 `GET /calendar/next-appointment`를 만든다.

**Architecture:** 기존 캘린더 도메인(`calendar_api → calendar_service → calendar_repository`)에 엔드포인트 1개, 서비스 메서드 1개, 레포 쿼리 1개를 더한다. `appointments`를 직접 조회하고(병원·의사·진료실 이름을 함께 쓰려고) 일정(`schedules`)은 보지 않는다. 새 테이블·새 파일 없음.

**Tech Stack:** FastAPI, SQLAlchemy 2.x async, PostgreSQL, Pydantic v2 (`BaseDTO` camelCase)

**Spec:** `../reference/3조_마음브릿지_요구사항_명세_2026-11-24.pdf` 일정-03 (18쪽), 연결-06·07 (42쪽)
> 일정-03 처리: "진료 예약과 다음 진료일을 보여 준다." 확인 기준: "가장 가까운 미래의 진료 예약이 다음 진료일로 나온다." 저장: `schedules`(진료 예약), `appointments`.

## Global Constraints

- 로그인 환자 본인 예약만 (`Depends(get_current_user)`, `Appointment.patient_id == current_user.id`).
- 응답은 `ApiResponseDTO[...]`, DTO는 `BaseDTO` 상속(camelCase), 시각은 기존 `KstDateTime` 타입.
- 날짜 계산은 KST (`app.util.date_util.today_kst`, `kst_day_range`).
- 주석은 한국어, 기존 캘린더 파일의 번호 주석 스타일을 잇는다.

## 임의 결정 D-38 (명세에 없는 부분, 팀 확인 필요)

| 항목 | 결정 |
|---|---|
| 어떤 예약 | `status ∈ {booked, waiting}` (취소·노쇼·완료·진료 중 제외). 진료(`treatment`)와 심리검사(`psych_test`) **둘 다** — 둘 다 병원 가는 날(D-33과 같은 기준). 응답에 `kind`를 넣어 화면이 구분 |
| "미래" 기준 | **오늘(KST) 0시 이후** 시작. 오늘 10시 예약은 11시에 봐도 아직 끝나지 않았으면(booked·waiting) 계속 "오늘 진료"로 보인다 |
| 정렬 | `scheduled_at`, 같으면 `appointment_id` 오름차순, 1건 |
| 없을 때 | 200, `data: null` |
| `dDay` | KST 날짜 차이 (오늘 0, 내일 1) |

## Review Focus

1. **오늘 이미 지난 시각의 대기 예약** → 다음 진료일로 그대로 나온다 (D-38). Task 1 테스트 "오늘 대기 예약이 다음 진료일".
2. **취소·완료된 예약** → 건너뛰고 그다음 예약이 나온다. Task 1 테스트 "오늘 예약 완료 처리 후 -> 내일 심리검사".
3. **다른 환자 예약** → 절대 안 섞인다. Task 1 테스트 "다른 환자(p2)는 자기 예약".
4. **앞으로 예약이 없는 환자** → 200 + `data: null`, 500 아님. Task 1 테스트 "완료 예약만 있는 환자(p5)".
5. **로그인 안 함** → 401. Task 1 테스트 "쿠키 없음 -> 401".

---

### Task 1: `GET /calendar/next-appointment`

**Files:**
- Modify: `src/app/schema/calendar_schema.py` (DTO 추가, 맨 아래)
- Modify: `src/app/repository/calendar_repository.py` (메서드 추가, `delete_personal_schedule` 뒤)
- Modify: `src/app/service/calendar_service.py` (메서드 추가, `get_day` 뒤)
- Modify: `src/app/api/calendar_api.py` (엔드포인트 추가, 2번 날짜 상세 뒤 — `/days/{day}`보다 경로가 겹치지 않으므로 순서 무관)
- Test: `tests/calendar_api_test.py` (`run()` 끝에 블록 추가)

**Interfaces:**
- Produces:
  - `CalendarRepository.find_next_appointment(patient_id: int, from_at: datetime) -> Appointment | None`
    — `hospital`, `doctor`, `room` 관계를 `selectinload`로 함께 로드
  - `CalendarService.get_next_appointment(user_id: int) -> NextAppointmentResponseDTO | None`
  - `NextAppointmentResponseDTO(BaseDTO)` 필드:
    `appointment_id: int`, `kind: AppointmentKind`, `status: AppointmentStatus`,
    `scheduled_at: KstDateTime`, `end_at: KstDateTime | None`, `d_day: int`,
    `hospital_name: str`, `doctor_name: str`, `room_name: str | None`, `tests: list[str] | None`

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/calendar_api_test.py`의 `run()` 맨 끝에 추가

시드(`seed_doctor_test_data.py`) 기준 p1 예약: 오늘 10시 `waiting`(treatment), 오늘 16시 `cancelled`, 내일 14시 `booked`(psych_test, 검사실, tests=["phq9","gad7"]), 지난달 completed·no_show. p2: 오늘 11시 booked. p5: 오늘 completed 1건뿐 → "다음 진료일 없음" 확인에 사용.

```python
    # ===== 다음 진료일 (일정-03, D-38) =====
    r = await c.get("/calendar/next-appointment")
    check("다음 진료일: 쿠키 없음 -> 401", r.status_code == 401, r.status_code)

    s, d = await call("GET", "/calendar/next-appointment")
    check("다음 진료일: 오늘 대기 예약 (취소된 16시 아님)",
          s == 200 and d["kind"] == "treatment" and d["status"] == "waiting" and d["dDay"] == 0
          and d["scheduledAt"].startswith(day(0) + "T10:00") and d["hospitalName"].startswith("[TEST]")
          and d["roomName"] == "진료실 1" and d["doctorName"], d)

    s, d = await call("GET", "/calendar/next-appointment", cookies={"access_token": token_for(p2)})
    check("다음 진료일: 다른 환자(p2)는 자기 예약 11시", s == 200 and d["scheduledAt"].startswith(day(0) + "T11:00"), d)

    s, d = await call("GET", "/calendar/next-appointment", cookies={"access_token": token_for(users["p5"])})
    check("다음 진료일: 완료 예약만 있는 환자(p5) -> data null", s == 200 and d is None, (s, d))

    # 오늘 예약을 완료 처리하면 그다음(내일 심리검사)이 나온다
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(Appointment)
            .where(Appointment.patient_id == p1.id, Appointment.status == "waiting")
            .values(status="completed")
        )
        await db.commit()
    s, d = await call("GET", "/calendar/next-appointment")
    check("다음 진료일: 오늘 완료 후 -> 내일 심리검사",
          s == 200 and d["kind"] == "psych_test" and d["dDay"] == 1 and d["tests"] == ["phq9", "gad7"]
          and d["roomName"] == "검사실", d)
```

필요한 import를 파일 위에 추가: `from sqlalchemy import update`, `from app.models.appointment_model import Appointment`.
`call()`은 `(status_code, body["data"])`를 돌려준다. 시드 병원 이름은 `HOSPITAL_PREFIX = "[TEST]"`로 시작한다.

- [ ] **Step 2: 실패 확인**

Run: `cd src && $(conda env list | awk '/backapp/{print $NF}')/bin/python ../tests/calendar_api_test.py | tail -8`
Expected: 새 "다음 진료일" 체크 중 401을 뺀 나머지가 FAIL (404), 기존 39개는 PASS.

- [ ] **Step 3: DTO 추가** — `calendar_schema.py`에 위 Interfaces의 `NextAppointmentResponseDTO`. `AppointmentKind`, `AppointmentStatus`는 `app.enums.appointment_enum`에서 import.

- [ ] **Step 4: 레포 쿼리 추가** — `find_next_appointment`

조건: `patient_id == patient_id`, `status.in_([BOOKED, WAITING])`, `scheduled_at >= from_at`; 정렬 `scheduled_at, appointment_id`; `.limit(1)`; `options(selectinload(Appointment.hospital), selectinload(Appointment.doctor), selectinload(Appointment.room))`; `scalar_one_or_none()`.

- [ ] **Step 5: 서비스 메서드 추가** — `get_next_appointment`

`from_at = kst_day_range(today_kst())[0]`. 없으면 `None`. `d_day = (appointment.scheduled_at.astimezone(KST).date() - today_kst()).days`. 이름은 `appointment.hospital.name`, `appointment.doctor.name`, `appointment.room.name if appointment.room else None`. 주석에 `(일정-03, 임의 결정 D-38)`.

- [ ] **Step 6: 엔드포인트 추가** — `calendar_api.py`

```python
@router.get(
    "/next-appointment",
    summary="다음 진료일 (가장 가까운 진료·검사 예약, 없으면 null)",
    response_model=ApiResponseDTO[NextAppointmentResponseDTO]
)
```
message: `"다음 진료일 조회 완료"`.

- [ ] **Step 7: 통과 확인**

Run: Step 2와 같은 명령
Expected: `결과: 44/44 통과, 실패 0`

- [ ] **Step 8: 의사 API 회귀 확인**

Run: `cd src && $(conda env list | awk '/backapp/{print $NF}')/bin/python ../tests/doctor_api_test.py | tail -3`
Expected: `결과: 80/80 통과, 실패 0`

- [ ] **Step 9: 임의 결정 기록** — `../reference/의사웹_백엔드_임의결정_2026-11-24.md` 표에 D-38 한 줄 추가 (이 문서는 우리가 만든 결정 기록이라 원본 명세와 달리 덧붙여 왔음. 사용자 확인 후 진행)

- [ ] **Step 10: 커밋** (브랜치 `feat/schedule-manage`)

```bash
git checkout -b feat/schedule-manage
git add src/app/schema/calendar_schema.py src/app/repository/calendar_repository.py \
        src/app/service/calendar_service.py src/app/api/calendar_api.py tests/calendar_api_test.py
git commit -m "feat: 다음 진료일 API 추가 (일정-03)"
```
