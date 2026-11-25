from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal
from fastapi import Depends, HTTPException, status
from app.repository.doctor_repository import DoctorRepository, get_doctor_repository
from app.enums.appointment_enum import AppointmentStatus, AppointmentKind, AppointmentVisitType, AppointmentBookingSource
from app.enums.schedule_enum import ScheduleType
from app.enums.risk_event_enum import RiskEventLevel, RiskEventStatus
from app.enums.risk_event_action_enum import RiskEventActionActorType
from app.enums.common_enum import Instrument, EmotionType
from app.models.risk_event_model import RiskEvent
from app.models.appointment_model import Appointment
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
    ChatSummaryDTO,
    ChatMessageResponseDTO,
    MessageEmotionDTO,
    RiskEventDetailResponseDTO,
    RiskContextMessageDTO,
    RiskEventActionResponseDTO,
    RiskEventActionCreateDTO,
    EmotionReportResponseDTO,
    EmotionSummaryDTO,
    DailyMoodDTO,
    WeeklyEmotionDTO,
    EmotionKeywordDTO,
    TimeSlotCountDTO,
    IntakeResultResponseDTO,
    IntakeScoreDTO,
    IntakeAnswerDTO,
    IntakeSessionBriefDTO,
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
# - 임의 결정 D-17: from이 없으면 오늘로 끝나는 기간. week=7일, month=1개월, 3months=3개월
PERIOD_MONTHS = {"month": 1, "3months": 3}

def report_range(period: str, start: date | None) -> tuple[date, date]:
    if start is None:
        end = today_kst() + timedelta(days=1)
        start = end - timedelta(days=7) if period == "week" else add_months(end, -PERIOD_MONTHS[period])
        return start, end

    end = start + timedelta(days=7) if period == "week" else add_months(start, PERIOD_MONTHS[period])
    return start, end


# 설문 결과 팝업의 척도 카드 3장 (API 명세 F-03: phq9·gad7·isi)
INTAKE_INSTRUMENTS = (Instrument.PHQ9, Instrument.GAD7, Instrument.ISI)

# 설문 결과 팝업의 문진 목록 개수
INTAKE_HISTORY_LIMIT = 10


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
        risk_levels: dict[int, RiskEventLevel] = {}
        for message_id, level in await self.repo.find_message_risk_levels(session_id):
            if RISK_RANK[level] > RISK_RANK.get(risk_levels.get(message_id), 0):
                risk_levels[message_id] = level

        messages = []
        for message in sorted(session.messages, key=lambda m: m.seq):
            # 임의 결정 D-05: 감정 분석이 여러 건이면 model_version이 가장 큰 1건 (ERD에 created_at 없음)
            analysis = max(message.emotion_analyses, key=lambda a: a.model_version or "", default=None)
            messages.append(ChatMessageResponseDTO(
                id=message.id,
                seq=message.seq,
                role=message.role,
                content=message.content,
                created_at=message.created_at,
                emotion=MessageEmotionDTO.model_validate(analysis) if analysis else None,
                risk_level=risk_levels.get(message.id)
            ))

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
            messages=messages
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
            ]
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
        avg = sum(r.mood_score for r in records) / len(records) if records else None
        prev_avg = await self.repo.avg_mood_score(patient_id, first_day - (next_day - first_day), first_day)
        emotion_counter = Counter(dominant for _, dominant in emotions)

        # 주별 감정 비율 (월요일 시작)
        weeks: dict[date, Counter] = {}
        for created_at, dominant in emotions:
            day = created_at.astimezone(KST).date()
            weeks.setdefault(day - timedelta(days=day.weekday()), Counter())[dominant] += 1

        # 시간대별 기록 수 (감정 기록을 남긴 시각)
        slot_counter = Counter(TIME_SLOTS[r.created_at.astimezone(KST).hour // 6] for r in records)

        return EmotionReportResponseDTO(
            patient_id=patient_id,
            period=period,
            start_date=first_day,
            end_date=next_day - timedelta(days=1),
            summary=EmotionSummaryDTO(
                avg_mood_score=round(avg, 2) if avg is not None else None,
                mood_change=round(avg - prev_avg, 2) if avg is not None and prev_avg is not None else None,
                recorded_days=len({r.record_date for r in records}),
                total_days=total_days,
                top_emotion=emotion_counter.most_common(1)[0][0] if emotion_counter else None
            ),
            daily_moods=[
                DailyMoodDTO(date=r.record_date, mood_score=r.mood_score, mood_tag=r.mood_tag)
                for r in records
            ],
            weekly_emotions=[
                WeeklyEmotionDTO(
                    week_start=week_start,
                    total=sum(counter.values()),
                    ratios={e: round(counter[e] / sum(counter.values()), 3) for e in EmotionType}
                )
                for week_start, counter in sorted(weeks.items())
            ],
            keywords=[
                EmotionKeywordDTO(keyword=tag, count=count)
                for tag, count in Counter(r.mood_tag.strip() for r in records if r.mood_tag and r.mood_tag.strip()).most_common(10)
            ],
            time_slots=[TimeSlotCountDTO(slot=slot, count=slot_counter[slot]) for slot in TIME_SLOTS]
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

        patient = await self.repo.find_user_names({patient_id})

        # 척도별 마지막 결과 (오래된 순으로 오므로 뒤의 것이 덮어쓴다) - 임의 결정 D-19
        latest = {result.instrument: result for result in await self.repo.find_session_assessments(session.id)}
        scores = [
            IntakeScoreDTO.model_validate(latest[instrument]) if instrument in latest else IntakeScoreDTO(instrument=instrument)
            for instrument in INTAKE_INSTRUMENTS
        ]

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
                value=c.value
            )
            for c in checklists
        ]

        summary = session.summary
        history = await self.repo.find_intake_sessions(patient_id, INTAKE_HISTORY_LIMIT)

        return IntakeResultResponseDTO(
            patient=DoctorPatientBriefDTO(id=patient_id, name=patient.get(patient_id)),
            session_id=session.id,
            status=session.status,
            started_at=session.started_at,
            ended_at=session.ended_at,
            scores=scores,
            answers=answers,
            chief_complaint=summary.chief_complaint if summary else None,
            findings=summary.findings if summary else None,
            context_summary=summary.context_summary if summary else None,
            history=[IntakeSessionBriefDTO.model_validate(s) for s in history]
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
