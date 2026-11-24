"""
의사 웹 API 테스트 데이터 넣기 / 지우기

실행 (backapp/src 에서, 서버와 같은 .env 설정으로 연결된다):
    python ../tests/seed_doctor_test_data.py          # 지우고 다시 넣기
    python ../tests/seed_doctor_test_data.py --reset  # 지우기만

- 테스트 데이터 표시: 이메일 '@test.mindbridge', 병원 이름 '[TEST]', 문항 item_key 'test_'
- 지우기: 위 표시가 붙은 사용자·병원·문항만 지운다. 나머지는 FK의 ON DELETE CASCADE로 같이 지워진다.
- 시각은 실행한 날(KST) 기준으로 만든다. (오늘 예약, 최근 2주 감정 기록 등)
- 끝나면 Swagger에서 쓸 access_token 쿠키 값을 출력한다.
"""
import asyncio
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import delete, or_  # noqa: E402

import app.model  # noqa: E402,F401  (모든 모델 등록)
from app.infrastructure.postgresql import engine, Base, AsyncSessionLocal  # noqa: E402
from app.model.user_model import User  # noqa: E402
from app.model.hospital_model import Hospital  # noqa: E402
from app.model.doctor_profile_model import DoctorProfile  # noqa: E402
from app.model.care_relation_model import CareRelation  # noqa: E402
from app.model.room_model import Room  # noqa: E402
from app.model.appointment_model import Appointment  # noqa: E402
from app.model.appointment_change_model import AppointmentChange  # noqa: E402
from app.model.risk_event_model import RiskEvent  # noqa: E402
from app.model.risk_event_action_model import RiskEventAction  # noqa: E402
from app.model.chat_session_model import ChatSession  # noqa: E402
from app.model.message_model import Message  # noqa: E402
from app.model.emotion_analysis_model import EmotionAnalysis  # noqa: E402
from app.model.session_summary_model import SessionSummary  # noqa: E402
from app.model.checklist_item_model import ChecklistItem  # noqa: E402
from app.model.session_checklist_model import SessionChecklist  # noqa: E402
from app.model.assessment_result_model import AssessmentResult  # noqa: E402
from app.model.emotion_record_model import EmotionRecord  # noqa: E402
from app.model.doctor_memo_model import DoctorMemo  # noqa: E402
from app.schema.user_schema import UserClaimDTO  # noqa: E402
from app.util.jwt_token_util import generate_access_token  # noqa: E402

KST = timezone(timedelta(hours=9))
EMAIL_DOMAIN = "@test.mindbridge"
HOSPITAL_PREFIX = "[TEST]"
ITEM_PREFIX = "test_"


def at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), tzinfo=KST)


async def reset(db) -> None:
    await db.execute(delete(User).where(User.email.like(f"%{EMAIL_DOMAIN}")))
    await db.execute(delete(Hospital).where(Hospital.name.like(f"{HOSPITAL_PREFIX}%")))
    await db.execute(delete(ChecklistItem).where(ChecklistItem.item_key.like(f"{ITEM_PREFIX}%")))
    await db.commit()


