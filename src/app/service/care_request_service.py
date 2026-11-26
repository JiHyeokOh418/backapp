import asyncio
import logging
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from app.repository.care_request_repository import (
    CareRequestRepository,
    get_care_request_repository,
    ACTIVE_STATUSES,
)
from app.models.care_request_model import CareRequest
from app.models.request_contact_model import RequestContact
from app.models.hospital_model import Hospital
from app.enums.care_request_enum import CareRequestMode, CareRequestType, CareRequestStatus
from app.enums.request_contact_enum import RequestContactStatus
from app.enums.notification_enum import NotificationType
from app.enums.user_enum import UserRole
from app.schema.user_schema import UserClaimDTO
from app.schema.doctor_schema import DoctorPatientBriefDTO, AppointmentDetailResponseDTO
from app.schema.care_request_schema import (
    CareRequestCreateDTO,
    CareRequestResponseDTO,
    ConnectedHospitalDTO,
    CareRequestExpireRunResultDTO,
    HospitalCareRequestDTO,
    HospitalCareRequestTab,
    CareRequestRespondDTO,
    RequestMessageCreateDTO,
    RequestMessageDTO,
    CareRequestAppointmentCreateDTO,
    CareRelationRegisterDTO,
    CareRelationResponseDTO,
    CareRequestDirectCreateDTO,
)
from app.models.request_message_model import RequestMessage
from app.repository.doctor_repository import DoctorRepository, get_doctor_repository
from app.service.doctor_service import DoctorService, SCHEDULE_BY_KIND, DEFAULT_APPOINTMENT_MINUTES
from app.enums.appointment_enum import AppointmentStatus, AppointmentVisitType, AppointmentBookingSource
from app.util.date_util import now_kst, KST
from app.util.geo_util import haversine_km, bounding_box

load_dotenv()

logger = logging.getLogger(__name__)

# 설정값 (.env, 없으면 기본값)
# - 반경 10km (결정-44 수정), 응답 제한 60초 (결정-45 수정, 반경 넓히기 없음)
# - 한 번에 연락할 병원 수 3곳 (임의 결정 D-51)
#   TODO: 한 번에 연락할 병원 수는 아직 미정. 결정-44 추천안 "한 번에 3곳"을 기본값으로 둔다.
CARE_REQUEST_RADIUS_KM = float(os.getenv("CARE_REQUEST_RADIUS_KM", "10"))
CARE_REQUEST_TIMEOUT_SECONDS = int(os.getenv("CARE_REQUEST_TIMEOUT_SECONDS", "60"))
CARE_REQUEST_MAX_HOSPITALS = int(os.getenv("CARE_REQUEST_MAX_HOSPITALS", "3"))

REQUEST_TYPE_LABEL = {
    CareRequestType.CONSULT: "상담",
    CareRequestType.TREATMENT: "진료",
}

# 병원 정보를 보여 주는 상태 (연결된 뒤)
HOSPITAL_VISIBLE_STATUSES = (CareRequestStatus.CONNECTED, CareRequestStatus.BOOKED)

# 병원 측 closed 탭은 최근 30일만 (임의 결정 D-55)
CLOSED_TAB_DAYS = 30

WEEKDAYS = "월화수목금토일"

# respond 409 문구
RESPOND_CLOSED_DETAIL = "이미 응답했거나 응답 시간이 지난 요청입니다."
ALREADY_CONNECTED_DETAIL = "이미 연결된 요청입니다."
CANCELLED_DETAIL = "환자가 취소한 요청입니다."


# 알림 dict (schedule_reminder_service.py의 _build_notification과 같은 방식)
# - request_id는 요청을 저장할 때 레포지토리가 채운다. (스케줄러처럼 이미 있으면 넣어서 보낸다)
def _build_notification(
    user_id: int, title: str, content: str, now: datetime, request_id: int | None = None,
    notification_type: NotificationType = NotificationType.REQUEST,
) -> dict:
    row = {
        "user_id": user_id,
        "notification_type": notification_type,
        "title": title,
        "content": content,
        "sent_at": now,
    }
    if request_id is not None:
        row["request_id"] = request_id
    return row


