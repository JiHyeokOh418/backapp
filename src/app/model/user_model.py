from datetime import datetime, date, timedelta, timezone
from sqlalchemy import BigInteger, String, Integer, Date, DateTime, Identity, ForeignKey, UniqueConstraint, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.enum.user_enum import UserRole, SocialProvider, Gender

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.model.doctor_profile_model import DoctorProfile
    from app.model.care_relation_model import CareRelation
    from app.model.attendance_model import Attendance
    from app.model.chat_session_model import ChatSession
    from app.model.assessment_result_model import AssessmentResult
    from app.model.risk_event_model import RiskEvent
    from app.model.daily_risk_score_model import DailyRiskScore
    from app.model.diary_model import Diary
    from app.model.emotion_record_model import EmotionRecord
    from app.model.sleep_record_model import SleepRecord
    from app.model.exercise_record_model import ExerciseRecord
    from app.model.patient_chart_model import PatientChart
    from app.model.doctor_memo_model import DoctorMemo
    from app.model.care_request_model import CareRequest
    from app.model.request_message_model import RequestMessage
    from app.model.appointment_model import Appointment
    from app.model.schedule_model import Schedule
    from app.model.notification_model import Notification
    from app.model.user_item_stackable_model import UserItemStackable
    from app.model.user_item_unique_model import UserItemUnique
    from app.model.myroom_entity_model import MyroomEntity
    from app.model.point_history_model import PointHistory
    from app.model.character_model import Character
    from app.model.flower_collection_model import FlowerCollection
    from app.model.mood_collection_model import MoodCollection
    from app.model.item_collection_model import ItemCollection

KST = timezone(timedelta(hours=9)) # UTC+9

# 사용자
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    nickname: Mapped[str | None] = mapped_column(String(50))
    role: Mapped[UserRole] = mapped_column(
        SQLEnum(UserRole, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=UserRole.PATIENT
    )
    doctor_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), index=True)
    social_provider: Mapped[SocialProvider] = mapped_column(
        SQLEnum(SocialProvider, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )
    social_id: Mapped[str | None] = mapped_column(String(100))
    name: Mapped[str | None] = mapped_column(String(50))
    gender: Mapped[Gender | None] = mapped_column(
        SQLEnum(Gender, native_enum=False, values_callable=lambda e: [m.value for m in e])
    )
    birth_date: Mapped[date | None] = mapped_column(Date)
    point_balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0) # 현재 포인트
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(KST)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(KST),
        onupdate=lambda: datetime.now(KST)
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("social_provider", "social_id", name="uq_users_social_provider_social_id"),
    )

    # 관계
    # cascade: User가 삭제되면 참조된 테이블을 모두 같이 연쇄삭제
    doctor_profile: Mapped["DoctorProfile | None"] = relationship(
        "DoctorProfile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    patient_care_relations: Mapped[list["CareRelation"]] = relationship(
        "CareRelation", back_populates="patient", foreign_keys="CareRelation.patient_id", cascade="all, delete-orphan"
    )
    doctor_care_relations: Mapped[list["CareRelation"]] = relationship(
        "CareRelation", back_populates="doctor", foreign_keys="CareRelation.doctor_id", cascade="all, delete-orphan"
    )
    attendances: Mapped[list["Attendance"]] = relationship(
        "Attendance", back_populates="user", cascade="all, delete-orphan"
    )
    chat_sessions: Mapped[list["ChatSession"]] = relationship(
        "ChatSession", back_populates="user", cascade="all, delete-orphan"
    )
    assessment_results: Mapped[list["AssessmentResult"]] = relationship(
        "AssessmentResult", back_populates="user", cascade="all, delete-orphan"
    )
    risk_events: Mapped[list["RiskEvent"]] = relationship(
        "RiskEvent", back_populates="user", foreign_keys="RiskEvent.user_id", cascade="all, delete-orphan"
    )
    daily_risk_scores: Mapped[list["DailyRiskScore"]] = relationship(
        "DailyRiskScore", back_populates="user", cascade="all, delete-orphan"
    )
    diaries: Mapped[list["Diary"]] = relationship(
        "Diary", back_populates="user", cascade="all, delete-orphan"
    )
    emotion_records: Mapped[list["EmotionRecord"]] = relationship(
        "EmotionRecord", back_populates="user", cascade="all, delete-orphan"
    )
    sleep_records: Mapped[list["SleepRecord"]] = relationship(
        "SleepRecord", back_populates="user", cascade="all, delete-orphan"
    )
    exercise_records: Mapped[list["ExerciseRecord"]] = relationship(
        "ExerciseRecord", back_populates="user", cascade="all, delete-orphan"
    )
    patient_charts: Mapped[list["PatientChart"]] = relationship(
        "PatientChart", back_populates="patient", cascade="all, delete-orphan"
    )
    patient_memos: Mapped[list["DoctorMemo"]] = relationship(
        "DoctorMemo", back_populates="patient", foreign_keys="DoctorMemo.patient_id", cascade="all, delete-orphan"
    )
    doctor_memos: Mapped[list["DoctorMemo"]] = relationship(
        "DoctorMemo", back_populates="doctor", foreign_keys="DoctorMemo.doctor_id", cascade="all, delete-orphan"
    )
    care_requests: Mapped[list["CareRequest"]] = relationship(
        "CareRequest", back_populates="patient", foreign_keys="CareRequest.patient_id", cascade="all, delete-orphan"
    )
    request_messages: Mapped[list["RequestMessage"]] = relationship(
        "RequestMessage", back_populates="sender", cascade="all, delete-orphan"
    )
    patient_appointments: Mapped[list["Appointment"]] = relationship(
        "Appointment", back_populates="patient", foreign_keys="Appointment.patient_id", cascade="all, delete-orphan"
    )
    doctor_appointments: Mapped[list["Appointment"]] = relationship(
        "Appointment", back_populates="doctor", foreign_keys="Appointment.doctor_id", cascade="all, delete-orphan"
    )
    schedules: Mapped[list["Schedule"]] = relationship(
        "Schedule", back_populates="user", foreign_keys="Schedule.user_id", cascade="all, delete-orphan"
    )
    notifications: Mapped[list["Notification"]] = relationship(
        "Notification", back_populates="user", cascade="all, delete-orphan"
    )
    stackable_items: Mapped[list["UserItemStackable"]] = relationship(
        "UserItemStackable", back_populates="user", cascade="all, delete-orphan"
    )
    unique_items: Mapped[list["UserItemUnique"]] = relationship(
        "UserItemUnique", back_populates="user", cascade="all, delete-orphan"
    )
    myroom_entities: Mapped[list["MyroomEntity"]] = relationship(
        "MyroomEntity", back_populates="user", cascade="all, delete-orphan"
    )
    point_histories: Mapped[list["PointHistory"]] = relationship(
        "PointHistory", back_populates="user", cascade="all, delete-orphan"
    )
    characters: Mapped[list["Character"]] = relationship(
        "Character", back_populates="user", cascade="all, delete-orphan"
    )
    flower_collections: Mapped[list["FlowerCollection"]] = relationship(
        "FlowerCollection", back_populates="user", cascade="all, delete-orphan"
    )
    mood_collections: Mapped[list["MoodCollection"]] = relationship(
        "MoodCollection", back_populates="user", cascade="all, delete-orphan"
    )
    item_collections: Mapped[list["ItemCollection"]] = relationship(
        "ItemCollection", back_populates="user", cascade="all, delete-orphan"
    )
