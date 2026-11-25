from datetime import date, datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.infrastructure.postgresql import get_postgresql_db
from fastapi import Depends

# 모델, ORM
from app.models.user_model import User
from app.models.care_relation_model import CareRelation
from app.models.doctor_profile_model import DoctorProfile
from app.models.room_model import Room
from app.models.appointment_model import Appointment
from app.models.risk_event_model import RiskEvent
from app.models.risk_event_action_model import RiskEventAction
from app.models.assessment_result_model import AssessmentResult
from app.models.chat_session_model import ChatSession
from app.models.message_model import Message
from app.models.emotion_record_model import EmotionRecord
from app.models.emotion_analysis_model import EmotionAnalysis
from app.models.session_checklist_model import SessionChecklist
from app.models.appointment_change_model import AppointmentChange
from app.models.schedule_model import Schedule
from app.enums.appointment_enum import AppointmentStatus, AppointmentKind
from app.enums.appointment_change_enum import AppointmentChangeType
from app.enums.common_enum import Instrument, RequestedBy
from app.enums.schedule_enum import ScheduleType
from app.enums.risk_event_enum import RiskEventLevel, RiskEventStatus
from app.enums.risk_event_action_enum import RiskEventActionActorType, RiskEventActionAction
from app.enums.chat_session_enum import ChatSessionType
from app.enums.message_enum import MessageRole
from sqlalchemy import select, update, insert, delete, func, case, exists, or_

KST = timezone(timedelta(hours=9)) # UTC+9

# 위험 등급 정렬용 (high가 가장 위)
RISK_LEVEL_ORDER = case(
    (RiskEvent.level == RiskEventLevel.HIGH, 3),
    (RiskEvent.level == RiskEventLevel.MEDIUM, 2),
    (RiskEvent.level == RiskEventLevel.LOW, 1),
    else_=0
)


# 의사 조치 -> (바뀔 상태, 바꿀 수 있는 지금 상태)  (임의 결정 D-07·D-08, 팀 enum의 on_hold·hold 반영)
# - review: 확인 / hold: 보류 / escalate: 위기 대응으로 올림 / note: 메모만 (상태 그대로)
RISK_TRANSITIONS = {
    RiskEventActionAction.REVIEW: (RiskEventStatus.REVIEWED, (RiskEventStatus.OPEN, RiskEventStatus.ON_HOLD)),
    RiskEventActionAction.HOLD: (RiskEventStatus.ON_HOLD, (RiskEventStatus.OPEN,)),
    RiskEventActionAction.ESCALATE: (
        RiskEventStatus.ESCALATED, (RiskEventStatus.OPEN, RiskEventStatus.REVIEWED, RiskEventStatus.ON_HOLD)
    ),
}


# 내가 지금 담당 중인 환자 id 서브쿼리 (담당이 끝난 관계 제외)
# - 목록 API는 모두 이 서브쿼리로 "담당 환자만" 걸러낸다. (보안-02, 공통-04)
def care_patient_ids(doctor_id: int):
    return (
        select(CareRelation.patient_id)
        .where(
            CareRelation.doctor_id == doctor_id,
            CareRelation.ended_at.is_(None)
        )
    )


