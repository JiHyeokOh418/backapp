from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal
from fastapi import Depends, HTTPException, status
from app.repository.doctor_repository import DoctorRepository, get_doctor_repository
from app.enums.appointment_enum import AppointmentStatus, AppointmentKind, AppointmentVisitType, AppointmentBookingSource
from app.enums.schedule_enum import ScheduleType
from app.enums.risk_event_enum import RiskEventLevel, RiskEventStatus
from app.enums.risk_event_action_enum import RiskEventActionActorType
from app.enums.common_enum import Instrument, EmotionType, ChecklistStatus
from app.enums.message_enum import MessageRole, MessageInputType
from app.models.risk_event_model import RiskEvent
from app.models.appointment_model import Appointment
from app.models.message_model import Message
from app.schema.doctor_schema import (
    DashboardSummaryResponseDTO,
    RoomResponseDTO,
    DoctorPatientResponseDTO,
    PatientAppointmentDTO,
    DoctorAppointmentResponseDTO,
    DoctorPatientBriefDTO,
    RiskEventResponseDTO,
    CalendarDayDTO,
    CalendarResponseDTO,
    AssessmentPointDTO,
    AssessmentTrendResponseDTO,
    ChatRecordResponseDTO,
    ChatSessionDetailResponseDTO,
    ChatSessionBriefDTO,
    SessionInputType,
    EmotionChangeDTO,
    ChatSummaryDTO,
    ChatMessageResponseDTO,
    MessageEmotionDTO,
    RiskEventDetailResponseDTO,
    RiskContextMessageDTO,
    RiskEventActionResponseDTO,
    RiskEventActionCreateDTO,
    RiskSimilarHistoryDTO,
    EmotionReportResponseDTO,
    EmotionSummaryDTO,
    DailyMoodDTO,
    WeeklyEmotionDTO,
    EmotionKeywordDTO,
    TimeSlotCountDTO,
    VisitMarkerDTO,
    IntakeResultResponseDTO,
    IntakeScoreDTO,
    IntakeAnswerDTO,
    IntakeSessionBriefDTO,
    IntakePatientInfoDTO,
    AppointmentChangeResponseDTO,
    AppointmentDetailResponseDTO,
    PatientAppointmentsResponseDTO,
    NextAppointmentDTO,
    AppointmentCreateDTO,
    AppointmentRescheduleDTO,
    AppointmentCancelDTO,
    AppointmentStatusUpdateDTO,
)
from app.schema.common_schema import PageResponseDTO
from app.util.date_util import kst_day_range, today_kst, add_months
from app.models.chat_session_model import ChatSession

KST = timezone(timedelta(hours=9)) # UTC+9

# 환자 정렬용 위험 등급 순위 (알림 없음 = 0)
RISK_RANK = {RiskEventLevel.HIGH: 3, RiskEventLevel.MEDIUM: 2, RiskEventLevel.LOW: 1}

# 환자 목록 탭 -> 그날 예약 상태
TAB_STATUS = {"waiting": AppointmentStatus.WAITING, "booked": AppointmentStatus.BOOKED}


# 오늘(KST)에서 months개월 전 같은 날 0시
def months_ago_kst(months: int) -> datetime:
    return kst_day_range(add_months(today_kst(), -months))[0]


# 감정 리포트 기간 -> (첫날, 마지막 다음 날)
# - 임의 결정 D-17: from이 없으면 오늘로 끝나는 기간
# - 임의 결정 D-45 (D-17 수정): week=7일, month=28일(4주), 3months=84일(12주)
#   화면의 월간 "10.15 – 11.11", "지난 4주 대비"에 맞춘다. 달력 1개월이 아니다.
PERIOD_DAYS = {"week": 7, "month": 28, "3months": 84}

def report_range(period: str, start: date | None) -> tuple[date, date]:
    length = timedelta(days=PERIOD_DAYS[period])
    if start is None:
        end = today_kst() + timedelta(days=1)
        return end - length, end

    return start, start + length


# 감정 분석 중 기쁨(joy) 비율 (0~1, 소수 3자리). 분석이 없으면 None
def joy_ratio_of(emotions: list[tuple]) -> float | None:
    if not emotions:
        return None
    return round(sum(1 for _, dominant in emotions if dominant == EmotionType.JOY) / len(emotions), 3)


# 설문 결과 팝업의 척도 카드 3장 (API 명세 F-03: phq9·gad7·isi)
INTAKE_INSTRUMENTS = (Instrument.PHQ9, Instrument.GAD7, Instrument.ISI)

# 설문 결과 팝업의 문진 목록 개수
INTAKE_HISTORY_LIMIT = 10

# 척도 만점 (척도 카드 "19 / 27점")
INSTRUMENT_MAX_SCORE = {Instrument.PHQ9: 27, Instrument.GAD7: 21, Instrument.ISI: 28, Instrument.BDI2: 63}


# 만 나이 (오늘 KST 기준, 올해 생일 전이면 1 뺀다). 생년월일이 없으면 None
def age_of(birth_date: date | None) -> int | None:
    if birth_date is None:
        return None
    today = today_kst()
    return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))


# 척도 문항 점수 (임의 결정 D-50)
# - 척도 문항(instrument 있음)이고 done일 때만: value가 int면 그 값, dict의 score가 int면 그 값, 그 외 None
# TODO: session_checklists.value의 JSON 모양이 문진 저장 쪽에서 정해지면 이 규칙을 맞춘다.
def answer_score(instrument: Instrument | None, answer_status: ChecklistStatus, value) -> int | None:
    if instrument is None or answer_status != ChecklistStatus.DONE:
        return None
    if isinstance(value, dict):
        value = value.get("score")
    # bool은 int의 하위 클래스라 따로 뺀다 (True가 1점이 되지 않게)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