def _no_hospital_notification(patient_id: int, now: datetime) -> dict:
    return _build_notification(
        patient_id, "주변에 연락 가능한 병원이 없어요",
        "지금은 연락할 수 있는 병원이 없어요. 잠시 후 다시 요청해 주세요.", now
    )


# 병원 의사에게 새 요청 알림 (where: "서울 강남구에서" / "담당 환자가")
def _new_request_notification(doctor_id: int, request_type: CareRequestType, where: str, now: datetime) -> dict:
    label = REQUEST_TYPE_LABEL[request_type]
    return _build_notification(
        doctor_id, f"새 {label} 요청이 도착했어요",
        f"{where} {label} 요청이 왔어요. {CARE_REQUEST_TIMEOUT_SECONDS}초 안에 응답해 주세요.", now
    )


# 예약 확정 알림 제목에 넣을 시각 (예: 11월 27일 (금) 15:00)
def _format_kst(value: datetime) -> str:
    local = value.astimezone(KST)
    return f"{local.month}월 {local.day}일 ({WEEKDAYS[local.weekday()]}) {local:%H:%M}"


# 모든 병원이 응답하지 않거나 불가로 답해 요청이 만료됐을 때 (스케줄러, 불가 응답 D-57 공용)
def _expired_notification(patient_id: int, request_id: int, now: datetime) -> dict:
    return _build_notification(
        patient_id, "연락 가능한 병원을 찾지 못했어요",
        "병원이 응답하지 않았어요. 잠시 후 다시 요청해 주세요.", now, request_id
    )


