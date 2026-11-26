from datetime import datetime
from fastapi import Depends
from sqlalchemy import select, insert, update, exists, func, and_, or_, not_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.infrastructure.postgresql import get_postgresql_db

# 모델, ORM
from app.models.care_request_model import CareRequest
from app.models.request_contact_model import RequestContact
from app.models.hospital_model import Hospital
from app.models.doctor_profile_model import DoctorProfile
from app.models.notification_model import Notification
from app.models.risk_event_model import RiskEvent
from app.models.request_message_model import RequestMessage
from app.models.appointment_model import Appointment
from app.models.care_relation_model import CareRelation
from app.enums.care_request_enum import CareRequestStatus
from app.enums.request_contact_enum import RequestContactStatus
from app.enums.appointment_enum import AppointmentStatus
from app.enums.risk_event_enum import RiskEventLevel, RiskEventStatus

# advisory lock 키 (일정 알림 REMINDER_LOCK_KEY = 20261125와 겹치지 않게)
CARE_REQUEST_EXPIRE_LOCK_KEY = 20261126   # 무응답 스케줄러: 여러 워커 중 1개만 실행
CARE_REQUEST_CREATE_LOCK_KEY = 20261127   # 진료 요청 만들기: 같은 환자가 동시에 두 번 눌러도 1건만

# 진행 중인 요청 상태 (새 요청을 막고, 취소할 수 있는 상태)
ACTIVE_STATUSES = (
    CareRequestStatus.REQUESTED,
    CareRequestStatus.CONTACTING,
    CareRequestStatus.CONNECTED,
)


class CareRequestRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # 요청 1건 + 연락 내역·연결 병원
    # - populate_existing: update()로 바꾼 뒤 다시 읽을 때 세션에 남은 예전 값 대신 DB 값을 쓴다.
    def _request_query(self):
        return (
            select(CareRequest)
            .options(selectinload(CareRequest.contacts), selectinload(CareRequest.matched_hospital))
            .execution_options(populate_existing=True)
        )

    async def find_request(self, request_id: int) -> CareRequest | None:
        result = await self.db.execute(self._request_query().where(CareRequest.request_id == request_id))
        return result.scalar_one_or_none()

    # 환자의 진행 중 요청 (requested·contacting·connected), 가장 최근 것
    async def find_active_request(self, patient_id: int) -> CareRequest | None:
        result = await self.db.execute(
            self._request_query()
            .where(CareRequest.patient_id == patient_id, CareRequest.status.in_(ACTIVE_STATUSES))
            .order_by(CareRequest.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    # 같은 환자의 요청 만들기를 줄 세운다 (트랜잭션이 끝나면 자동으로 풀림)
    # - "진행 중 요청 확인 -> 저장" 사이에 같은 환자의 다른 요청이 끼어들지 못하게 한다.
    # - 두 정수 키 버전(int4, int4)이라 patient_id를 int4 범위로 맞춘다.
    async def lock_patient(self, patient_id: int) -> None:
        await self.db.execute(
            select(func.pg_advisory_xact_lock(CARE_REQUEST_CREATE_LOCK_KEY, patient_id % 2_147_483_647))
        )

    # 확인 전(open) high 위험 기록이 있는지 (있으면 병원 연락 대신 crisis)
    async def has_open_high_risk(self, patient_id: int) -> bool:
        result = await self.db.execute(
            select(exists().where(
                RiskEvent.user_id == patient_id,
                RiskEvent.status == RiskEventStatus.OPEN,
                RiskEvent.level == RiskEventLevel.HIGH,
            ))
        )
        return bool(result.scalar())

    # 주변 병원 후보: 요청 받는 중 + 위도·경도 있음 + 소속 의사 1명 이상 + 위도·경도 사각형 안
    # - 정확한 반경(원)은 서비스에서 haversine_km로 다시 거른다. (PostGIS 없음)
    async def find_candidate_hospitals(
        self, min_lat: float, max_lat: float, min_lon: float, max_lon: float
    ) -> list[Hospital]:
        has_doctor = exists().where(DoctorProfile.hospital_id == Hospital.hospital_id)
        result = await self.db.execute(
            select(Hospital).where(
                Hospital.is_accepting.is_(True),
                Hospital.latitude.is_not(None),
                Hospital.longitude.is_not(None),
                Hospital.latitude.between(min_lat, max_lat),
                Hospital.longitude.between(min_lon, max_lon),
                has_doctor,
            )
        )
        return list(result.scalars().all())

    # 병원별 소속 의사 id {hospital_id: [doctor_id, ...]}
    async def find_doctor_ids_by_hospital(self, hospital_ids: list[int]) -> dict[int, list[int]]:
        if not hospital_ids:
            return {}
        result = await self.db.execute(
            select(DoctorProfile.hospital_id, DoctorProfile.user_id)
            .where(DoctorProfile.hospital_id.in_(hospital_ids))
            .order_by(DoctorProfile.user_id)
        )
        doctor_ids: dict[int, list[int]] = {hospital_id: [] for hospital_id in hospital_ids}
        for hospital_id, user_id in result.all():
            doctor_ids[hospital_id].append(user_id)
        return doctor_ids

    # 요청 + 연락 내역 + 알림을 한 트랜잭션으로 저장하고 commit
    # - notification_rows에는 request_id가 없다. 요청을 넣은 뒤 여기서 채운다.
    # - hospital_ids는 서비스에서 중복을 없앤 목록이다. (같은 요청으로 같은 병원에 두 번 연락하지 않는다, 연결-02 규칙)
    async def save_request(
        self,
        values: dict,
        hospital_ids: list[int],
        notification_rows: list[dict],
        sent_at: datetime,
    ) -> int:
        result = await self.db.execute(
            insert(CareRequest).values(**values).returning(CareRequest.request_id)
        )
        request_id = result.scalar_one()

        if hospital_ids:
            await self.db.execute(
                insert(RequestContact),
                [
                    {
                        "request_id": request_id,
                        "hospital_id": hospital_id,
                        "status": RequestContactStatus.SENT,
                        "sent_at": sent_at,
                    }
                    for hospital_id in hospital_ids
                ],
            )

        if notification_rows:
            await self.db.execute(
                insert(Notification),
                [{**row, "request_id": request_id} for row in notification_rows],
            )

        await self.db.commit()
        return request_id

    # 요청 취소: 진행 중일 때만 cancelled (동시에 병원이 응답해도 조건부 UPDATE로 안전하게)
    # - 이미 만든 연락 내역은 그대로 둔다. (병원 목록에서 "취소된 요청"으로 보인다)
    async def cancel_request(self, request_id: int) -> bool:
        result = await self.db.execute(
            update(CareRequest)
            .where(CareRequest.request_id == request_id, CareRequest.status.in_(ACTIVE_STATUSES))
            .values(status=CareRequestStatus.CANCELLED)
        )
        await self.db.commit()
        return result.rowcount > 0

    # ------------------------------------------------------------
    # 무응답 스케줄러 (CareRequestExpireService.run_once)
    # - 아래 함수들은 한 트랜잭션 안에서 차례로 부르고, 마지막 create_notifications에서 한 번에 commit한다.
    # ------------------------------------------------------------

    # 여러 워커가 떠 있어도 1개만 실행 (트랜잭션 단위 lock, commit·rollback 때 풀림)
    async def try_acquire_lock(self) -> bool:
        result = await self.db.execute(
            select(func.pg_try_advisory_xact_lock(CARE_REQUEST_EXPIRE_LOCK_KEY))
        )
        return bool(result.scalar())

    # 1. 기한이 지난 sent 연락 -> no_response
    # - WHERE status='sent' 조건부라 병원이 먼저 응답한 연락은 바뀌지 않는다.
    async def expire_no_response_contacts(self, deadline: datetime) -> int:
        result = await self.db.execute(
            update(RequestContact)
            .where(RequestContact.status == RequestContactStatus.SENT, RequestContact.sent_at <= deadline)
            .values(status=RequestContactStatus.NO_RESPONSE)
        )
        return result.rowcount

    # 2. contacting인데 남은 sent 연락이 없고 연결된 병원도 없는 요청 -> expired, (request_id, patient_id) 목록
    # - WHERE status='contacting' 조건부라 그 사이 연결(connected)된 요청은 바뀌지 않는다.
    # - request_id를 주면 그 요청만 본다. (병원이 불가로 응답한 직후, 임의 결정 D-57)
    async def expire_exhausted_requests(self, request_id: int | None = None) -> list[tuple[int, int]]:
        has_sent = exists().where(
            RequestContact.request_id == CareRequest.request_id,
            RequestContact.status == RequestContactStatus.SENT,
        )
        stmt = (
            update(CareRequest)
            .where(
                CareRequest.status == CareRequestStatus.CONTACTING,
                CareRequest.matched_hospital_id.is_(None),
                ~has_sent,
            )
            .values(status=CareRequestStatus.EXPIRED)
            .returning(CareRequest.request_id, CareRequest.patient_id)
        )
        if request_id is not None:
            stmt = stmt.where(CareRequest.request_id == request_id)
        result = await self.db.execute(stmt)
        return [(rid, patient_id) for rid, patient_id in result.all()]

    # 3. 알림 여러 건을 한 번에 넣고 commit (알림이 없어도 앞의 변경을 commit한다)
    # - 스케줄러와 병원 응답(respond)이 마지막에 같이 쓴다.
    async def create_notifications(self, rows: list[dict]) -> int:
        if rows:
            await self.db.execute(insert(Notification), rows)
        await self.db.commit()
        return len(rows)

    async def rollback(self) -> None:
        await self.db.rollback()

    # ------------------------------------------------------------
    # 병원 측 (2단계)
    # ------------------------------------------------------------

    # 의사의 소속 병원 id (doctor_profiles.hospital_id), 프로필이 없으면 None
    async def find_doctor_hospital_id(self, doctor_id: int) -> int | None:
        result = await self.db.execute(
            select(DoctorProfile.hospital_id).where(DoctorProfile.user_id == doctor_id)
        )
        return result.scalar_one_or_none()

    # 연락 내역 + 요청 + 환자 + 병원
    def _contact_query(self):
        return (
            select(RequestContact)
            .join(RequestContact.request)
            .options(
                selectinload(RequestContact.request).selectinload(CareRequest.patient),
                selectinload(RequestContact.hospital),
            )
            .execution_options(populate_existing=True)
        )

    async def find_hospital_contact(self, request_id: int, hospital_id: int) -> RequestContact | None:
        result = await self.db.execute(
            self._contact_query().where(
                RequestContact.request_id == request_id, RequestContact.hospital_id == hospital_id
            )
        )
        return result.scalar_one_or_none()

    # 내 병원의 요청 목록 (탭별)
    # - pending: 우리 연락이 sent + 요청이 contacting + 응답 기한(deadline 이후에 보낸 것)이 남음
    #   (스케줄러가 최대 10초 늦게 no_response로 바꾸므로 기한 지난 것은 여기서 먼저 뺀다)
    # - connected: 요청이 우리 병원과 연결되었고 connected·booked
    # - closed: 그 밖 (declined, no_response, 다른 병원과 연결, 취소, 만료), closed_since 이후만 (임의 결정 D-55)
    # - 정렬: pending은 기한이 가까운 순(= sent_at 오래된 순), 나머지는 sent_at 최신순
    async def find_hospital_contacts(
        self, hospital_id: int, tab: str, deadline: datetime, closed_since: datetime
    ) -> list[RequestContact]:
        pending = and_(
            RequestContact.status == RequestContactStatus.SENT,
            CareRequest.status == CareRequestStatus.CONTACTING,
            RequestContact.sent_at > deadline,
        )
        connected = and_(
            CareRequest.matched_hospital_id == hospital_id,
            CareRequest.status.in_((CareRequestStatus.CONNECTED, CareRequestStatus.BOOKED)),
        )

        stmt = self._contact_query().where(RequestContact.hospital_id == hospital_id)
        if tab == "pending":
            stmt = stmt.where(pending).order_by(RequestContact.sent_at.asc())
        elif tab == "connected":
            stmt = stmt.where(connected).order_by(RequestContact.sent_at.desc())
        else:
            stmt = (
                stmt.where(not_(or_(pending, connected)), RequestContact.sent_at >= closed_since)
                .order_by(RequestContact.sent_at.desc())
            )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    # respond 1. 우리 연락 sent -> available/declined (기한 안, 아직 응답 전일 때만)
    # - 조건부 UPDATE라 스케줄러가 먼저 no_response로 바꿨거나 이미 응답했으면 rowcount 0
    async def mark_contact_response(
        self, request_id: int, hospital_id: int, doctor_id: int,
        contact_status: RequestContactStatus, now: datetime, deadline: datetime
    ) -> bool:
        result = await self.db.execute(
            update(RequestContact)
            .where(
                RequestContact.request_id == request_id,
                RequestContact.hospital_id == hospital_id,
                RequestContact.status == RequestContactStatus.SENT,
                RequestContact.sent_at > deadline,
            )
            .values(status=contact_status, responded_by=doctor_id, responded_at=now)
        )
        return result.rowcount > 0

    # respond 2. 요청을 우리 병원과 연결 (contacting이고 아직 연결된 병원이 없을 때만)
    # - 두 병원이 동시에 눌러도 행 lock 때문에 한쪽은 기다렸다가 조건을 다시 보고 rowcount 0이 된다. (연결-03 규칙: 1곳만)
    async def connect_request(self, request_id: int, hospital_id: int) -> bool:
        result = await self.db.execute(
            update(CareRequest)
            .where(
                CareRequest.request_id == request_id,
                CareRequest.status == CareRequestStatus.CONTACTING,
                CareRequest.matched_hospital_id.is_(None),
            )
            .values(matched_hospital_id=hospital_id, status=CareRequestStatus.CONNECTED)
        )
        return result.rowcount > 0

    # ------------------------------------------------------------
    # 예약 채팅 (3단계)
    # ------------------------------------------------------------

    # 연결을 수락한 의사 id (우리 병원 연락의 responded_by, available일 때)
    async def find_accepted_doctor_id(self, request_id: int, hospital_id: int) -> int | None:
        result = await self.db.execute(
            select(RequestContact.responded_by).where(
                RequestContact.request_id == request_id,
                RequestContact.hospital_id == hospital_id,
                RequestContact.status == RequestContactStatus.AVAILABLE,
            )
        )
        return result.scalar_one_or_none()

    # 요청으로 잡은 예약 중 취소되지 않은 가장 늦은 진료 일시 (booked 상태의 채팅 마감 계산용)
    async def find_latest_appointment_at(self, request_id: int) -> datetime | None:
        result = await self.db.execute(
            select(Appointment.scheduled_at)
            .where(Appointment.request_id == request_id, Appointment.status != AppointmentStatus.CANCELLED)
            .order_by(Appointment.scheduled_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    # 상대가 보낸 안 읽은 메시지 읽음 처리 후 commit
    # - from_patient=True: 환자가 보낸 메시지 (의사가 읽음) / False: 병원(의사)이 보낸 메시지 (환자가 읽음)
    async def mark_messages_read(self, request_id: int, patient_id: int, from_patient: bool, now: datetime) -> int:
        sender_cond = RequestMessage.sender_id == patient_id if from_patient else RequestMessage.sender_id != patient_id
        result = await self.db.execute(
            update(RequestMessage)
            .where(RequestMessage.request_id == request_id, RequestMessage.read_at.is_(None), sender_cond)
            .values(read_at=now)
        )
        await self.db.commit()
        return result.rowcount

    # 메시지 목록 (오래된 순), after_id를 주면 그 뒤 메시지만 (폴링용)
    async def find_messages(self, request_id: int, after_id: int | None) -> list[RequestMessage]:
        stmt = (
            select(RequestMessage)
            .where(RequestMessage.request_id == request_id)
            .order_by(RequestMessage.message_id.asc())
            .execution_options(populate_existing=True)
        )
        if after_id is not None:
            stmt = stmt.where(RequestMessage.message_id > after_id)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    # 메시지 저장 + 상대 알림을 한 번에 commit
    async def create_message(self, values: dict, notification_rows: list[dict]) -> RequestMessage:
        result = await self.db.execute(insert(RequestMessage).values(**values).returning(RequestMessage))
        message = result.scalar_one()
        if notification_rows:
            await self.db.execute(insert(Notification), notification_rows)
        await self.db.commit()
        return message

    # ------------------------------------------------------------
    # 진료 후 담당 등록 + 빠른 진료 예약 (5단계)
    # ------------------------------------------------------------

    async def find_appointment(self, appointment_id: int) -> Appointment | None:
        result = await self.db.execute(
            select(Appointment)
            .options(selectinload(Appointment.doctor))
            .where(Appointment.appointment_id == appointment_id)
        )
        return result.scalar_one_or_none()

    # 지금 담당 관계 (ended_at IS NULL), 여러 건이면 가장 최근 것
    async def find_current_relation(self, patient_id: int) -> CareRelation | None:
        result = await self.db.execute(
            select(CareRelation)
            .options(selectinload(CareRelation.doctor))
            .where(CareRelation.patient_id == patient_id, CareRelation.ended_at.is_(None))
            .order_by(CareRelation.started_at.desc(), CareRelation.relation_id.desc())
            .limit(1)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    # 담당 등록 (한 트랜잭션): 기존 담당 관계는 모두 ended_at=now로 끝내고 새 관계 1건 -> commit
    async def register_relation(self, patient_id: int, doctor_id: int, now: datetime) -> None:
        await self.db.execute(
            update(CareRelation)
            .where(CareRelation.patient_id == patient_id, CareRelation.ended_at.is_(None))
            .values(ended_at=now)
        )
        await self.db.execute(
            insert(CareRelation).values(patient_id=patient_id, doctor_id=doctor_id, started_at=now, created_at=now)
        )
        await self.db.commit()


def get_care_request_repository(db: AsyncSession = Depends(get_postgresql_db)):
    return CareRequestRepository(db)