# 예약 길이 기본값 (끝 시각을 안 보냈을 때, 임의 결정 D-22)
DEFAULT_APPOINTMENT_MINUTES = 30

# 진료 상태 변경: 바꿀 상태 -> 바꿀 수 있는 지금 상태 (임의 결정 D-25)
# booked -> waiting -> in_progress -> completed, booked·waiting -> no_show
STATUS_ALLOWED_FROM = {
    AppointmentStatus.WAITING: [AppointmentStatus.BOOKED],
    AppointmentStatus.IN_PROGRESS: [AppointmentStatus.BOOKED, AppointmentStatus.WAITING],
    AppointmentStatus.COMPLETED: [AppointmentStatus.IN_PROGRESS],
    AppointmentStatus.NO_SHOW: [AppointmentStatus.BOOKED, AppointmentStatus.WAITING],
}

# 일정 변경·취소가 되는 상태
CHANGEABLE_STATUSES = (AppointmentStatus.BOOKED, AppointmentStatus.WAITING)

# 예약 종류 -> 캘린더 일정 종류·제목 (임의 결정 D-27)
SCHEDULE_BY_KIND = {
    AppointmentKind.TREATMENT: (ScheduleType.APPOINTMENT, "진료 예약"),
    AppointmentKind.PSYCH_TEST: (ScheduleType.EXAM, "심리검사 예약"),
}


# 시간대 (임의 결정 D-15): 0~6 새벽 / 6~12 오전 / 12~18 오후 / 18~24 저녁
TIME_SLOTS = ("dawn", "morning", "afternoon", "evening")


# 요약 미리보기 길이
PREVIEW_LENGTH = 80

# 임의 결정 D-06: 위험 감지 상세의 "앞뒤 6턴" = 감지된 메시지 앞 6개 + 뒤 6개 메시지
CONTEXT_AROUND = 6

# 위험 감지 상세의 "이전 기록 최근 30일 유사 표현" 기간 (임의 결정 D-48)
SIMILAR_RISK_DAYS = 30


# 세션 번호 = "A-" + 시작 시각(KST)의 MMDD, 시작 전이면 예정 시각 기준 (임의 결정 D-41)
# - 상담 상세(F-06)와 위험 감지 상세(F-05)에서 같이 쓴다.
# TODO: ERD에 세션 번호 컬럼이 없어서 같은 날 세션이 2개면 번호가 겹친다.
def session_code(session: ChatSession) -> str:
    base = session.started_at or session.scheduled_at
    return "A-" + base.astimezone(KST).strftime("%m%d")


