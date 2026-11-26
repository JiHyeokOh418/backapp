from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Annotated, Literal
from pydantic import AwareDatetime, Field, PlainSerializer, StringConstraints
from app.schema.common_schema import BaseDTO
from app.schema.doctor_schema import DoctorPatientBriefDTO
from app.enums.care_request_enum import CareRequestMode, CareRequestType, CareRequestStatus
from app.enums.request_contact_enum import RequestContactStatus
from app.enums.user_enum import UserRole
from app.enums.appointment_enum import AppointmentContactMethod, AppointmentKind

KST = timezone(timedelta(hours=9)) # UTC+9

# 시각은 KST(+09:00)로 내려준다 (schedule_reminder_schema.py와 같은 방식)
KstDateTime = Annotated[datetime, PlainSerializer(lambda v: v.astimezone(KST), return_type=datetime)]


# ============================================================
# 1단계: 진료 요청 (연결-01·02)
# ============================================================

# 진료 요청 (POST /care-requests)
# - latitude·longitude는 필수: 반경 계산에 쓴다. 프론트가 위치 허용 또는 주소 변환으로 채운다. (임의 결정 D-52)
# - memo: 명세는 500자지만 care_requests.memo 컬럼이 String(255)라서 255자로 맞춘다.
class CareRequestCreateDTO(BaseDTO):
    request_type: CareRequestType
    address: str | None = Field(default=None, max_length=255)   # 상세 주소 (병원에는 보여주지 않는다)
    sido: str = Field(min_length=1, max_length=20)              # 시·도
    sigungu: str = Field(min_length=1, max_length=30)           # 시·군·구
    latitude: Decimal = Field(ge=-90, le=90)                    # 위도
    longitude: Decimal = Field(ge=-180, le=180)                 # 경도
    preferred_time: str | None = Field(default=None, max_length=50)  # 희망 시간대 (예: "오늘 오후")
    memo: str | None = Field(default=None, max_length=255)      # 요청 메모


# 연결된 병원 (connected·booked일 때만 내려준다)
class ConnectedHospitalDTO(BaseDTO):
    hospital_id: int
    name: str
    phone: str | None
    address: str


# 진료 요청 응답 (환자용)
# - 위험도·위험 기록은 어떤 필드로도 내려 주지 않는다. (공통-05)
# - status가 crisis면 프론트는 위기 안내 화면을 띄운다. (위험도 문구 없이)
class CareRequestResponseDTO(BaseDTO):
    request_id: int
    request_type: CareRequestType
    request_mode: CareRequestMode
    status: CareRequestStatus
    preferred_time: str | None
    memo: str | None
    created_at: KstDateTime
    contact_count: int                          # 연락한 병원 수
    expires_at: KstDateTime | None              # 응답 기한 = 가장 늦게 보낸 연락의 sent_at + 제한 시간
    hospital: ConnectedHospitalDTO | None = None


# ============================================================
# 2단계: 병원 측 요청 목록 + 응답 (연결-03·04, 화면-30)
# ============================================================

# 목록 탭 (GET /doctor/care-requests?tab=)
# - pending: 응답 기다리는 중 / connected: 우리 병원과 연결됨 / closed: 그 밖 (최근 30일)
HospitalCareRequestTab = Literal["pending", "connected", "closed"]


# 병원 측 요청 1건 (내 병원의 연락 내역 기준)
# - patient: 우리 병원과 연결된 뒤에만 이름을 채운다. 그 전에는 null (결정-41·50) (임의 결정 D-56)
# - 상세 주소·위도·경도·위험 기록은 내려 주지 않는다.
class HospitalCareRequestDTO(BaseDTO):
    request_id: int
    request_code: str                           # "R-" + request_id 6자리 (예: R-000123)
    request_type: CareRequestType
    sido: str | None
    sigungu: str | None
    preferred_time: str | None
    memo: str | None
    request_status: CareRequestStatus           # 요청 전체 상태
    contact_status: RequestContactStatus        # 우리 병원 연락 상태
    sent_at: KstDateTime
    expires_at: KstDateTime                     # sent_at + 응답 제한 시간
    responded_at: KstDateTime | None
    patient: DoctorPatientBriefDTO | None = None


# 가능·불가 응답 (POST /doctor/care-requests/{request_id}/respond)
class CareRequestRespondDTO(BaseDTO):
    response: Literal["available", "declined"]


# ============================================================
# 3단계: 예약 채팅 (연결-05, 화면-26)
# ============================================================

# 메시지 보내기 (POST /care-requests/{request_id}/messages)
# - 앞뒤 공백을 지운 뒤 1~1000자 (공백만 보내면 422)
class RequestMessageCreateDTO(BaseDTO):
    content: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


# 메시지 1건
class RequestMessageDTO(BaseDTO):
    message_id: int
    sender_id: int
    sender_role: UserRole       # patient / doctor
    content: str
    created_at: KstDateTime
    read_at: KstDateTime | None


# ============================================================
# 4단계: 예약 확정 (연결-06·07, 화면-27)
# - 응답은 F-07과 같은 AppointmentDetailResponseDTO (doctor_schema.py)
# ============================================================

# 예약 확정 (POST /doctor/care-requests/{request_id}/appointment)
class CareRequestAppointmentCreateDTO(BaseDTO):
    scheduled_at: AwareDatetime
    end_at: AwareDatetime | None = None             # 없으면 시작 + 30분 (D-22와 같은 규칙)
    contact_method: AppointmentContactMethod        # phone / chat (필수)
    kind: AppointmentKind = AppointmentKind.TREATMENT
    room_id: int | None = None


# ============================================================
# 5단계: 진료 후 담당 등록 + 빠른 진료 예약 (연결-09·10)
# ============================================================

# 진료 후 선택 (POST /care-requests/appointments/{appointment_id}/register)
# - register: 이 의사를 담당으로 등록 / once: 이번 한 번만 (아무것도 만들지 않음)
class CareRelationRegisterDTO(BaseDTO):
    choice: Literal["register", "once"]


# 담당 관계 응답
class CareRelationResponseDTO(BaseDTO):
    relation_id: int
    doctor_id: int
    doctor_name: str | None
    started_at: KstDateTime


# 담당 의사에게 직접 요청 (POST /care-requests/direct)
# - 위치를 받지 않는다. 주변 병원 연락 없이 담당 의사의 병원에만 연락한다.
class CareRequestDirectCreateDTO(BaseDTO):
    request_type: CareRequestType
    preferred_time: str | None = Field(default=None, max_length=50)
    memo: str | None = Field(default=None, max_length=255)   # care_requests.memo가 String(255)


# 무응답 스케줄러 1회 실행 결과 (로그·테스트 확인용)
class CareRequestExpireRunResultDTO(BaseDTO):
    lock_acquired: bool          # 다른 워커가 실행 중이라 건너뛰었으면 False
    expired_contact_count: int   # 이번에 no_response로 바꾼 연락 수
    expired_request_count: int   # 이번에 expired로 바꾼 요청 수