class DoctorRepository:

    # 생성자 주입
    def __init__(self, db: AsyncSession):
        self.db = db


    # 1. 담당 관계 확인
    async def exists_care_relation(self, doctor_id: int, patient_id: int) -> bool:
        query = care_patient_ids(doctor_id).where(CareRelation.patient_id == patient_id).limit(1)
        result = await self.db.execute(query)
        return result.scalar_one_or_none() is not None


    # 2. 의사 프로필 (소속 병원 확인용)
    async def find_doctor_profile(self, doctor_id: int) -> DoctorProfile | None:
        result = await self.db.execute(
            select(DoctorProfile).where(DoctorProfile.user_id == doctor_id)
        )
        return result.scalar_one_or_none()


    # 3. 그날 내 예약 개수 (취소 제외, 완료, 대기)
    # - filter(): 조건별 count를 쿼리 1번으로 센다.
    async def count_appointments_by_status(self, doctor_id: int, start: datetime, end: datetime) -> tuple[int, int, int]:
        query = (
            select(
                func.count().filter(Appointment.status != AppointmentStatus.CANCELLED),
                func.count().filter(Appointment.status == AppointmentStatus.COMPLETED),
                func.count().filter(Appointment.status == AppointmentStatus.WAITING)
            )
            .where(
                Appointment.doctor_id == doctor_id,
                Appointment.patient_id.in_(care_patient_ids(doctor_id)),
                Appointment.scheduled_at >= start,
                Appointment.scheduled_at < end
            )
        )

        result = await self.db.execute(query)
        today_count, completed_count, waiting_count = result.one()
        return today_count, completed_count, waiting_count


    # 4. 확인 안 한 위험 알림 개수 (담당 환자)
    async def count_open_risk_events(self, doctor_id: int) -> int:
        query = (
            select(func.count(RiskEvent.id))
            .where(
                RiskEvent.status == RiskEventStatus.OPEN,
                RiskEvent.user_id.in_(care_patient_ids(doctor_id))
            )
        )

        result = await self.db.execute(query)
        return result.scalar_one()


    # 5. 소속 병원의 사용 중인 진료실
    async def find_active_rooms(self, hospital_id: int) -> list[Room]:
        query = (
            select(Room)
            .where(
                Room.hospital_id == hospital_id,
                Room.is_active.is_(True)
            )
            .order_by(Room.id)
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())


    # 6. 담당 환자 (이름 검색, 탈퇴 회원 제외)
    async def find_care_patients(self, doctor_id: int, q: str | None) -> list[User]:
        query = (
            select(User)
            .where(
                User.id.in_(care_patient_ids(doctor_id)),
                User.deleted_at.is_(None)
            )
        )

        if q:
            query = query.where(User.name.ilike(f"%{q}%"))

        result = await self.db.execute(query)
        return list(result.scalars().all())


    # 7. 그날 내 예약 (취소 제외, 시각순)
    # - patient_ids를 주면 그 환자들 것만
    # - 환자 이름이 필요하므로 patient 관계를 selectinload로 미리 불러온다.
    async def find_appointments(
        self, doctor_id: int, start: datetime, end: datetime, patient_ids: list[int] | None = None
    ) -> list[Appointment]:
        query = (
            select(Appointment)
            .options(selectinload(Appointment.patient))
            .where(
                Appointment.doctor_id == doctor_id,
                Appointment.patient_id.in_(care_patient_ids(doctor_id)),
                Appointment.status != AppointmentStatus.CANCELLED,
                Appointment.scheduled_at >= start,
                Appointment.scheduled_at < end
            )
            .order_by(Appointment.scheduled_at, Appointment.appointment_id)
        )

        if patient_ids is not None:
            query = query.where(Appointment.patient_id.in_(patient_ids))

        result = await self.db.execute(query)
        return list(result.scalars().all())


    # 8. 위험 알림 목록 (담당 환자, 등급 높은 순 -> 최신순)
    # - patient_ids를 주면 그 환자들 것만
    async def find_risk_events(
        self, doctor_id: int, status: RiskEventStatus, patient_ids: list[int] | None = None
    ) -> list[RiskEvent]:
        query = (
            select(RiskEvent)
            .options(selectinload(RiskEvent.patient))
            .where(
                RiskEvent.status == status,
                RiskEvent.user_id.in_(care_patient_ids(doctor_id))
            )
            .order_by(RISK_LEVEL_ORDER.desc(), RiskEvent.created_at.desc(), RiskEvent.id.desc())
        )

        if patient_ids is not None:
            query = query.where(RiskEvent.user_id.in_(patient_ids))

        result = await self.db.execute(query)
        return list(result.scalars().all())


    # 9. 위험 알림 1건
    # - populate_existing: 확인 처리 직후 다시 조회할 때 DB 값으로 덮어쓴다.
    async def find_risk_event_by_id(self, event_id: int) -> RiskEvent | None:
        query = (
            select(RiskEvent)
            .options(selectinload(RiskEvent.patient))
            .where(RiskEvent.id == event_id)
            .execution_options(populate_existing=True)
        )

        result = await self.db.execute(query)
        return result.scalar_one_or_none()


    # 10. 위험 알림 확인 처리 + 조치 이력 1건 (한 트랜잭션)
    # - open·on_hold인 경우에만 바꾼다. 동시에 두 번 눌러도 1번만 성공한다.
    # - 조치 이력은 추가만 한다. (판단-13·14: 수정·삭제 없음)
    async def review_risk_event(self, event_id: int, doctor_id: int) -> bool:
        return await self.add_risk_action(event_id, doctor_id, RiskEventActionAction.REVIEW, None)


    # 위험 알림 상태 변경 (RISK_TRANSITIONS 규칙, 지금 상태가 맞을 때만) -> 바뀌었으면 True
    async def _change_risk_status(self, event_id: int, doctor_id: int, action: RiskEventActionAction, now: datetime) -> bool:
        to_status, from_statuses = RISK_TRANSITIONS[action]
        result = await self.db.execute(
            update(RiskEvent)
            .where(
                RiskEvent.id == event_id,
                RiskEvent.status.in_(from_statuses)
            )
            .values(status=to_status, reviewed_by=doctor_id, reviewed_at=now)
        )
        return result.rowcount > 0


    # 11. 월 캘린더: 날짜(KST)별 진료·검사 개수 (취소 제외)
    async def count_appointments_by_day(self, doctor_id: int, start: datetime, end: datetime) -> list[tuple]:
        day = func.date(func.timezone("Asia/Seoul", Appointment.scheduled_at))
        query = (
            select(
                day,
                func.count().filter(Appointment.kind == AppointmentKind.TREATMENT),
                func.count().filter(Appointment.kind == AppointmentKind.PSYCH_TEST)
            )
            .where(
                Appointment.doctor_id == doctor_id,
                Appointment.patient_id.in_(care_patient_ids(doctor_id)),
                Appointment.status != AppointmentStatus.CANCELLED,
                Appointment.scheduled_at >= start,
                Appointment.scheduled_at < end
            )
            .group_by(day)
            .order_by(day)
        )

        result = await self.db.execute(query)
        return list(result.all())


    # ===== 2단계: 환자를 고르면 바뀌는 위젯 =====

    # 12. 척도 결과 (기간 안, 오래된 순 -> 그래프 x축 순서)
    async def find_assessments(self, patient_id: int, instrument: Instrument, since: datetime) -> list[AssessmentResult]:
        query = (
            select(AssessmentResult)
            .where(
                AssessmentResult.user_id == patient_id,
                AssessmentResult.instrument == instrument,
                AssessmentResult.assessed_at >= since
            )
            .order_by(AssessmentResult.assessed_at, AssessmentResult.id)
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())


    # 13. 실제로 시작된 상담 세션 (최신순) + 세션마다 위험 감지 여부
    # - has_risk: 이 세션의 메시지 중 risk_events.message_id로 걸린 것이 있으면 true
    #   (risk_events.origin_id는 String(36)이라 세션 id와 바로 비교하지 않는다)
    # - 요약 미리보기가 필요하므로 summary 관계를 selectinload로 미리 불러온다.
    # - 위젯(최근 4개)과 상담 내역 팝업 목록(offset·limit)이 같이 쓴다.
    async def find_chat_sessions(self, patient_id: int, limit: int, offset: int = 0) -> list[tuple[ChatSession, bool]]:
        has_risk = (
            exists()
            .where(
                Message.session_id == ChatSession.id,
                RiskEvent.message_id == Message.id
            )
            .label("has_risk")
        )

        query = (
            select(ChatSession, has_risk)
            .options(selectinload(ChatSession.summary))
            .where(
                ChatSession.user_id == patient_id,
                ChatSession.started_at.is_not(None)
            )
            .order_by(ChatSession.started_at.desc(), ChatSession.id.desc())
            .offset(offset)
            .limit(limit)
        )

        result = await self.db.execute(query)
        return [(session, risk) for session, risk in result.all()]


    # 14. 실제로 시작된 상담 세션 개수 (팝업 목록 totalCount)
    async def count_chat_sessions(self, patient_id: int) -> int:
        query = (
            select(func.count(ChatSession.id))
            .where(
                ChatSession.user_id == patient_id,
                ChatSession.started_at.is_not(None)
            )
        )

        result = await self.db.execute(query)
        return result.scalar_one()


    # 15. 상담 세션 1건 + 환자, 요약, 메시지, 메시지별 감정 분석
    # - 비동기라 관계를 모두 selectinload로 미리 불러온다. (메시지 -> 감정 분석은 체인으로)
    async def find_chat_session_detail(self, session_id: int) -> ChatSession | None:
        query = (
            select(ChatSession)
            .options(
                selectinload(ChatSession.user),
                selectinload(ChatSession.summary),
                selectinload(ChatSession.messages).selectinload(Message.emotion_analyses)
            )
            .where(ChatSession.id == session_id)
        )

        result = await self.db.execute(query)
        return result.scalar_one_or_none()


    # 16. 세션 안 메시지별 위험 등급 -> [(message_id, level), ...]
    async def find_message_risk_levels(self, session_id: int) -> list[tuple]:
        query = (
            select(RiskEvent.message_id, RiskEvent.level)
            .join(Message, RiskEvent.message_id == Message.id)
            .where(Message.session_id == session_id)
        )

        result = await self.db.execute(query)
        return list(result.all())


    # ===== F-05 위험 감지 상세 팝업 =====

    # 17. 환자별 감지 목록 (since 이후, 최신순)
    async def find_patient_risk_events(self, patient_id: int, since: datetime) -> list[RiskEvent]:
        query = (
            select(RiskEvent)
            .options(selectinload(RiskEvent.patient))
            .where(
                RiskEvent.user_id == patient_id,
                RiskEvent.created_at >= since
            )
            .order_by(RiskEvent.created_at.desc(), RiskEvent.id.desc())
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())


    # 18. 감지 1건 + 환자 + 조치 이력
    # - populate_existing: 조치 추가 직후 다시 조회할 때 DB 값으로 덮어쓴다.
    async def find_risk_event_detail(self, event_id: int) -> RiskEvent | None:
        query = (
            select(RiskEvent)
            .options(selectinload(RiskEvent.patient), selectinload(RiskEvent.actions))
            .where(RiskEvent.id == event_id)
            .execution_options(populate_existing=True)
        )

        result = await self.db.execute(query)
        return result.scalar_one_or_none()


    # 19. 메시지 앞뒤 대화 (같은 세션에서 seq ± around)
    async def find_messages_around(self, message_id: int, around: int) -> list[Message]:
        target = (await self.db.execute(select(Message).where(Message.id == message_id))).scalar_one_or_none()
        if not target:
            return []

        query = (
            select(Message)
            .where(
                Message.session_id == target.session_id,
                Message.seq.between(target.seq - around, target.seq + around)
            )
            .order_by(Message.seq)
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())


    # 20. id -> 이름 (조치한 의사 이름 표시용)
    async def find_user_names(self, user_ids: set[int]) -> dict[int, str | None]:
        if not user_ids:
            return {}

        result = await self.db.execute(select(User.id, User.name).where(User.id.in_(user_ids)))
        return {user_id: name for user_id, name in result.all()}


    # 21. 의사 조치 기록 추가 (review·hold·escalate는 상태도 바꾼다, note는 이력만)
    # - 지금 상태에서 그 조치를 할 수 없으면 아무것도 하지 않고 False (동시에 눌러도 1번만)
    # - 조치 이력은 추가만 한다. (판단-13·14: 수정·삭제 없음)
    async def add_risk_action(self, event_id: int, doctor_id: int, action: RiskEventActionAction, memo: str | None) -> bool:
        now = datetime.now(KST)

        if action in RISK_TRANSITIONS and not await self._change_risk_status(event_id, doctor_id, action, now):
            await self.db.rollback()
            return False

        await self.db.execute(
            insert(RiskEventAction).values(
                risk_event_id=event_id,
                actor_type=RiskEventActionActorType.DOCTOR,
                actor_id=doctor_id,
                action=action,
                memo=memo,
                created_at=now
            )
        )
        await self.db.commit()
        return True


    # ===== F-04 감정 그래프 팝업 =====

    # 의사에게 보여 줄 감정 기록 조건: 그 환자, 의사에게 공유함(is_shared), 삭제 안 함
    @staticmethod
    def _shared_emotion_records(patient_id: int, start: date, end: date) -> tuple:
        return (
            EmotionRecord.user_id == patient_id,
            EmotionRecord.is_shared.is_(True),
            EmotionRecord.deleted_at.is_(None),
            EmotionRecord.record_date >= start,
            EmotionRecord.record_date < end
        )


    # 22. 감정 기록 (기간 [start, end) 날짜, 날짜순)
    async def find_emotion_records(self, patient_id: int, start: date, end: date) -> list[EmotionRecord]:
        query = (
            select(EmotionRecord)
            .where(*self._shared_emotion_records(patient_id, start, end))
            .order_by(EmotionRecord.record_date, EmotionRecord.emotion_id)
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())


    # 23. 기간 평균 기분 점수 (기록 없으면 None)
    async def avg_mood_score(self, patient_id: int, start: date, end: date) -> float | None:
        query = (
            select(func.avg(EmotionRecord.mood_score))
            .where(*self._shared_emotion_records(patient_id, start, end))
        )

        result = await self.db.execute(query)
        avg = result.scalar_one()
        return float(avg) if avg is not None else None


    # 24. 환자 메시지의 감정 (기간 안) -> [(created_at, dominant), ...]
    # - 메시지마다 감정 분석 1건만 쓴다: model_version이 가장 큰 것 (임의 결정 D-05)
    #   PostgreSQL DISTINCT ON(message_id) + ORDER BY model_version DESC
    async def find_message_emotions(self, patient_id: int, start: datetime, end: datetime) -> list[tuple]:
        query = (
            select(Message.created_at, EmotionAnalysis.dominant)
            .join(EmotionAnalysis, EmotionAnalysis.message_id == Message.id)
            .join(ChatSession, ChatSession.id == Message.session_id)
            .where(
                ChatSession.user_id == patient_id,
                Message.role == MessageRole.USER,
                Message.created_at >= start,
                Message.created_at < end
            )
            .distinct(Message.id)
            .order_by(Message.id, EmotionAnalysis.model_version.desc().nulls_last())
        )

        result = await self.db.execute(query)
        return list(result.all())


    # ===== F-03 설문조사 결과 팝업 =====

    # 25. 사전 문진 세션 1건 + 요약 + 문항별 응답(+문항 정보)
    # - session_id가 없으면 가장 최근에 시작된 문진
    async def find_intake_session(self, patient_id: int, session_id: int | None) -> ChatSession | None:
        query = (
            select(ChatSession)
            .options(
                selectinload(ChatSession.summary),
                selectinload(ChatSession.checklists).selectinload(SessionChecklist.item)
            )
            .where(
                ChatSession.user_id == patient_id,
                ChatSession.session_type == ChatSessionType.INTAKE
            )
        )

        if session_id is not None:
            query = query.where(ChatSession.id == session_id)
        else:
            query = (
                query.where(ChatSession.started_at.is_not(None))
                .order_by(ChatSession.started_at.desc(), ChatSession.id.desc())
                .limit(1)
            )

        result = await self.db.execute(query)
        return result.scalar_one_or_none()


    # 26. 문진 세션에서 측정한 척도 결과 (같은 척도가 여러 번이면 최근 것이 뒤)
    async def find_session_assessments(self, session_id: int) -> list[AssessmentResult]:
        query = (
            select(AssessmentResult)
            .where(AssessmentResult.session_id == session_id)
            .order_by(AssessmentResult.assessed_at, AssessmentResult.id)
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())


    # 27. 환자의 사전 문진 목록 (최신순)
    async def find_intake_sessions(self, patient_id: int, limit: int) -> list[ChatSession]:
        query = (
            select(ChatSession)
            .where(
                ChatSession.user_id == patient_id,
                ChatSession.session_type == ChatSessionType.INTAKE,
                ChatSession.started_at.is_not(None)
            )
            .order_by(ChatSession.started_at.desc(), ChatSession.id.desc())
            .limit(limit)
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())


    # ===== F-07 예약 일정 팝업 =====

    # 28. 예약 1건 + 환자 + 변경 이력
    # - populate_existing: 변경 직후 다시 조회할 때 DB 값으로 덮어쓴다.
    async def find_appointment(self, appointment_id: int) -> Appointment | None:
        query = (
            select(Appointment)
            .options(selectinload(Appointment.patient), selectinload(Appointment.changes))
            .where(Appointment.appointment_id == appointment_id)
            .execution_options(populate_existing=True)
        )

        result = await self.db.execute(query)
        return result.scalar_one_or_none()


    # 29. 환자별 내 예약 (기간 안, 취소 포함, 시각순)
    async def find_patient_appointments(
        self, doctor_id: int, patient_id: int, start: datetime, end: datetime
    ) -> list[Appointment]:
        query = (
            select(Appointment)
            .options(selectinload(Appointment.patient), selectinload(Appointment.changes))
            .where(
                Appointment.doctor_id == doctor_id,
                Appointment.patient_id == patient_id,
                Appointment.scheduled_at >= start,
                Appointment.scheduled_at < end
            )
            .order_by(Appointment.scheduled_at, Appointment.appointment_id)
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())


    # 30. 환자별 내 예약의 변경·취소·노쇼 횟수 (전체 기간) -> (reschedule, cancel, no_show)
    async def count_patient_appointment_stats(self, doctor_id: int, patient_id: int) -> tuple[int, int, int]:
        mine = (Appointment.doctor_id == doctor_id, Appointment.patient_id == patient_id)

        change_count = lambda change_type: (
            select(func.count(AppointmentChange.id))
            .join(Appointment, Appointment.appointment_id == AppointmentChange.appointment_id)
            .where(*mine, AppointmentChange.change_type == change_type)
            .scalar_subquery()
        )
        no_show_count = (
            select(func.count(Appointment.appointment_id))
            .where(*mine, Appointment.status == AppointmentStatus.NO_SHOW)
            .scalar_subquery()
        )

        result = await self.db.execute(
            select(change_count(AppointmentChangeType.RESCHEDULE), change_count(AppointmentChangeType.CANCEL), no_show_count)
        )
        reschedule_count, cancel_count, no_shows = result.one()
        return reschedule_count, cancel_count, no_shows


    # 31. 시간 겹침 확인 (임의 결정 D-23)
    # - 같은 의사 또는 같은 진료실의 다른 예약(취소·노쇼 제외)과 [start, end)가 겹치면 True
    # - 끝 시각이 없는 예약은 30분으로 본다.
    # ponytail: 확인과 저장 사이에 다른 요청이 끼어들 수 있다. 동시 예약이 잦으면 DB 배타 제약(EXCLUDE)으로 옮긴다.
    async def exists_overlap(
        self, doctor_id: int, room_id: int | None, start: datetime, end: datetime, exclude_id: int | None = None
    ) -> bool:
        other_end = func.coalesce(Appointment.end_at, Appointment.scheduled_at + timedelta(minutes=30))
        same_owner = Appointment.doctor_id == doctor_id if room_id is None else or_(
            Appointment.doctor_id == doctor_id, Appointment.room_id == room_id
        )

        query = (
            select(Appointment.appointment_id)
            .where(
                same_owner,
                Appointment.status.not_in([AppointmentStatus.CANCELLED, AppointmentStatus.NO_SHOW]),
                Appointment.scheduled_at < end,
                other_end > start
            )
            .limit(1)
        )
        if exclude_id is not None:
            query = query.where(Appointment.appointment_id != exclude_id)

        result = await self.db.execute(query)
        return result.scalar_one_or_none() is not None


    # 32. 진료실 1건
    async def find_room(self, room_id: int) -> Room | None:
        result = await self.db.execute(select(Room).where(Room.id == room_id))
        return result.scalar_one_or_none()


    # 33. 이 병원에서 진료를 마친 적이 있는지 (초진/재진 판단, 임의 결정 D-26)
    async def has_completed_visit(self, patient_id: int, hospital_id: int) -> bool:
        query = (
            select(Appointment.appointment_id)
            .where(
                Appointment.patient_id == patient_id,
                Appointment.hospital_id == hospital_id,
                Appointment.status == AppointmentStatus.COMPLETED
            )
            .limit(1)
        )

        result = await self.db.execute(query)
        return result.scalar_one_or_none() is not None


    # 34. 예약 추가 + 환자·의사 캘린더 일정 2건 (한 트랜잭션, 연결-07) -> 새 예약 id
    async def create_appointment(self, values: dict, schedule_type: ScheduleType, title: str) -> int:
        now = datetime.now(KST)
        result = await self.db.execute(
            insert(Appointment)
            .values(**values, created_at=now, updated_at=now)
            .returning(Appointment.appointment_id)
        )
        appointment_id = result.scalar_one()

        await self.db.execute(
            insert(Schedule),
            [
                {
                    "user_id": user_id,
                    "created_by": values["doctor_id"],
                    "schedule_type": schedule_type,
                    "title": title,
                    "start_at": values["scheduled_at"],
                    "end_at": values["end_at"],
                    "appointment_id": appointment_id,
                    "created_at": now,
                    "updated_at": now
                }
                for user_id in (values["patient_id"], values["doctor_id"])
            ]
        )
        await self.db.commit()
        return appointment_id


    # 35. 일정 변경 + 변경 이력 + 캘린더 일정 이동 (한 트랜잭션)
    # - booked·waiting인 예약만 바꾼다. 바뀐 예약은 다시 booked
    async def reschedule_appointment(
        self, appointment_id: int, doctor_id: int, from_at: datetime, start: datetime, end: datetime, reason: str | None
    ) -> bool:
        result = await self.db.execute(
            update(Appointment)
            .where(
                Appointment.appointment_id == appointment_id,
                Appointment.status.in_([AppointmentStatus.BOOKED, AppointmentStatus.WAITING])
            )
            .values(scheduled_at=start, end_at=end, status=AppointmentStatus.BOOKED)
        )
        if result.rowcount == 0:
            await self.db.rollback()
            return False

        await self.db.execute(
            insert(AppointmentChange).values(
                appointment_id=appointment_id,
                from_at=from_at,
                to_at=start,
                change_type=AppointmentChangeType.RESCHEDULE,
                reason=reason,
                requested_by=RequestedBy.DOCTOR,
                changed_by=doctor_id,
                created_at=datetime.now(KST)
            )
        )
        await self.db.execute(
            update(Schedule)
            .where(Schedule.appointment_id == appointment_id)
            .values(start_at=start, end_at=end)
        )
        await self.db.commit()
        return True


    # 36. 예약 취소 + 변경 이력 + 캘린더 일정 삭제 (한 트랜잭션, 연결-07: 양쪽 캘린더에서 사라진다)
    async def cancel_appointment(
        self, appointment_id: int, doctor_id: int, from_at: datetime, reason: str | None
    ) -> bool:
        result = await self.db.execute(
            update(Appointment)
            .where(
                Appointment.appointment_id == appointment_id,
                Appointment.status.in_([AppointmentStatus.BOOKED, AppointmentStatus.WAITING])
            )
            .values(status=AppointmentStatus.CANCELLED)
        )
        if result.rowcount == 0:
            await self.db.rollback()
            return False

        await self.db.execute(
            insert(AppointmentChange).values(
                appointment_id=appointment_id,
                from_at=from_at,
                change_type=AppointmentChangeType.CANCEL,
                reason=reason,
                requested_by=RequestedBy.DOCTOR,
                changed_by=doctor_id,
                created_at=datetime.now(KST)
            )
        )
        await self.db.execute(delete(Schedule).where(Schedule.appointment_id == appointment_id))
        await self.db.commit()
        return True


    # 37. 진료 상태 변경 (지금 상태가 from_statuses 중 하나일 때만)
    async def update_appointment_status(
        self, appointment_id: int, from_statuses: list[AppointmentStatus], to_status: AppointmentStatus
    ) -> bool:
        values = {"status": to_status}
        if to_status == AppointmentStatus.COMPLETED:
            values["completed_at"] = datetime.now(KST)

        result = await self.db.execute(
            update(Appointment)
            .where(
                Appointment.appointment_id == appointment_id,
                Appointment.status.in_(from_statuses)
            )
            .values(**values)
        )
        await self.db.commit()
        return result.rowcount > 0


    # 38. 환자별 내 다음 예약 (now 이후, booked·waiting 중 가장 이른 1건)
    async def find_next_appointment(self, doctor_id: int, patient_id: int, now: datetime) -> Appointment | None:
        query = (
            select(Appointment)
            .where(
                Appointment.doctor_id == doctor_id,
                Appointment.patient_id == patient_id,
                Appointment.scheduled_at > now,
                Appointment.status.in_([AppointmentStatus.BOOKED, AppointmentStatus.WAITING])
            )
            .order_by(Appointment.scheduled_at, Appointment.appointment_id)
            .limit(1)
        )

        result = await self.db.execute(query)
        return result.scalar_one_or_none()



# 주입 팩토리 메서드
def get_doctor_repository(db: AsyncSession = Depends(get_postgresql_db)):
    return DoctorRepository(db)