async def seed(db) -> dict[str, User]:
    today = datetime.now(KST).date()
    now = datetime.now(KST)

    # ===== 병원·진료실 =====
    h1 = Hospital(name=f"{HOSPITAL_PREFIX} 마음병원", sido="서울", sigungu="강남구")
    h2 = Hospital(name=f"{HOSPITAL_PREFIX} 다른병원", sido="부산", sigungu="해운대구")
    db.add_all([h1, h2])
    await db.flush()

    room1 = Room(hospital_id=h1.hospital_id, name="진료실 1", room_type="consult")
    exam_room = Room(hospital_id=h1.hospital_id, name="검사실", room_type="exam")
    old_room = Room(hospital_id=h1.hospital_id, name="구 진료실", room_type="consult", is_active=False)
    other_room = Room(hospital_id=h2.hospital_id, name="진료실 A", room_type="consult")
    db.add_all([room1, exam_room, old_room, other_room])

    # ===== 사용자 =====
    def user(key: str, name: str, role: str, gender: str | None = None, birth: date | None = None) -> User:
        return User(
            email=f"{key}{EMAIL_DOMAIN}", name=name, role=role, social_provider="google",
            social_id=f"test-{key}", gender=gender, birth_date=birth
        )

    users = {
        "doctor_a": user("doctor_a", "이은솔", "doctor", "female", date(1985, 3, 2)),
        "doctor_b": user("doctor_b", "한도윤", "doctor", "male", date(1980, 7, 9)),
        "patient_x": user("patient_x", "환자계정", "patient"),        # 의사가 아닌 계정 (403 확인용)
        "p1": user("p1", "김민준", "patient", "male", date(1998, 5, 14)),      # 데이터가 가장 많은 환자
        "p2": user("p2", "이서연", "patient", "female", date(2001, 11, 3)),
        "p3": user("p3", "박지훈", "patient", "male", date(1995, 1, 20)),      # 담당이 끝난 환자
        "p4": user("p4", "최유나", "patient", "female", date(1999, 8, 8)),     # 의사 B의 환자
        "p5": user("p5", "정하은", "patient", "female", date(2003, 2, 27)),    # 데이터가 거의 없는 환자
    }
    db.add_all(users.values())
    await db.flush()
    a, b = users["doctor_a"], users["doctor_b"]
    p1, p2, p3, p4, p5 = (users[k] for k in ("p1", "p2", "p3", "p4", "p5"))

    db.add_all([
        DoctorProfile(user_id=a.id, hospital_id=h1.hospital_id, specialty="정신건강의학과"),
        DoctorProfile(user_id=b.id, hospital_id=h2.hospital_id, specialty="정신건강의학과"),
    ])

    # ===== 담당 관계 =====
    started = now - timedelta(days=150)
    db.add_all([
        CareRelation(doctor_id=a.id, patient_id=p1.id, started_at=started),
        CareRelation(doctor_id=a.id, patient_id=p2.id, started_at=started),
        CareRelation(doctor_id=a.id, patient_id=p5.id, started_at=started),
        CareRelation(doctor_id=a.id, patient_id=p3.id, started_at=started, ended_at=now - timedelta(days=1)),
        CareRelation(doctor_id=b.id, patient_id=p4.id, started_at=started),
    ])
    await db.flush()

    # ===== 예약 =====
    def appt(patient, doctor, hospital, start, status, kind="treatment", room=None, **kw) -> Appointment:
        return Appointment(
            patient_id=patient.id, doctor_id=doctor.id, hospital_id=hospital.hospital_id,
            scheduled_at=start, end_at=start + timedelta(minutes=30), status=status, kind=kind,
            room_id=room.id if room else None, booking_source="doctor", created_by=doctor.id, **kw
        )

    tomorrow, last_month = today + timedelta(days=1), today - timedelta(days=30)
    p2_rescheduled = appt(p2, a, h1, at(today, 11), "booked", room=room1, visit_type="return")
    db.add_all([
        # 오늘 (요약: 오늘 5건 = 취소 제외, 완료 1, 대기 2)
        appt(p5, a, h1, at(today, 9), "completed", room=room1, visit_type="first", completed_at=at(today, 9, 30)),
        appt(p1, a, h1, at(today, 10), "waiting", room=room1, visit_type="return"),
        p2_rescheduled,
        appt(p2, a, h1, at(today, 15), "waiting", room=room1, visit_type="return"),
        appt(p1, a, h1, at(today, 16), "cancelled", room=room1),
        appt(p3, a, h1, at(today, 13), "booked", room=room1),        # 담당 끝난 환자 -> 어디에도 안 나와야 함
        appt(p4, b, h2, at(today, 10), "booked", room=other_room),   # 다른 의사 -> 안 나와야 함
        # 내일·다음 주 (캘린더, 겹침 확인용)
        appt(p1, a, h1, at(tomorrow, 14), "booked", kind="psych_test", room=exam_room, tests=["phq9", "gad7"]),
        appt(p2, a, h1, at(today + timedelta(days=7), 10), "booked", room=room1),
        # 지난달 (재진 판정, 노쇼 횟수)
        appt(p1, a, h1, at(last_month, 10), "completed", room=room1, visit_type="first", completed_at=at(last_month, 10, 30)),
        appt(p1, a, h1, at(last_month + timedelta(days=14), 10), "no_show", room=room1),
    ])
    await db.flush()
    db.add(AppointmentChange(
        appointment_id=p2_rescheduled.appointment_id, from_at=at(today - timedelta(days=1), 11), to_at=at(today, 11),
        change_type="reschedule", reason="환자 사정", requested_by="patient", created_at=now - timedelta(days=2)
    ))

    # ===== P1 상담 세션 (메시지 16개, 7번에 위험 감지, 감정 분석) =====
    chat_start = now - timedelta(days=2)
    session = ChatSession(
        user_id=p1.id, status="ended", end_reason="completed", summary_status="ready", session_type="counselling",
        started_at=chat_start, ended_at=chat_start + timedelta(minutes=40)
    )
    db.add(session)
    await db.flush()

    lines = [
        "요즘 잠을 잘 못 자요.", "언제부터 그러셨나요?", "한 달쯤 된 것 같아요.", "잠들기까지 얼마나 걸리세요?",
        "두세 시간은 걸려요.", "많이 힘드셨겠어요.", "가끔은 다 그만두고 싶다는 생각도 들어요.", "그런 생각이 들 때 어떻게 하시나요?",
        "그냥 누워 있어요.", "주변에 이야기할 사람이 있나요?", "친구 한 명이요.", "그 친구와 이야기하면 어떠세요?",
        "조금 나아져요.", "좋은 방법이네요.", "오늘 이야기해서 좀 후련해요.", "다음에 또 이야기해요.",
    ]
    messages = [
        Message(session_id=session.id, seq=i + 1, role="user" if i % 2 == 0 else "assistant",
                content=text, created_at=chat_start + timedelta(minutes=i * 2))
        for i, text in enumerate(lines)
    ]
    db.add_all(messages)
    await db.flush()

    emotion = lambda msg, dominant, version, **scores: EmotionAnalysis(
        message_id=msg.id, model_version=version, dominant=dominant,
        **{e: scores.get(e, 0.02) for e in ("anger", "joy", "anxiety", "embarrassment", "sadness", "hurt")}
    )
    db.add_all([
        emotion(messages[0], "anxiety", "v2", anxiety=0.7),
        emotion(messages[2], "sadness", "v2", sadness=0.6),
        emotion(messages[4], "sadness", "v2", sadness=0.65),
        emotion(messages[6], "hurt", "v1", hurt=0.5),        # 같은 메시지에 2버전 -> v2(sadness)가 보여야 함
        emotion(messages[6], "sadness", "v2", sadness=0.9),
        emotion(messages[8], "sadness", "v2", sadness=0.5),
        emotion(messages[12], "joy", "v2", joy=0.6),
        emotion(messages[14], "joy", "v2", joy=0.7),
    ])
    summary = SessionSummary(
        session_id=session.id, context_summary="한 달째 불면, 잠들기까지 2~3시간. 일시적인 무기력감과 소진 표현이 있었으나 친구와의 대화로 완화됨.",
        mood_summary={"start": "anxiety", "end": "joy"}, topics=["불면", "무기력", "대인관계"],
        chief_complaint="불면", findings={"note": "수면 위생 교육 권장"}
    )
    db.add(summary)
    # 아직 시작 안 한 예정 세션 -> 상담 기록 목록에 안 나와야 함
    db.add(ChatSession(user_id=p1.id, status="scheduled", session_type="counselling", scheduled_at=now + timedelta(days=3)))
    # P2: 요약 없는 세션
    db.add(ChatSession(user_id=p2.id, status="ended", summary_status="pending", session_type="counselling",
                       started_at=now - timedelta(days=1), ended_at=now - timedelta(days=1) + timedelta(minutes=20)))
    await db.flush()
    session.summary_id = summary.id

    # ===== 위험 알림 =====
    p1_high = RiskEvent(
        user_id=p1.id, message_id=messages[6].id, level="high", source="rule", origin="chat", origin_id=str(session.id),
        status="open", evidence="소진·포기 표현", matched_terms=["그만두고 싶다"], context_judgement="자해 의도는 명확하지 않으나 확인 필요",
        category="무기력", score=0.87, model_version="v2", created_at=now - timedelta(hours=2)
    )
    p2_low_reviewed = RiskEvent(
        user_id=p2.id, level="low", source="emotion", origin="diary", status="reviewed", evidence="우울 감정 지속",
        reviewed_by=a.id, reviewed_at=now - timedelta(days=2), created_at=now - timedelta(days=3)
    )
    db.add_all([
        p1_high,
        RiskEvent(user_id=p1.id, level="medium", source="classifier", origin="trend", status="open",
                  evidence="최근 7일 점수 상승", created_at=now - timedelta(days=3)),
        RiskEvent(user_id=p2.id, level="medium", source="llm", origin="assessment", status="open",
                  evidence="PHQ-9 중등도", created_at=now - timedelta(days=1)),
        p2_low_reviewed,
        RiskEvent(user_id=p4.id, level="high", source="rule", origin="chat", status="open",
                  evidence="다른 의사 환자", created_at=now - timedelta(hours=1)),
    ])
    await db.flush()
    db.add_all([
        RiskEventAction(risk_event_id=p1_high.id, actor_type="ai", action="safety_question", created_at=now - timedelta(hours=2)),
        RiskEventAction(risk_event_id=p1_high.id, actor_type="system", action="notify_doctor", created_at=now - timedelta(hours=2)),
        RiskEventAction(risk_event_id=p2_low_reviewed.id, actor_type="doctor", actor_id=a.id, action="review",
                        created_at=now - timedelta(days=2)),
    ])

    # ===== P1 사전 문진 (체크리스트 + 척도) =====
    intake_start = now - timedelta(days=10)
    intake = ChatSession(user_id=p1.id, status="ended", end_reason="completed", summary_status="ready",
                         session_type="intake", started_at=intake_start, ended_at=intake_start + timedelta(minutes=25))
    db.add(intake)
    await db.flush()
    db.add(SessionSummary(session_id=intake.id, context_summary="초진 전 사전 문진", chief_complaint="잠을 못 잠, 무기력",
                          findings={"phq9": "moderate", "isi": "moderate"}))

    items = [
        ChecklistItem(item_key=f"{ITEM_PREFIX}phq9_1", label="흥미나 즐거움이 거의 없음", answer_type="scale",
                      options=[0, 1, 2, 3], instrument="phq9", item_no=1),
        ChecklistItem(item_key=f"{ITEM_PREFIX}phq9_2", label="기분이 가라앉거나 우울함", answer_type="scale",
                      options=[0, 1, 2, 3], instrument="phq9", item_no=2),
        ChecklistItem(item_key=f"{ITEM_PREFIX}gad7_1", label="초조하거나 불안함", answer_type="scale",
                      options=[0, 1, 2, 3], instrument="gad7", item_no=1),
        ChecklistItem(item_key=f"{ITEM_PREFIX}sleep_note", label="수면 관련 자유 기술", answer_type="text"),
    ]
    db.add_all(items)
    await db.flush()
    db.add_all([
        SessionChecklist(session_id=intake.id, item_id=items[1].id, sort_order=2, required=True, status="done", value=2, ask_count=1),
        SessionChecklist(session_id=intake.id, item_id=items[0].id, sort_order=1, required=True, status="done", value=3, ask_count=1),
        SessionChecklist(session_id=intake.id, item_id=items[2].id, sort_order=3, required=True, status="skipped",
                         skip_reason="user_declined", ask_count=2),
        SessionChecklist(session_id=intake.id, item_id=items[3].id, required=False, status="pending"),  # sort_order 없음 -> 맨 뒤
    ])

    # ===== 척도 결과 (경과 그래프: 4개월, 문진 세션 연결) =====
    db.add_all([
        AssessmentResult(user_id=p1.id, instrument="phq9", total_score=20, severity="severe", source="clinic",
                         assessed_at=now - timedelta(days=120)),      # 3개월 밖 -> 그래프에 안 나와야 함
        AssessmentResult(user_id=p1.id, instrument="phq9", total_score=16, severity="moderately_severe", source="clinic",
                         assessed_at=now - timedelta(days=60)),
        AssessmentResult(user_id=p1.id, instrument="phq9", total_score=14, severity="moderate", source="ai_intake",
                         session_id=intake.id, assessed_at=intake_start + timedelta(minutes=5)),
        AssessmentResult(user_id=p1.id, instrument="phq9", total_score=12, severity="moderate", source="ai_intake",
                         session_id=intake.id, assessed_at=intake_start + timedelta(minutes=20)),  # 문진 카드에 이 값
        AssessmentResult(user_id=p1.id, instrument="isi", total_score=17, severity="moderate", source="ai_intake",
                         session_id=intake.id, assessed_at=intake_start + timedelta(minutes=22)),
        AssessmentResult(user_id=p1.id, instrument="phq9", total_score=9, severity="mild", source="self",
                         assessed_at=now - timedelta(days=1)),
    ])

    # ===== P1 감정 기록 (최근 2주 + 그 전 1주, 하루 1건, 며칠은 비움) =====
    tags = ["불안", "피곤", "무기력", "불안", None, "괜찮음", "피곤"]
    for offset in range(20, -1, -1):
        if offset in (4, 9, 15):
            continue
        day = today - timedelta(days=offset)
        db.add(EmotionRecord(
            user_id=p1.id, record_date=at(day, 0), mood_score=2 + (20 - offset) % 3 + (1 if offset < 7 else 0),
            mood_tag=tags[offset % 7], created_at=at(day, [7, 13, 22, 2][offset % 4], 30)
        ))

    # ===== 메모 (메모 팝업 회귀 확인용) =====
    db.add_all([
        DoctorMemo(patient_id=p1.id, doctor_id=a.id, category="clinic", content="수면제 처방 검토", is_pinned=True,
                   created_at=now - timedelta(days=5), updated_at=now - timedelta(days=5)),
        DoctorMemo(patient_id=p1.id, doctor_id=a.id, category="counsel", content="친구와의 관계가 지지 요인",
                   created_at=now - timedelta(days=2), updated_at=now - timedelta(days=2)),
    ])

    await db.commit()
    return users


async def main(reset_only: bool) -> None:
    # 서버 시작 때와 같이 테이블이 없으면 만든다.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        await reset(db)
        if reset_only:
            print("테스트 데이터를 지웠습니다.")
            return
        users = await seed(db)

    print("테스트 데이터를 넣었습니다. (Swagger: 브라우저 쿠키 access_token에 아래 값을 넣고 호출)")
    for key in ("doctor_a", "doctor_b", "patient_x"):
        u = users[key]
        token = generate_access_token(UserClaimDTO(id=u.id, email=u.email, role=u.role, social_provider=u.social_provider))
        print(f"\n[{key}] id={u.id} {u.name}\n{token}")
    print("\n환자 id:", {k: users[k].id for k in ("p1", "p2", "p3", "p4", "p5")})

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main("--reset" in sys.argv))