class CareRequestService:

    # doctor_repo: 예약 확정(4단계)에서 F-07의 예약 생성·시간 검증을 그대로 쓰기 위해 받는다.
    # - 두 레포지토리는 같은 요청 안에서 get_postgresql_db 세션 1개를 같이 쓴다 (FastAPI Depends 캐시).
    def __init__(self, repo: CareRequestRepository, doctor_repo: DoctorRepository):
        self.repo = repo
        self.doctor_repo = doctor_repo
        self.doctor_service = DoctorService(doctor_repo)

    @staticmethod
    def _ensure_patient(current_user: UserClaimDTO) -> None:
        if current_user.role != UserRole.PATIENT:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="환자만 사용할 수 있습니다."
            )

    # ORM -> 응답 DTO (위험 정보는 넣지 않는다, 공통-05)
    @staticmethod
    def _to_response(request: CareRequest) -> CareRequestResponseDTO:
        latest_sent_at = max((c.sent_at for c in request.contacts), default=None)
        expires_at = (
            latest_sent_at + timedelta(seconds=CARE_REQUEST_TIMEOUT_SECONDS) if latest_sent_at else None
        )
        hospital = None
        if request.status in HOSPITAL_VISIBLE_STATUSES and request.matched_hospital:
            hospital = ConnectedHospitalDTO.model_validate(request.matched_hospital)

        return CareRequestResponseDTO(
            request_id=request.request_id,
            request_type=request.request_type,
            request_mode=request.request_mode,
            status=request.status,
            preferred_time=request.preferred_time,
            memo=request.memo,
            created_at=request.created_at,
            contact_count=len(request.contacts),
            expires_at=expires_at,
            hospital=hospital,
        )

    async def _ensure_no_active_request(self, patient_id: int) -> None:
        if await self.repo.find_active_request(patient_id):
            # (임의 결정 D-53) 진행 중(requested·contacting·connected) 요청이 있으면 새로 만들 수 없다.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="진행 중인 진료 요청이 있습니다."
            )

    # 요청 만들기 공통 시작 (주변 병원 요청·직접 요청): 환자 확인 -> 환자별 lock -> 진행 중 요청 확인
    async def _begin_request(self, current_user: UserClaimDTO) -> int:
        self._ensure_patient(current_user)
        await self.repo.lock_patient(current_user.id)
        await self._ensure_no_active_request(current_user.id)
        return current_user.id

    # 확인 전 high 위험 기록이 있으면 병원 연락 없이 crisis로 저장하고 응답, 없으면 None
    # TODO: crisis로 넘어간 요청의 위기 대응(판단-07) 연결 방식은 미정
    async def _save_crisis_if_needed(self, values: dict, now: datetime) -> CareRequestResponseDTO | None:
        if not await self.repo.has_open_high_risk(values["patient_id"]):
            return None
        request_id = await self.repo.save_request({**values, "status": CareRequestStatus.CRISIS}, [], [], now)
        return self._to_response(await self.repo.find_request(request_id))

    # 반경 안 병원을 가까운 순으로 최대 N곳
    # - SQL로 위도·경도 사각형 안 후보를 가져오고, 파이썬에서 실제 거리(원)로 다시 거른다.
    async def _find_nearby_hospitals(self, latitude: float, longitude: float) -> list[Hospital]:
        candidates = await self.repo.find_candidate_hospitals(
            *bounding_box(latitude, longitude, CARE_REQUEST_RADIUS_KM)
        )
        with_distance = [
            (haversine_km(latitude, longitude, float(h.latitude), float(h.longitude)), h)
            for h in candidates
        ]
        nearby = sorted(
            (item for item in with_distance if item[0] <= CARE_REQUEST_RADIUS_KM),
            key=lambda item: (item[0], item[1].hospital_id),  # 거리가 같으면 id 순 (결과가 매번 같게)
        )
        return [hospital for _, hospital in nearby[:CARE_REQUEST_MAX_HOSPITALS]]

    # POST /care-requests (연결-01·02)
    # - 처리 순서: 진행 중 요청 확인 -> 위기 확인 -> 주변 병원 고르기 -> 요청·연락·알림 저장 (한 트랜잭션)
    # - 명세의 "requested로 저장 -> crisis/expired/contacting으로 변경"은 한 트랜잭션 안의 일이라
    #   밖에서는 최종 상태만 보인다. 그래서 최종 상태로 한 번에 저장한다.
    async def create_request(
        self, current_user: UserClaimDTO, dto: CareRequestCreateDTO
    ) -> CareRequestResponseDTO:
        patient_id = await self._begin_request(current_user)

        now = now_kst()
        values = {
            "patient_id": patient_id,
            "request_mode": CareRequestMode.NEARBY,
            "request_type": dto.request_type,
            "address": dto.address,
            "sido": dto.sido,
            "sigungu": dto.sigungu,
            "latitude": dto.latitude,
            "longitude": dto.longitude,
            "preferred_time": dto.preferred_time,
            "memo": dto.memo,  # 요청 메모에는 위험 필터를 쓰지 않는다 (11-24 확정)
            "created_at": now,
        }

        # 1. 확인 전 high 위험 기록이 있으면 병원 연락 없이 crisis
        crisis = await self._save_crisis_if_needed(values, now)
        if crisis:
            return crisis

        # 2. 주변 병원 (반경 10km, 가까운 순 최대 3곳)
        hospitals = await self._find_nearby_hospitals(float(dto.latitude), float(dto.longitude))

        # 3. 병원이 없으면 expired + 환자 알림 (연결-02 예외)
        if not hospitals:
            request_id = await self.repo.save_request(
                {**values, "status": CareRequestStatus.EXPIRED}, [], [_no_hospital_notification(patient_id, now)], now
            )
            return self._to_response(await self.repo.find_request(request_id))

        # 4. 병원마다 연락 1건 + 소속 의사 전원에게 알림, contacting
        # - 병원 이름·환자 이름은 알림에 넣지 않는다. 지역과 요청 종류만 (결정-41·50)
        hospital_ids = list(dict.fromkeys(h.hospital_id for h in hospitals))  # 순서 유지 중복 제거
        doctor_ids = await self.repo.find_doctor_ids_by_hospital(hospital_ids)
        notifications = [
            _new_request_notification(doctor_id, dto.request_type, f"{dto.sido} {dto.sigungu}에서", now)
            for hospital_id in hospital_ids
            for doctor_id in doctor_ids.get(hospital_id, [])
        ]
        request_id = await self.repo.save_request(
            {**values, "status": CareRequestStatus.CONTACTING}, hospital_ids, notifications, now
        )
        return self._to_response(await self.repo.find_request(request_id))

    # GET /care-requests/me: 진행 중 요청, 없으면 None
    async def get_my_active_request(self, current_user: UserClaimDTO) -> CareRequestResponseDTO | None:
        self._ensure_patient(current_user)
        request = await self.repo.find_active_request(current_user.id)
        return self._to_response(request) if request else None

    # POST /care-requests/{request_id}/cancel
    async def cancel_request(self, current_user: UserClaimDTO, request_id: int) -> CareRequestResponseDTO:
        self._ensure_patient(current_user)

        request = await self.repo.find_request(request_id)
        if not request or request.patient_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="진료 요청이 존재하지 않습니다."
            )

        # 확인한 뒤 병원이 응답·만료되었을 수 있어서 UPDATE 조건으로 한 번 더 막는다.
        if request.status not in ACTIVE_STATUSES or not await self.repo.cancel_request(request_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="취소할 수 없는 상태의 요청입니다."
            )

        return self._to_response(await self.repo.find_request(request_id))

    # ------------------------------------------------------------
    # 병원 측 (2단계, 연결-03·04, 화면-30)
    # ------------------------------------------------------------

    # 내 병원 = doctor_profiles.hospital_id, 프로필이 없으면 404
    async def _get_my_hospital_id(self, doctor_id: int) -> int:
        hospital_id = await self.repo.find_doctor_hospital_id(doctor_id)
        if hospital_id is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="의사 프로필이 없습니다."
            )
        return hospital_id

    # 연락 내역 ORM -> 병원 측 DTO
    # - 환자 이름은 우리 병원과 연결된 뒤(connected·booked)에만 (결정-41·50) (임의 결정 D-56)
    @staticmethod
    def _to_hospital_dto(contact: RequestContact) -> HospitalCareRequestDTO:
        request = contact.request
        is_ours = (
            request.matched_hospital_id == contact.hospital_id
            and request.status in HOSPITAL_VISIBLE_STATUSES
        )
        patient = (
            DoctorPatientBriefDTO(id=request.patient.id, name=request.patient.name) if is_ours else None
        )

        return HospitalCareRequestDTO(
            request_id=request.request_id,
            request_code=f"R-{request.request_id:06d}",
            request_type=request.request_type,
            sido=request.sido,
            sigungu=request.sigungu,
            preferred_time=request.preferred_time,
            memo=request.memo,
            request_status=request.status,
            contact_status=contact.status,
            sent_at=contact.sent_at,
            expires_at=contact.sent_at + timedelta(seconds=CARE_REQUEST_TIMEOUT_SECONDS),
            responded_at=contact.responded_at,
            patient=patient,
        )

    # GET /doctor/care-requests?tab=
    async def get_hospital_requests(
        self, doctor_id: int, tab: HospitalCareRequestTab
    ) -> list[HospitalCareRequestDTO]:
        hospital_id = await self._get_my_hospital_id(doctor_id)
        now = now_kst()
        contacts = await self.repo.find_hospital_contacts(
            hospital_id, tab,
            deadline=now - timedelta(seconds=CARE_REQUEST_TIMEOUT_SECONDS),
            closed_since=now - timedelta(days=CLOSED_TAB_DAYS),
        )
        return [self._to_hospital_dto(c) for c in contacts]

    # POST /doctor/care-requests/{request_id}/respond (한 트랜잭션)
    # 1. 우리 병원 연락 내역이 없으면 404
    # 2. 연락 sent -> available/declined (조건부 UPDATE, rowcount 0이면 409)
    # 3. available: 요청 connected (조건부 UPDATE, rowcount 0이면 rollback 후 409) + 환자 알림 (연결-04)
    # 4. declined: 남은 sent 연락이 없고 연결된 병원도 없으면 바로 expired + 환자 알림 (임의 결정 D-57)
    async def respond(
        self, doctor_id: int, request_id: int, dto: CareRequestRespondDTO
    ) -> HospitalCareRequestDTO:
        hospital_id = await self._get_my_hospital_id(doctor_id)

        contact = await self.repo.find_hospital_contact(request_id, hospital_id)
        if not contact:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="진료 요청이 존재하지 않습니다."
            )

        # 요청이 이미 끝난 상태면 연락 상태를 바꾸지 않고 막는다 (취소·다른 병원과 연결·만료)
        request = contact.request
        if request.status == CareRequestStatus.CANCELLED:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=CANCELLED_DETAIL)
        if request.status in HOSPITAL_VISIBLE_STATUSES:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=ALREADY_CONNECTED_DETAIL)
        if request.status != CareRequestStatus.CONTACTING:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=RESPOND_CLOSED_DETAIL)

        now = now_kst()
        deadline = now - timedelta(seconds=CARE_REQUEST_TIMEOUT_SECONDS)
        contact_status = (
            RequestContactStatus.AVAILABLE if dto.response == "available" else RequestContactStatus.DECLINED
        )

        if not await self.repo.mark_contact_response(
            request_id, hospital_id, doctor_id, contact_status, now, deadline
        ):
            await self.repo.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=RESPOND_CLOSED_DETAIL)

        notifications: list[dict] = []
        if contact_status == RequestContactStatus.AVAILABLE:
            if not await self.repo.connect_request(request_id, hospital_id):
                # 다른 병원이 먼저 연결됨 -> 우리 응답도 되돌린다
                await self.repo.rollback()
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=ALREADY_CONNECTED_DETAIL)
            notifications.append(_build_notification(
                request.patient_id, "병원이 연락 가능해요",
                f"{contact.hospital.name}에서 연락 가능하다고 답했어요. 채팅으로 예약 시간을 정해 보세요.",
                now, request_id
            ))
        else:
            for expired_id, patient_id in await self.repo.expire_exhausted_requests(request_id):
                notifications.append(_expired_notification(patient_id, expired_id, now))

        await self.repo.create_notifications(notifications)  # 연락·요청 변경과 알림을 한 번에 commit

        return self._to_hospital_dto(await self.repo.find_hospital_contact(request_id, hospital_id))

    # ------------------------------------------------------------
    # 예약 채팅 (3단계, 연결-05, 화면-26)
    # - 실시간 전송은 이번 범위가 아니다. 프론트는 afterId로 폴링한다. (임의 결정 D-58)
    #   TODO: 채팅 실시간 전송(WebSocket)
    # - 전화는 앱에서 병원 번호로 거는 것뿐, 서버에 저장하지 않는다. (결정-47)
    # ------------------------------------------------------------

    # 요청 + 참여자 확인 -> (요청, 내 역할)
    # - 참여자: 요청한 환자 + 연결된 병원(matched_hospital_id) 소속 의사. 그 밖은 403 (연결-05 예외·규칙)
    async def _get_chat_request(self, current_user: UserClaimDTO, request_id: int) -> tuple[CareRequest, UserRole]:
        request = await self.repo.find_request(request_id)
        if not request:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="진료 요청이 존재하지 않습니다."
            )

        if current_user.role == UserRole.PATIENT and request.patient_id == current_user.id:
            return request, UserRole.PATIENT

        if current_user.role == UserRole.DOCTOR and request.matched_hospital_id is not None:
            if await self.repo.find_doctor_hospital_id(current_user.id) == request.matched_hospital_id:
                return request, UserRole.DOCTOR

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="채팅 참여자가 아닙니다."
        )

    # 메시지를 보낼 수 있는지
    # - connected: 가능 / booked: 예약 진료일(KST)이 끝날 때까지 (결정-47) / 그 밖: 불가
    # - booked인데 남은 예약이 없으면(모두 취소) 불가
    async def _can_send(self, request: CareRequest, now: datetime) -> bool:
        if request.status == CareRequestStatus.CONNECTED:
            return True
        if request.status != CareRequestStatus.BOOKED:
            return False
        scheduled_at = await self.repo.find_latest_appointment_at(request.request_id)
        return scheduled_at is not None and now.astimezone(KST).date() <= scheduled_at.astimezone(KST).date()

    @staticmethod
    def _to_message_dto(message: RequestMessage, patient_id: int) -> RequestMessageDTO:
        return RequestMessageDTO(
            message_id=message.message_id,
            sender_id=message.sender_id,
            sender_role=UserRole.PATIENT if message.sender_id == patient_id else UserRole.DOCTOR,
            content=message.content,
            created_at=message.created_at,
            read_at=message.read_at,
        )

    # GET /care-requests/{request_id}/messages?afterId=
    # - 상대가 보낸 안 읽은 메시지의 read_at을 먼저 채우고 목록을 돌려준다.
    async def get_messages(
        self, current_user: UserClaimDTO, request_id: int, after_id: int | None
    ) -> list[RequestMessageDTO]:
        request, my_role = await self._get_chat_request(current_user, request_id)

        await self.repo.mark_messages_read(
            request_id, request.patient_id, from_patient=(my_role == UserRole.DOCTOR), now=now_kst()
        )
        messages = await self.repo.find_messages(request_id, after_id)
        return [self._to_message_dto(m, request.patient_id) for m in messages]

    # POST /care-requests/{request_id}/messages
    # - 상대 알림 (notification_type=chat, request_id)
    #   환자가 보내면: 연결을 수락한 의사 (없으면 병원 소속 의사 전원) / 의사가 보내면: 환자
    # - 알림에는 메시지 내용을 넣지 않는다. (잠금 화면 노출 방지)
    async def send_message(
        self, current_user: UserClaimDTO, request_id: int, dto: RequestMessageCreateDTO
    ) -> RequestMessageDTO:
        request, my_role = await self._get_chat_request(current_user, request_id)

        now = now_kst()
        if not await self._can_send(request, now):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="메시지를 보낼 수 없는 상태의 요청입니다."
            )

        request_code = f"R-{request.request_id:06d}"
        if my_role == UserRole.PATIENT:
            accepted_id = await self.repo.find_accepted_doctor_id(request_id, request.matched_hospital_id)
            if accepted_id is not None:
                receiver_ids = [accepted_id]
            else:
                doctor_ids = await self.repo.find_doctor_ids_by_hospital([request.matched_hospital_id])
                receiver_ids = doctor_ids.get(request.matched_hospital_id, [])
            title, content = "새 메시지가 도착했어요", f"환자가 메시지를 보냈어요. ({request_code})"
        else:
            receiver_ids = [request.patient_id]
            title, content = "새 메시지가 도착했어요", f"{request.matched_hospital.name}에서 메시지를 보냈어요."

        notifications = [
            _build_notification(receiver_id, title, content, now, request_id, NotificationType.CHAT)
            for receiver_id in receiver_ids
        ]
        message = await self.repo.create_message(
            {"request_id": request_id, "sender_id": current_user.id, "content": dto.content, "created_at": now},
            notifications,
        )
        return self._to_message_dto(message, request.patient_id)

    # ------------------------------------------------------------
    # 예약 확정 (4단계, 연결-06·07, 화면-27)
    # ------------------------------------------------------------

    # POST /doctor/care-requests/{request_id}/appointment (한 트랜잭션)
    # - 예약 1건 + 환자·의사 일정 2건 + 요청 booked + 환자 알림 1건 (doctor_repository.create_appointment)
    # - 예약 변경·취소·진료 완료는 기존 F-07 API를 그대로 쓴다.
    async def create_appointment(
        self, doctor_id: int, request_id: int, dto: CareRequestAppointmentCreateDTO
    ) -> AppointmentDetailResponseDTO:
        hospital_id = await self._get_my_hospital_id(doctor_id)

        request = await self.repo.find_request(request_id)
        if not request:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="진료 요청이 존재하지 않습니다."
            )
        if request.matched_hospital_id != hospital_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="연결된 병원의 의사만 예약할 수 있습니다."
            )
        if request.status != CareRequestStatus.CONNECTED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="예약을 확정할 수 없는 상태의 요청입니다."
            )

        # 진료실은 내 병원의 사용 중인 방만 (F-07과 같은 규칙)
        if dto.room_id is not None:
            room = await self.doctor_repo.find_room(dto.room_id)
            if not room or room.hospital_id != hospital_id or not room.is_active:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="사용할 수 없는 진료실입니다."
                )

        # 시간 검증은 F-07 그대로: 끝 > 시작, 지난 시각 400, 같은 시간 내 예약·진료실 겹침 409 (결정-48)
        start = dto.scheduled_at
        end = dto.end_at or start + timedelta(minutes=DEFAULT_APPOINTMENT_MINUTES)
        await self.doctor_service._check_time(doctor_id, dto.room_id, start, end)

        visited = await self.doctor_repo.has_completed_visit(request.patient_id, hospital_id)
        schedule_type, title = SCHEDULE_BY_KIND[dto.kind]

        appointment_id = await self.doctor_repo.create_appointment(
            {
                "patient_id": request.patient_id,
                "doctor_id": doctor_id,
                "hospital_id": hospital_id,
                "request_id": request_id,
                "contact_method": dto.contact_method,
                "scheduled_at": start,
                "end_at": end,
                "kind": dto.kind,
                "room_id": dto.room_id,
                "visit_type": AppointmentVisitType.RETURN if visited else AppointmentVisitType.FIRST,
                "status": AppointmentStatus.BOOKED,
                "booking_source": AppointmentBookingSource.DOCTOR,
                "created_by": doctor_id,
            },
            schedule_type,
            title,
            request_id=request_id,
            notify_title=f"진료 예약이 확정됐어요: {_format_kst(start)}",
        )
        if appointment_id is None:
            # 확인한 뒤 환자가 취소했거나 같은 병원 다른 의사가 먼저 확정함 (create_appointment가 rollback)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="예약을 확정할 수 없는 상태의 요청입니다."
            )

        return self.doctor_service._to_appointment_detail(await self.doctor_repo.find_appointment(appointment_id))

    # ------------------------------------------------------------
    # 진료 후 담당 등록 (5단계, 연결-09)
    # - 진료 완료(연결-08)는 기존 PUT /doctor/appointments/{id}/status (completed / no_show)
    # - TODO: 담당 등록에 의사 동의를 받을지 (결정-49)
    # ------------------------------------------------------------

    @staticmethod
    def _to_relation_dto(relation) -> CareRelationResponseDTO:
        return CareRelationResponseDTO(
            relation_id=relation.relation_id,
            doctor_id=relation.doctor_id,
            doctor_name=relation.doctor.name if relation.doctor else None,
            started_at=relation.started_at,
        )

    # POST /care-requests/appointments/{appointment_id}/register
    # - register: 기존 담당 관계는 끝내고 예약 의사와 새 관계 (이미 그 의사가 담당이면 그대로)
    # - once: 아무것도 만들지 않는다 (None)
    async def register_after_visit(
        self, current_user: UserClaimDTO, appointment_id: int, dto: CareRelationRegisterDTO
    ) -> CareRelationResponseDTO | None:
        self._ensure_patient(current_user)
        patient_id = current_user.id

        appointment = await self.repo.find_appointment(appointment_id)
        if not appointment or appointment.patient_id != patient_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="예약이 존재하지 않습니다."
            )
        if appointment.status != AppointmentStatus.COMPLETED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="진료를 마친 예약만 선택할 수 있습니다."
            )

        if dto.choice == "once":
            return None

        # 같은 환자가 동시에 눌러도 담당 관계가 2건 생기지 않게 줄 세운다
        await self.repo.lock_patient(patient_id)
        current = await self.repo.find_current_relation(patient_id)
        if current and current.doctor_id == appointment.doctor_id:
            # 바꿀 것 없음: DTO를 먼저 만들고 lock만 풀어 준다 (rollback하면 세션 객체가 만료된다)
            relation = self._to_relation_dto(current)
            await self.repo.rollback()
            return relation

        await self.repo.register_relation(patient_id, appointment.doctor_id, now_kst())
        return self._to_relation_dto(await self.repo.find_current_relation(patient_id))

    # ------------------------------------------------------------
    # 빠른 진료 예약 (5단계, 연결-10): 담당 의사에게 직접
    # - 진행 중 요청·위기 확인은 주변 병원 요청과 같다.
    # - 주변 병원 연락 없이 담당 의사 병원에 연락 1건 + 그 의사에게만 알림. 60초 무응답 규칙도 같다. (임의 결정 D-59)
    # - 이후 응답·채팅·예약 확정은 2~4단계와 같다. (연락은 병원 단위라 같은 병원 다른 의사도 목록에서 볼 수 있다)
    # ------------------------------------------------------------

    async def create_direct_request(
        self, current_user: UserClaimDTO, dto: CareRequestDirectCreateDTO
    ) -> CareRequestResponseDTO:
        patient_id = await self._begin_request(current_user)

        relation = await self.repo.find_current_relation(patient_id)
        if not relation:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="담당 의사가 없습니다."
            )
        hospital_id = await self.repo.find_doctor_hospital_id(relation.doctor_id)
        if hospital_id is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="담당 의사의 병원 정보가 없습니다."
            )

        now = now_kst()
        values = {
            "patient_id": patient_id,
            "target_doctor_id": relation.doctor_id,
            "request_mode": CareRequestMode.DIRECT,
            "request_type": dto.request_type,
            "preferred_time": dto.preferred_time,
            "memo": dto.memo,
            "created_at": now,
        }

        crisis = await self._save_crisis_if_needed(values, now)
        if crisis:
            return crisis

        request_id = await self.repo.save_request(
            {**values, "status": CareRequestStatus.CONTACTING},
            [hospital_id],
            [_new_request_notification(relation.doctor_id, dto.request_type, "담당 환자가", now)],
            now,
        )
        return self._to_response(await self.repo.find_request(request_id))