# 소요 시간(분, 버림). 시작·종료 중 하나라도 없거나 종료가 시작보다 이르면(잘못된 데이터) None
# - 상담 상세(F-06)와 설문 결과(F-03)에서 같이 쓴다.
def duration_minutes(started_at: datetime | None, ended_at: datetime | None) -> int | None:
    if started_at is None or ended_at is None or ended_at < started_at:
        return None
    return int((ended_at - started_at).total_seconds() // 60)


# 세션 입력 방식: 환자(user) 메시지가 모두 text -> text, 모두 voice -> voice, 섞이면 mixed (임의 결정 D-43)
# - 환자 메시지가 없으면 None. AI(assistant) 메시지는 보지 않는다.
# - 상담 상세(F-06)와 설문 결과(F-03)에서 같이 쓴다.
def input_type_of(messages: list[Message]) -> SessionInputType | None:
    types = {m.input_type for m in messages if m.role == MessageRole.USER}
    if not types:
        return None
    if len(types) > 1:
        return "mixed"
    return "voice" if types == {MessageInputType.VOICE} else "text"


# 예외처리, 서비스가 드러나도록 이름을 선정해서 제작
# 트랜잭션 관리
class DoctorService:

    def __init__(self, repo: DoctorRepository):
        self.repo = repo


    # 담당 환자인지 확인 (보안-02, 공통-04) - 아니면 403
    async def _ensure_in_charge(self, doctor_id: int, patient_id: int) -> None:
        if not await self.repo.exists_care_relation(doctor_id, patient_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="담당 환자가 아닙니다."
            )


    # ORM -> 상담 기록 1건 DTO (위젯, 상담 내역 팝업 목록 공용)
    @staticmethod
    def _to_chat_record(session: ChatSession, has_risk: bool) -> ChatRecordResponseDTO:
        summary = session.summary
        return ChatRecordResponseDTO(
            id=session.id,
            session_type=session.session_type,
            status=session.status,
            started_at=session.started_at,
            ended_at=session.ended_at,
            summary_status=session.summary_status,
            preview=summary.context_summary[:PREVIEW_LENGTH] if summary and summary.context_summary else None,
            topics=summary.topics if summary else None,
            has_risk=has_risk
        )


    # ORM -> 위험 알림 응답 DTO
    @staticmethod
    def _to_risk_response(event: RiskEvent) -> RiskEventResponseDTO:
        return RiskEventResponseDTO(
            id=event.id,
            level=event.level,
            patient=DoctorPatientBriefDTO(id=event.user_id, name=event.patient.name if event.patient else None),
            evidence=event.evidence,
            origin=event.origin,
            status=event.status,
            is_repeated=event.is_repeated,
            is_uncertain=event.is_uncertain,
            due_at=event.due_at,
            created_at=event.created_at,
            reviewed_at=event.reviewed_at
        )


    # ORM -> 예약 응답 DTO
    @staticmethod
    def _to_appointment_response(appointment: Appointment) -> DoctorAppointmentResponseDTO:
        return DoctorAppointmentResponseDTO(
            appointment_id=appointment.appointment_id,
            scheduled_at=appointment.scheduled_at,
            end_at=appointment.end_at,
            patient=DoctorPatientBriefDTO(
                id=appointment.patient_id,
                name=appointment.patient.name if appointment.patient else None
            ),
            visit_type=appointment.visit_type,
            kind=appointment.kind,
            contact_method=appointment.contact_method,
            room_id=appointment.room_id,
            status=appointment.status
        )


    # 1. 상단 요약 바
    async def get_dashboard_summary(self, doctor_id: int, day: date | None) -> DashboardSummaryResponseDTO:
        day = day or today_kst()
        start, end = kst_day_range(day)

        today_count, completed_count, waiting_count = await self.repo.count_appointments_by_status(doctor_id, start, end)
        open_risk_count = await self.repo.count_open_risk_events(doctor_id)

        return DashboardSummaryResponseDTO(
            date=day,
            today_count=today_count,
            completed_count=completed_count,
            waiting_count=waiting_count,
            open_risk_count=open_risk_count
        )


    # 2. 진료실 목록 (내 소속 병원)
    async def get_rooms(self, doctor_id: int) -> list[RoomResponseDTO]:
        profile = await self.repo.find_doctor_profile(doctor_id)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="의사 프로필이 없습니다."
            )

        rooms = await self.repo.find_active_rooms(profile.hospital_id)
        return [RoomResponseDTO.model_validate(room) for room in rooms]


    # 3. 환자 목록·검색 (의사-01)
    # - 담당 환자에 "확인 안 한 알림 중 최고 등급"과 "그날 예약"을 붙인다.
    # - 정렬: 위험 high -> medium -> low -> 없음, 같으면 최근 알림 -> 예약 시각 -> id
    # - 임의 결정 D-01 (결정-39 미정): 위험도가 같으면 최근 알림 -> 예약 시각 -> id
    # - 임의 결정 D-02: waiting/booked 탭은 그날 예약 중 그 상태인 예약이 하나라도 있는 환자, 표시 예약도 그 예약
    # ponytail: 담당 환자 수만큼 파이썬에서 합치고 정렬한다. 환자가 수천 명이 되면 SQL 정렬로 옮긴다.
    async def get_patients(
        self, doctor_id: int, tab: Literal["all", "waiting", "booked"], day: date | None, q: str | None
    ) -> list[DoctorPatientResponseDTO]:
        day = day or today_kst()
        start, end = kst_day_range(day)

        patients = await self.repo.find_care_patients(doctor_id, q.strip() if q else None)
        if not patients:
            return []

        patient_ids = [patient.id for patient in patients]

        # 환자별 그날 첫 예약 (시각순으로 오므로 처음 것만 남긴다)
        # - waiting/booked 탭이면 그 상태인 예약만 본다.
        day_appointments = await self.repo.find_appointments(doctor_id, start, end, patient_ids)
        if tab in TAB_STATUS:
            day_appointments = [a for a in day_appointments if a.status == TAB_STATUS[tab]]

        appointments: dict[int, Appointment] = {}
        for appointment in day_appointments:
            appointments.setdefault(appointment.patient_id, appointment)

        # 환자별 최고 등급 알림 (등급 높은 순 -> 최신순으로 오므로 처음 것이 대표)
        top_risks: dict[int, RiskEvent] = {}
        for event in await self.repo.find_risk_events(doctor_id, RiskEventStatus.OPEN, patient_ids):
            top_risks.setdefault(event.user_id, event)

        # 탭 필터: 그 상태인 예약이 있는 환자만
        if tab in TAB_STATUS:
            patients = [patient for patient in patients if patient.id in appointments]

        def sort_key(patient):
            risk = top_risks.get(patient.id)
            appointment = appointments.get(patient.id)
            return (
                -RISK_RANK.get(risk.level, 0) if risk else 0,
                -risk.created_at.timestamp() if risk else 0,
                appointment.scheduled_at.timestamp() if appointment else float("inf"),
                patient.id
            )

        result = []
        for patient in sorted(patients, key=sort_key):
            risk = top_risks.get(patient.id)
            appointment = appointments.get(patient.id)
            result.append(DoctorPatientResponseDTO(
                id=patient.id,
                name=patient.name,
                gender=patient.gender,
                birth_date=patient.birth_date,
                risk_level=risk.level if risk else None,
                appointment=PatientAppointmentDTO(
                    appointment_id=appointment.appointment_id,
                    scheduled_at=appointment.scheduled_at,
                    status=appointment.status
                ) if appointment else None
            ))

        return result


    # 4. 오늘 예약 일정
    # - 임의 결정 D-03 (결정-50 미정): 담당 환자의 예약만 보여 준다.
    async def get_appointments(self, doctor_id: int, day: date | None) -> list[DoctorAppointmentResponseDTO]:
        start, end = kst_day_range(day or today_kst())
        appointments = await self.repo.find_appointments(doctor_id, start, end)
        return [self._to_appointment_response(appointment) for appointment in appointments]


    # 5. 위험 환자 알림 목록
    async def get_risk_events(self, doctor_id: int, risk_status: RiskEventStatus) -> list[RiskEventResponseDTO]:
        events = await self.repo.find_risk_events(doctor_id, risk_status)
        return [self._to_risk_response(event) for event in events]


    # 6. 위험 알림 확인
    # - 없으면 404, 담당 환자가 아니면 403, 이미 확인한 알림이면 409
    async def review_risk_event(self, doctor_id: int, event_id: int) -> RiskEventResponseDTO:
        event = await self.repo.find_risk_event_by_id(event_id)
        if not event:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="위험 알림이 존재하지 않습니다."
            )

        await self._ensure_in_charge(doctor_id, event.user_id)

        if not await self.repo.review_risk_event(event_id, doctor_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="확인 전(open)·보류(on_hold) 알림만 확인할 수 있습니다."
            )

        reviewed_event = await self.repo.find_risk_event_by_id(event_id)
        return self._to_risk_response(reviewed_event)


    # 7. 월 캘린더 (month = "2026-11", 형식 검사는 라우터의 Query pattern이 한다)
    async def get_calendar(self, doctor_id: int, month: str | None) -> CalendarResponseDTO:
        month = month or today_kst().strftime("%Y-%m")

        year, mon = map(int, month.split("-"))
        first_day = date(year, mon, 1)
        next_first_day = date(year + mon // 12, mon % 12 + 1, 1)

        rows = await self.repo.count_appointments_by_day(
            doctor_id, kst_day_range(first_day)[0], kst_day_range(next_first_day)[0]
        )

        return CalendarResponseDTO(
            month=month,
            days=[
                CalendarDayDTO(date=day, treatment_count=treatment, psych_test_count=psych_test)
                for day, treatment, psych_test in rows
            ]
        )


    # ===== 2단계: 환자를 고르면 바뀌는 위젯 (담당 환자만) =====

    # 8. 경과 그래프 (의사-02·03)
    async def get_assessment_trend(
        self, doctor_id: int, patient_id: int, instrument: Instrument, months: int
    ) -> AssessmentTrendResponseDTO:
        await self._ensure_in_charge(doctor_id, patient_id)

        results = await self.repo.find_assessments(patient_id, instrument, months_ago_kst(months))
        points = [AssessmentPointDTO.model_validate(result) for result in results]

        return AssessmentTrendResponseDTO(
            patient_id=patient_id,
            instrument=instrument,
            months=months,
            points=points,
            latest=points[-1] if points else None,
            previous=points[-2] if len(points) >= 2 else None
        )


    # 9. AI 상담 기록 위젯 (의사-04·05)
    # - 임의 결정 D-04 (결정-39·40 미정): ERD에 일기 열람 동의를 저장할 곳이 없어 일기 탭은 열지 않는다(501).
    async def get_records(
        self, doctor_id: int, patient_id: int, tab: Literal["chat", "diary"], limit: int
    ) -> list[ChatRecordResponseDTO]:
        await self._ensure_in_charge(doctor_id, patient_id)

        if tab == "diary":
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="일기 탭은 아직 정해지지 않았습니다. (결정-39·40)"
            )

        sessions = await self.repo.find_chat_sessions(patient_id, limit)
        return [self._to_chat_record(session, has_risk) for session, has_risk in sessions]


    # ===== F-06 AI 상담 내역 팝업 (의사-04·05) =====

    # 10. 상담 세션 목록 (페이지)
    async def get_chat_sessions(
        self, doctor_id: int, patient_id: int, offset: int, limit: int
    ) -> PageResponseDTO[ChatRecordResponseDTO]:
        await self._ensure_in_charge(doctor_id, patient_id)

        sessions = await self.repo.find_chat_sessions(patient_id, limit, offset)
        total_count = await self.repo.count_chat_sessions(patient_id)

        return PageResponseDTO(
            total_count=total_count,
            total_pages=(total_count + limit - 1) // limit,
            offset=offset,
            limit=limit,
            items=[self._to_chat_record(session, has_risk) for session, has_risk in sessions]
        )


    # 11. 상담 세션 상세 (세션 정보, 요약·태그, 감정 변화, 대화 전문)
    # - 없으면 404, 담당 환자의 세션이 아니면 403
    async def get_chat_session_detail(self, doctor_id: int, session_id: int) -> ChatSessionDetailResponseDTO:
        session = await self.repo.find_chat_session_detail(session_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="상담 세션이 존재하지 않습니다."
            )

        await self._ensure_in_charge(doctor_id, session.user_id)

        # 메시지별 가장 높은 위험 등급
        risk_rows = await self.repo.find_message_risk_levels(session_id)
        risk_levels: dict[int, RiskEventLevel] = {}
        for message_id, level in risk_rows:
            if RISK_RANK[level] > RISK_RANK.get(risk_levels.get(message_id), 0):
                risk_levels[message_id] = level

        # 세션 전체 위험 신호: 알림 수(한 메시지에 알림 2건이면 2) + 가장 높은 등급
        max_risk_level = max(risk_levels.values(), key=lambda level: RISK_RANK[level], default=None)

        messages = []
        user_emotions: list[EmotionType] = []   # 감정 분석이 있는 환자 메시지의 dominant (대화 순서)
        for message in sorted(session.messages, key=lambda m: m.seq):
            # 임의 결정 D-05: 감정 분석이 여러 건이면 model_version이 가장 큰 1건 (ERD에 created_at 없음)
            analysis = max(message.emotion_analyses, key=lambda a: a.model_version or "", default=None)
            if analysis and message.role == MessageRole.USER:
                user_emotions.append(analysis.dominant)
            messages.append(ChatMessageResponseDTO(
                id=message.id,
                seq=message.seq,
                role=message.role,
                content=message.content,
                created_at=message.created_at,
                emotion=MessageEmotionDTO.model_validate(analysis) if analysis else None,
                risk_level=risk_levels.get(message.id)
            ))

        # 이전·다음 세션 (시작 전 세션은 기준 시각이 없어서 둘 다 없음, 임의 결정 D-42)
        prev_session, next_session = None, None
        if session.started_at is not None:
            prev_session, next_session = await self.repo.find_adjacent_sessions(
                session.user_id, session.session_type, session.started_at, session.id
            )

        return ChatSessionDetailResponseDTO(
            id=session.id,
            patient=DoctorPatientBriefDTO(id=session.user_id, name=session.user.name if session.user else None),
            session_type=session.session_type,
            status=session.status,
            end_reason=session.end_reason,
            started_at=session.started_at,
            ended_at=session.ended_at,
            summary_status=session.summary_status,
            summary=ChatSummaryDTO.model_validate(session.summary) if session.summary else None,
            messages=messages,
            session_code=session_code(session),
            duration_minutes=duration_minutes(session.started_at, session.ended_at),
            prev_session=ChatSessionBriefDTO.model_validate(prev_session) if prev_session else None,
            next_session=ChatSessionBriefDTO.model_validate(next_session) if next_session else None,
            input_type=input_type_of(session.messages),
            # TODO: 감정 변화를 메시지 감정 분석으로 볼지 session_summaries.mood_summary로 볼지 미정 -> 지금은 메시지 기준
            emotion_change=(
                EmotionChangeDTO(start=user_emotions[0], end=user_emotions[-1])
                if len(user_emotions) >= 2 else None
            ),
            risk_count=len(risk_rows),
            max_risk_level=max_risk_level,
            # 임의 결정 D-44: 턴 = 환자 발화 1 + AI 응답 1 -> 환자 메시지 수 (몇 턴을 펼칠지는 프론트)
            turn_count=sum(1 for m in session.messages if m.role == MessageRole.USER)
        )


    # ===== F-05 위험 감지 상세 팝업 (의사-06·07) =====

    # 없으면 404, 담당 환자가 아니면 403
    async def _get_my_risk_event(self, doctor_id: int, event_id: int):
        event = await self.repo.find_risk_event_detail(event_id)
        if not event:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="위험 알림이 존재하지 않습니다."
            )

        await self._ensure_in_charge(doctor_id, event.user_id)
        return event


    # 12. 환자별 감지 목록 (최근 days일)
    async def get_patient_risk_events(self, doctor_id: int, patient_id: int, days: int) -> list[RiskEventResponseDTO]:
        await self._ensure_in_charge(doctor_id, patient_id)

        since = kst_day_range(today_kst() - timedelta(days=days - 1))[0]
        events = await self.repo.find_patient_risk_events(patient_id, since)
        return [self._to_risk_response(event) for event in events]


    # 13. 감지 상세 (감지 정보, 대화 앞뒤 6개, 걸린 단어, 문맥 판단, 조치 이력)
    async def get_risk_event_detail(self, doctor_id: int, event_id: int) -> RiskEventDetailResponseDTO:
        event = await self._get_my_risk_event(doctor_id, event_id)

        messages = await self.repo.find_messages_around(event.message_id, CONTEXT_AROUND) if event.message_id else []

        actions = sorted(event.actions, key=lambda a: (a.created_at, a.id))
        names = await self.repo.find_user_names(
            {a.actor_id for a in actions if a.actor_type == RiskEventActionActorType.DOCTOR and a.actor_id}
        )

        # 출처 세션 번호 (대화에서 감지됐을 때만, 임의 결정 D-41)
        session = await self.repo.find_chat_session(messages[0].session_id) if messages else None

        # 지금 담당 의사 (임의 결정 D-47)
        # TODO: 담당 의사가 여러 명일 때 화면에 몇 명 보여 줄지 미정 -> 지금은 1명
        doctor_name = await self.repo.find_current_doctor_name(event.user_id)

        # 이전 유사 기록: 이 알림 전 30일 안, 같은 category(없으면 같은 origin) (임의 결정 D-48)
        # TODO: "유사 표현"을 category로 볼지 걸린 단어(matched_terms)가 겹치는 것으로 볼지 미정 -> 지금은 category
        similar = await self.repo.find_similar_risk_events(
            event.user_id, event.category, event.origin,
            since=event.created_at - timedelta(days=SIMILAR_RISK_DAYS), before=event.created_at, exclude_id=event.id
        )
        latest = similar[0] if similar else None

        return RiskEventDetailResponseDTO(
            id=event.id,
            patient=DoctorPatientBriefDTO(id=event.user_id, name=event.patient.name if event.patient else None),
            level=event.level,
            status=event.status,
            source=event.source,
            origin=event.origin,
            category=event.category,
            score=event.score,
            evidence=event.evidence,
            matched_terms=event.matched_terms,
            context_judgement=event.context_judgement,
            model_version=event.model_version,
            is_repeated=event.is_repeated,
            is_uncertain=event.is_uncertain,
            due_at=event.due_at,
            created_at=event.created_at,
            reviewed_at=event.reviewed_at,
            session_id=messages[0].session_id if messages else None,
            context=[
                RiskContextMessageDTO(
                    id=m.id, seq=m.seq, role=m.role, content=m.content, created_at=m.created_at,
                    is_trigger=(m.id == event.message_id)
                )
                for m in messages
            ],
            actions=[
                RiskEventActionResponseDTO(
                    id=a.id, actor_type=a.actor_type, actor_id=a.actor_id,
                    actor_name=names.get(a.actor_id) if a.actor_type == RiskEventActionActorType.DOCTOR else None,
                    action=a.action, memo=a.memo, created_at=a.created_at
                )
                for a in actions
            ],
            session_code=session_code(session) if session else None,
            doctor_name=doctor_name,
            similar_history=RiskSimilarHistoryDTO(
                count=len(similar),
                latest_id=latest.id if latest else None,
                latest_at=latest.created_at if latest else None,
                latest_evidence=latest.evidence if latest else None
            )
        )


    # 14. 조치 기록 추가 (note: 메모 / hold: 보류 / escalate: 위기 대응으로 올림)
    # - 지금 상태에서 할 수 없는 조치 -> 409 (hold는 open만, escalate는 escalated가 아닐 때만)
    async def add_risk_action(
        self, doctor_id: int, event_id: int, action: RiskEventActionCreateDTO
    ) -> RiskEventDetailResponseDTO:
        await self._get_my_risk_event(doctor_id, event_id)

        if not await self.repo.add_risk_action(event_id, doctor_id, action.action, action.memo):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"지금 상태에서는 {action.action.value} 조치를 할 수 없습니다."
            )

        return await self.get_risk_event_detail(doctor_id, event_id)


    # ===== F-04 감정 그래프 팝업 (의사-02·03, 결정-26 미정 -> 임의 결정 D-13) =====

    # 15. 감정 리포트 (요약 4칸, 일별 기분, 주별 감정 비율, 키워드, 시간대별 기록)
    # - 기분 점수·키워드·시간대: 환자가 직접 남기고 의사에게 공유한(is_shared) 감정 기록(emotion_records)
    # - 감정 비율·가장 많은 감정: AI 상담 대화의 감정 분석(emotion_analyses)
    # - 일기는 쓰지 않는다 (임의 결정 D-04)
    async def get_emotion_report(
        self, doctor_id: int, patient_id: int, period: Literal["week", "month", "3months"], start: date | None
    ) -> EmotionReportResponseDTO:
        await self._ensure_in_charge(doctor_id, patient_id)

        first_day, next_day = report_range(period, start)
        start_at, end_at = kst_day_range(first_day)[0], kst_day_range(next_day)[0]
        total_days = (next_day - first_day).days

        records = await self.repo.find_emotion_records(patient_id, first_day, next_day)
        emotions = await self.repo.find_message_emotions(patient_id, start_at, end_at)

        # 요약: 평균 기분, 직전 같은 길이 기간과의 차이
        prev_first_day = first_day - (next_day - first_day)
        avg = sum(r.mood_score for r in records) / len(records) if records else None
        prev_avg = await self.repo.avg_mood_score(patient_id, prev_first_day, first_day)
        emotion_counter = Counter(dominant for _, dominant in emotions)

        # 기쁨 감정 비율과 직전 같은 길이 기간과의 차이 (0.07이면 화면 "▲ 7%p")
        # TODO: "기쁨 감정" 칸을 기쁨으로 고정할지 가장 많은 감정(topEmotion)으로 바꿀지 미정 -> 화면대로 기쁨 고정
        prev_emotions = await self.repo.find_message_emotions(patient_id, kst_day_range(prev_first_day)[0], start_at)
        joy_ratio, prev_joy_ratio = joy_ratio_of(emotions), joy_ratio_of(prev_emotions)

        # 주별 감정 비율: 기간 첫날부터 7일씩 묶는다 (임의 결정 D-46, 화면 "10.15주 / 10.22주")
        # - 데이터가 없는 주도 total 0으로 넣어 화면 막대 수를 일정하게 한다.
        weeks: dict[date, Counter] = {
            first_day + timedelta(days=offset): Counter() for offset in range(0, total_days, 7)
        }
        for created_at, dominant in emotions:
            day = created_at.astimezone(KST).date()
            weeks[first_day + timedelta(days=7 * ((day - first_day).days // 7))][dominant] += 1

        # 시간대별 기록 수 (감정 기록을 남긴 시각)
        slot_counter = Counter(TIME_SLOTS[r.created_at.astimezone(KST).hour // 6] for r in records)

        # 진료일 표시: 기간 안 내가 진료를 마친 예약 + 그날(KST) 가장 늦은 PHQ-9
        # TODO: 다른 의사의 진료도 넣을지 미정 -> 지금은 내 진료만
        visits = await self.repo.find_completed_appointments(doctor_id, patient_id, start_at, end_at)
        phq9_by_day = {
            # 오래된 순으로 덮어쓰므로 날짜마다 가장 늦은 결과가 남는다.
            result.assessed_at.astimezone(KST).date(): result
            for result in await self.repo.find_assessments(patient_id, Instrument.PHQ9, start_at, end_at)
        }
        visit_markers = []
        for visit in visits:
            day = visit.scheduled_at.astimezone(KST).date()
            phq9 = phq9_by_day.get(day)
            visit_markers.append(VisitMarkerDTO(
                date=day,
                appointment_id=visit.appointment_id,
                phq9_score=phq9.total_score if phq9 else None,
                phq9_severity=phq9.severity if phq9 else None
            ))

        names = await self.repo.find_user_names({patient_id})

        # TODO: 하루에 감정 기록이 여러 건이면 일별 그래프 값을 어떻게 할지 미정 -> 지금처럼 기록을 그대로 내려 준다.
        return EmotionReportResponseDTO(
            patient_id=patient_id,
            patient=DoctorPatientBriefDTO(id=patient_id, name=names.get(patient_id)),
            period=period,
            start_date=first_day,
            end_date=next_day - timedelta(days=1),
            summary=EmotionSummaryDTO(
                avg_mood_score=round(avg, 2) if avg is not None else None,
                mood_change=round(avg - prev_avg, 2) if avg is not None and prev_avg is not None else None,
                recorded_days=len({r.record_date for r in records}),
                total_days=total_days,
                top_emotion=emotion_counter.most_common(1)[0][0] if emotion_counter else None,
                joy_ratio=joy_ratio,
                joy_change=round(joy_ratio - prev_joy_ratio, 3) if joy_ratio is not None and prev_joy_ratio is not None else None
            ),
            daily_moods=[
                DailyMoodDTO(date=r.record_date, mood_score=r.mood_score, mood_tag=r.mood_tag)
                for r in records
            ],
            weekly_emotions=[
                WeeklyEmotionDTO(
                    week_start=week_start,
                    total=sum(counter.values()),
                    ratios={
                        e: round(counter[e] / sum(counter.values()), 3) if counter else 0.0
                        for e in EmotionType
                    }
                )
                for week_start, counter in sorted(weeks.items())
            ],
            keywords=[
                EmotionKeywordDTO(keyword=tag, count=count)
                for tag, count in Counter(r.mood_tag.strip() for r in records if r.mood_tag and r.mood_tag.strip()).most_common(10)
            ],
            time_slots=[TimeSlotCountDTO(slot=slot, count=slot_counter[slot]) for slot in TIME_SLOTS],
            visit_markers=visit_markers
        )


    # ===== F-03 설문조사 결과 팝업 =====

    # 16. 사전 문진 결과 (문진 정보, 척도 점수, 문항별 응답, 주호소, AI 소견)
    # - session_id가 없으면 가장 최근 문진 (임의 결정 D-18)
    # - 그 환자의 문진이 아니거나 없으면 404
    async def get_intake_result(self, doctor_id: int, patient_id: int, session_id: int | None) -> IntakeResultResponseDTO:
        await self._ensure_in_charge(doctor_id, patient_id)

        session = await self.repo.find_intake_session(patient_id, session_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="사전 문진 결과가 없습니다."
            )

        # 척도별 마지막 결과 (오래된 순으로 오므로 뒤의 것이 덮어쓴다) - 임의 결정 D-19
        # - 결과가 없는 카드도 만점은 넣는다.
        latest = {result.instrument: result for result in await self.repo.find_session_assessments(session.id)}
        scores = []
        for instrument in INTAKE_INSTRUMENTS:
            result = latest.get(instrument)
            scores.append(IntakeScoreDTO(
                instrument=instrument,
                total_score=result.total_score if result else None,
                severity=result.severity if result else None,
                assessed_at=result.assessed_at if result else None,
                max_score=INSTRUMENT_MAX_SCORE[instrument]
            ))

        # 문항 순서: sort_order -> 척도 문항 번호 -> id (값이 없으면 뒤로)
        checklists = sorted(
            session.checklists,
            key=lambda c: (c.sort_order is None, c.sort_order or 0, c.item.item_no is None, c.item.item_no or 0, c.id)
        )
        answers = [
            IntakeAnswerDTO(
                item_key=c.item.item_key,
                label=c.item.label,
                instrument=c.item.instrument,
                item_no=c.item.item_no,
                answer_type=c.item.answer_type,
                options=c.item.options,
                required=c.required,
                status=c.status,
                skip_reason=c.skip_reason,
                value=c.value,
                score=answer_score(c.item.instrument, c.status, c.value)
            )
            for c in checklists
        ]

        # 응답률: 필수 문항 중 done 비율 (반올림, 필수 문항이 없으면 100) - 임의 결정 D-49
        required = [c for c in checklists if c.required]
        done_count = sum(1 for c in required if c.status == ChecklistStatus.DONE)
        completion_rate = round(done_count * 100 / len(required)) if required else 100

        # 부제 환자 정보: 이름·성별·만 나이·내 병원 차트번호 (환자 row 1번만 조회)
        user = await self.repo.find_patient_info(patient_id)
        profile = await self.repo.find_doctor_profile(doctor_id)
        chart_no = await self.repo.find_chart_no(patient_id, profile.hospital_id) if profile else None

        summary = session.summary
        history = await self.repo.find_intake_sessions(patient_id, INTAKE_HISTORY_LIMIT)

        return IntakeResultResponseDTO(
            patient=DoctorPatientBriefDTO(id=patient_id, name=user.name if user else None),
            session_id=session.id,
            status=session.status,
            started_at=session.started_at,
            ended_at=session.ended_at,
            scores=scores,
            answers=answers,
            chief_complaint=summary.chief_complaint if summary else None,
            findings=summary.findings if summary else None,
            context_summary=summary.context_summary if summary else None,
            history=[IntakeSessionBriefDTO.model_validate(s) for s in history],
            patient_info=IntakePatientInfoDTO(
                gender=user.gender if user else None,
                birth_date=user.birth_date if user else None,
                age=age_of(user.birth_date) if user else None,
                chart_no=chart_no
            ),
            input_type=input_type_of(session.messages),
            duration_minutes=duration_minutes(session.started_at, session.ended_at),
            completion_rate=completion_rate
            # TODO: 주 호소 아래 환자 인용 문장 - session_summaries에 칸이 없어서 이번에는 내려 주지 않는다.
            # TODO: "AI 참고 소견" 라벨 색(파랑·회색·초록) 기준 - findings에 구분 값이 없어서 프론트에서 정한다.
        )


    # ===== F-07 예약 일정 팝업 =====

    # ORM -> 예약 1건 DTO (변경 이력 포함)
    def _to_appointment_detail(self, appointment: Appointment) -> AppointmentDetailResponseDTO:
        return AppointmentDetailResponseDTO(
            **self._to_appointment_response(appointment).model_dump(),
            tests=appointment.tests,
            patient_note=appointment.patient_note,
            completed_at=appointment.completed_at,
            changes=[
                AppointmentChangeResponseDTO.model_validate(change)
                for change in sorted(appointment.changes, key=lambda c: (c.created_at, c.id))
            ]
        )


    # 내 예약인지 확인 - 없으면 404, 내 예약이 아니거나 담당 환자가 아니면 403 (임의 결정 D-21)
    async def _get_my_appointment(self, doctor_id: int, appointment_id: int) -> Appointment:
        appointment = await self.repo.find_appointment(appointment_id)
        if not appointment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="예약이 존재하지 않습니다."
            )

        if appointment.doctor_id != doctor_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="내 예약만 바꿀 수 있습니다."
            )

        await self._ensure_in_charge(doctor_id, appointment.patient_id)
        return appointment


    # 시간 확인: 끝이 시작보다 뒤, 시작이 지금보다 뒤(임의 결정 D-24), 다른 예약과 안 겹침(D-23)
    async def _check_time(
        self, doctor_id: int, room_id: int | None, start: datetime, end: datetime, exclude_id: int | None = None
    ) -> None:
        if end <= start:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="끝 시각은 시작 시각보다 뒤여야 합니다."
            )

        if start <= datetime.now(KST):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="지난 시각으로는 예약할 수 없습니다."
            )

        if await self.repo.exists_overlap(doctor_id, room_id, start, end, exclude_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="같은 시간에 다른 예약이 있습니다."
            )


    # 17. 환자별 예약 (월) + 변경·취소·노쇼 횟수 (임의 결정 D-28)
    async def get_patient_appointments(
        self, doctor_id: int, patient_id: int, month: str | None
    ) -> PatientAppointmentsResponseDTO:
        await self._ensure_in_charge(doctor_id, patient_id)

        month = month or today_kst().strftime("%Y-%m")
        first_day = date(*map(int, month.split("-")), 1)
        start, end = kst_day_range(first_day)[0], kst_day_range(add_months(first_day, 1))[0]

        appointments = await self.repo.find_patient_appointments(doctor_id, patient_id, start, end)
        reschedule_count, cancel_count, no_show_count = await self.repo.count_patient_appointment_stats(doctor_id, patient_id)
        names = await self.repo.find_user_names({patient_id})

        # 다음 예약 (month와 상관없이 지금 이후 가장 이른 1건)
        next_appointment = await self.repo.find_next_appointment(doctor_id, patient_id, datetime.now(KST))

        return PatientAppointmentsResponseDTO(
            patient=DoctorPatientBriefDTO(id=patient_id, name=names.get(patient_id)),
            month=month,
            reschedule_count=reschedule_count,
            cancel_count=cancel_count,
            no_show_count=no_show_count,
            items=[self._to_appointment_detail(appointment) for appointment in appointments],
            next_appointment=self._to_next_appointment(next_appointment)
        )


    # ORM -> 다음 예약 DTO (D-day는 KST 날짜끼리 뺀다: 오늘 23시 예약도 D-0)
    def _to_next_appointment(self, appointment: Appointment | None) -> NextAppointmentDTO | None:
        if appointment is None:
            return None

        return NextAppointmentDTO(
            appointment_id=appointment.appointment_id,
            scheduled_at=appointment.scheduled_at,
            d_day=(appointment.scheduled_at.astimezone(KST).date() - today_kst()).days
        )


    # 18. 예약 추가 (+ 환자·의사 캘린더 일정)
    async def create_appointment(self, doctor_id: int, request: AppointmentCreateDTO) -> AppointmentDetailResponseDTO:
        await self._ensure_in_charge(doctor_id, request.patient_id)

        profile = await self.repo.find_doctor_profile(doctor_id)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="의사 프로필이 없습니다."
            )

        # 진료실은 내 병원의 사용 중인 방만
        if request.room_id is not None:
            room = await self.repo.find_room(request.room_id)
            if not room or room.hospital_id != profile.hospital_id or not room.is_active:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="사용할 수 없는 진료실입니다."
                )

        start = request.scheduled_at
        end = request.end_at or start + timedelta(minutes=DEFAULT_APPOINTMENT_MINUTES)
        await self._check_time(doctor_id, request.room_id, start, end)

        visited = await self.repo.has_completed_visit(request.patient_id, profile.hospital_id)
        schedule_type, title = SCHEDULE_BY_KIND[request.kind]

        appointment_id = await self.repo.create_appointment(
            {
                "patient_id": request.patient_id,
                "doctor_id": doctor_id,
                "hospital_id": profile.hospital_id,
                "scheduled_at": start,
                "end_at": end,
                "status": AppointmentStatus.BOOKED,
                "kind": request.kind,
                "contact_method": request.contact_method,
                "tests": request.tests,
                "visit_type": AppointmentVisitType.RETURN if visited else AppointmentVisitType.FIRST,
                "room_id": request.room_id,
                "booking_source": AppointmentBookingSource.DOCTOR,
                "created_by": doctor_id
            },
            schedule_type,
            title
        )

        return self._to_appointment_detail(await self.repo.find_appointment(appointment_id))


    # 19. 일정 변경 (끝 시각을 안 보내면 원래 길이 유지)
    async def reschedule_appointment(
        self, doctor_id: int, appointment_id: int, request: AppointmentRescheduleDTO
    ) -> AppointmentDetailResponseDTO:
        appointment = await self._get_my_appointment(doctor_id, appointment_id)

        if appointment.status not in CHANGEABLE_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="예약됨·대기 중인 예약만 일정을 바꿀 수 있습니다."
            )

        old_start = appointment.scheduled_at
        duration = (appointment.end_at - old_start) if appointment.end_at else timedelta(minutes=DEFAULT_APPOINTMENT_MINUTES)
        start = request.scheduled_at
        end = request.end_at or start + duration
        await self._check_time(doctor_id, appointment.room_id, start, end, exclude_id=appointment_id)

        if not await self.repo.reschedule_appointment(appointment_id, doctor_id, old_start, start, end, request.reason):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="예약됨·대기 중인 예약만 일정을 바꿀 수 있습니다."
            )

        return self._to_appointment_detail(await self.repo.find_appointment(appointment_id))


    # 20. 예약 취소 (+ 캘린더 일정 삭제)
    async def cancel_appointment(
        self, doctor_id: int, appointment_id: int, request: AppointmentCancelDTO
    ) -> AppointmentDetailResponseDTO:
        appointment = await self._get_my_appointment(doctor_id, appointment_id)

        if not await self.repo.cancel_appointment(appointment_id, doctor_id, appointment.scheduled_at, request.reason):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="예약됨·대기 중인 예약만 취소할 수 있습니다."
            )

        return self._to_appointment_detail(await self.repo.find_appointment(appointment_id))


    # 21. 진료 상태 변경 (STATUS_ALLOWED_FROM 순서만 허용, 아니면 409)
    async def update_appointment_status(
        self, doctor_id: int, appointment_id: int, request: AppointmentStatusUpdateDTO
    ) -> AppointmentDetailResponseDTO:
        await self._get_my_appointment(doctor_id, appointment_id)

        if not await self.repo.update_appointment_status(
            appointment_id, STATUS_ALLOWED_FROM[request.status], request.status
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"지금 상태에서는 {request.status.value}(으)로 바꿀 수 없습니다."
            )

        return self._to_appointment_detail(await self.repo.find_appointment(appointment_id))



# 레포지토리 주입 팩토리 함수
def get_doctor_service(repo: DoctorRepository = Depends(get_doctor_repository)):
    return DoctorService(repo)
