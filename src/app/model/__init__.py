from .default_model import Default

# 서버가 켜질 때 Base.metadata에 모든 테이블이 등록되도록 전부 import한다.
# 다른 테이블이 많이 참조하는 테이블
from .user_model import User
from .hospital_model import Hospital
from .rag_document_model import RagDocument
from .checklist_item_model import ChecklistItem
from .item_model import Item
from .mission_model import Mission
from .flower_model import Flower
from .mood_model import Mood

# user
from .doctor_profile_model import DoctorProfile
from .care_relation_model import CareRelation
from .attendance_model import Attendance
from .admin_model import Admin
from .doctor_verification_model import DoctorVerification

# chat
from .chat_session_model import ChatSession
from .message_model import Message
from .session_summary_model import SessionSummary
from .session_document_model import SessionDocument
from .llm_call_model import LlmCall
from .guard_check_model import GuardCheck
from .emotion_analysis_model import EmotionAnalysis

# rag
from .rag_chunk_model import RagChunk

# checklist
from .session_checklist_model import SessionChecklist
from .checklist_event_model import ChecklistEvent
from .assessment_result_model import AssessmentResult

# risk
from .risk_event_model import RiskEvent
from .risk_event_action_model import RiskEventAction
from .daily_risk_score_model import DailyRiskScore

# record
from .diary_model import Diary
from .diary_analysis_model import DiaryAnalysis
from .emotion_record_model import EmotionRecord
from .sleep_record_model import SleepRecord
from .exercise_record_model import ExerciseRecord

# hospital
from .room_model import Room
from .patient_chart_model import PatientChart
from .doctor_memo_model import DoctorMemo

# care_request
from .care_request_model import CareRequest
from .request_contact_model import RequestContact
from .request_message_model import RequestMessage

# appointment
from .appointment_model import Appointment
from .appointment_change_model import AppointmentChange
from .schedule_model import Schedule

# notification
from .notification_model import Notification

# reward
from .user_item_stackable_model import UserItemStackable
from .user_item_unique_model import UserItemUnique
from .myroom_entity_model import MyroomEntity
from .point_history_model import PointHistory

# collection
from .character_model import Character
from .flower_collection_model import FlowerCollection
from .mood_collection_model import MoodCollection
from .item_collection_model import ItemCollection