# ============================================================
# 무응답 스케줄러 (연결-02 예외, 결정-45 수정)
# - 일정 알림 스케줄러(schedule_reminder_service.py)와 같은 방식: asyncio 루프 + advisory lock
# - 10초마다 실행한다. 60초 기준을 최대 10초 늦게 처리한다. (임의 결정 D-54)
# ============================================================

class CareRequestExpireService:

    def __init__(self, repo: CareRequestRepository):
        self.repo = repo

    async def run_once(self, now: datetime | None = None) -> CareRequestExpireRunResultDTO:
        now = now or now_kst()

        if not await self.repo.try_acquire_lock():
            return CareRequestExpireRunResultDTO(
                lock_acquired=False, expired_contact_count=0, expired_request_count=0
            )

        # 1. sent_at <= now - 60초 인 sent 연락 -> no_response
        deadline = now - timedelta(seconds=CARE_REQUEST_TIMEOUT_SECONDS)
        contact_count = await self.repo.expire_no_response_contacts(deadline)

        # 2. 남은 sent 연락이 없는 contacting 요청 -> expired + 환자 알림
        expired = await self.repo.expire_exhausted_requests()
        rows = [_expired_notification(patient_id, request_id, now) for request_id, patient_id in expired]
        await self.repo.create_notifications(rows)  # 1·2번 변경과 알림을 한 번에 commit

        return CareRequestExpireRunResultDTO(
            lock_acquired=True,
            expired_contact_count=contact_count,
            expired_request_count=len(expired),
        )


async def run_care_request_expire_loop(
    session_factory: async_sessionmaker[AsyncSession],
    interval_seconds: int = 10
) -> None:
    while True:
        try:
            # 루프마다 세션을 새로 연다 (오래 열어 둔 세션·트랜잭션이 남지 않게)
            async with session_factory() as db:
                service = CareRequestExpireService(CareRequestRepository(db))
                result = await service.run_once()

            if result.expired_contact_count > 0 or result.expired_request_count > 0:
                print(f"진료 요청 무응답 처리: 연락 {result.expired_contact_count}건, 요청 {result.expired_request_count}건")

        except Exception:
            logger.exception("진료 요청 무응답 스케줄러 실행 중 오류")

        await asyncio.sleep(interval_seconds)


def get_care_request_service(
    repo: CareRequestRepository = Depends(get_care_request_repository),
    doctor_repo: DoctorRepository = Depends(get_doctor_repository),
):
    return CareRequestService(repo, doctor_repo)
