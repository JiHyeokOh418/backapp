from typing import Any

from fastapi import Depends

from app.repository.llm_repository import LlmRepository, get_llm_repository
from app.model.chat_session_model import ChatSession
from app.model.message_model import Message
from app.model.session_checklist_model import SessionChecklist
from app.enum.chat_enum import InputType
from app.schema.llm_schema import (
    LlmReplyOutput,
    ScheduledSessionCreateDTO,
    ChatSessionResponseDTO,
    MainSessionResponseDTO,
    MessageListResponseDTO,
    SendMessageResponseDTO,
)

# LLM 호출 + 검증을 반복하는 최대 횟수 (첫 호출 포함)
# TODO: 임시값. 확정 필요
MAX_LLM_ATTEMPTS = 3

# 세션 종료 판정에 필요한 최소 사용자 메시지 수
# TODO: 임시값. 확정 필요
MIN_USER_TURNS = 3


# 예외처리
# 트랜잭션 관리 (commit / rollback은 이 service에서 정한다. repository는 flush까지만)
#
# 안전필터, 감정분석은 나중에 끼워 넣는다. (send_message 안의 표시된 위치)
# 세션 요약, 타임아웃 배치는 repository 함수가 추가된 뒤에 구현한다. (파일 맨 아래 메모)
class LlmService:

    def __init__(self, repo: LlmRepository):
        self.repo = repo


    # 1. 의사: 예정 세션 생성 (한 번 호출에 세션 1건)
    # - 담당 환자인지 확인(exists_care_relation)은 현재 llm_repository에 없다. (memo_repository에 있음)
    # - 직전 세션: find_latest_session_summary(user_id)로 환자의 가장 최근 세션 요약을 찾아
    #   그 session_id를 prev_session_id로 넣는다. 없으면 None
    #   (요약이 아직 없는 세션은 직전 세션으로 잡히지 않는다)
    # - 체크리스트: find_checklist_items로 항목 검증(없거나 is_active=False면 거절)
    #   -> create_session_checklist(required, sort_order 포함)
    # - 한 트랜잭션으로 묶어 commit
    async def create_scheduled_session(
        self,
        doctor_id: int,
        request: ScheduledSessionCreateDTO,
    ) -> ChatSessionResponseDTO:
        pass


    # 2. 환자: 상담 메인 (진행 중 세션, 없으면 다음 예정 세션)
    # - available(지금 접속 가능 여부)은 service가 scheduled_at과 비교해 계산
    async def get_main_session(self, user_id: int) -> MainSessionResponseDTO | None:
        pass


    # 3. 환자: 세션 시작 (SCHEDULED -> ACTIVE)
    async def start_session(self, user_id: int, session_id: int) -> ChatSessionResponseDTO:
        pass


    # 4. 환자: 세션 직접 종료 (ACTIVE -> ENDED, end_reason=USER)
    async def end_session_by_user(self, user_id: int, session_id: int) -> ChatSessionResponseDTO:
        pass


    # 5. 환자: 화면용 대화 기록 조회 (커서 방식)
    async def get_messages(
        self,
        user_id: int,
        session_id: int,
        after_seq: int | None,
        limit: int,
    ) -> MessageListResponseDTO:
        pass


    # 6. 환자: 사용자 메시지 전송 (한 턴 전체를 처리하고 AI 답변과 세션 상태를 반환)
    #
    # [트랜잭션 1: 세션 잠금]
    #  - _get_locked_active_session으로 잠금 조회 (본인 세션, ACTIVE)
    #  - 재전송 확인: find_message_by_client_id가 있으면 _find_reply로 기존 답변을 돌려주고 끝
    #  - 사용자 메시지 저장(create_message), commit (잠금 해제)
    #  - (나중에) 입력 안전필터
    # [프롬프트 조립 + LLM 호출 / 검증 루프, 최대 MAX_LLM_ATTEMPTS회]
    #  - _build_prompt_context -> _call_llm -> _validate_llm_output
    #  - 오류가 있으면 _build_retry_feedback으로 사유를 만들어 다시 호출
    #  - 호출 기록은 메모리에 모은다. (답변 메시지가 생긴 뒤에 저장해야 llm_calls.message_id를 채울 수 있다)
    #  - 모두 실패하면 _build_fallback_reply 문구로 대체. 턴마다 답변 메시지는 반드시 1개 생긴다.
    # [트랜잭션 2: 재잠금 -> _save_turn_result -> commit]
    #  - (나중에) 출력 안전필터, 감정분석
    #  - 체크리스트 반영, 답변 메시지 저장, llm_calls 저장, 종료 판정
    # [응답]
    #  - 사용자에게 보일 값(답변, 표정)과 session_status만 내려준다. 체크리스트 값 등 내부 값은 제외.
    async def send_message(
        self,
        user_id: int,
        session_id: int,
        client_message_id: str,
        content: str,
        input_type: InputType,
    ) -> SendMessageResponseDTO:
        pass


    # 6-1. 턴 처리 내부: 프롬프트 재료 조회 (세션 원문, 체크리스트)
    async def _build_prompt_context(
        self, session_id: int
    ) -> tuple[list[Message], list[SessionChecklist]]:
        pass


    # 6-2. 턴 처리 내부: LLM 호출 1회 (재시도 루프는 send_message가 돈다)
    # - feedback: 이전 시도의 검증 실패 사유 (첫 호출은 None)
    # - 반환: (파싱된 출력, create_llm_call에 넘길 호출 기록). 파싱에 실패하면 출력은 None
    async def _call_llm(
        self,
        messages: list[Message],
        checklists: list[SessionChecklist],
        feedback: str | None,
        attempt: int,
    ) -> tuple[LlmReplyOutput | None, dict[str, Any]]:
        pass


    # 6-3. 턴 처리 내부: LLM 출력 검증
    # - item_id가 이 세션 항목인지, 상태 전이, value와 answer_type, skip_reason, evidence_seq(사용자 메시지) 확인
    # - 반환: 오류 목록 (비어 있으면 통과)
    async def _validate_llm_output(
        self,
        session_id: int,
        output: LlmReplyOutput,
        checklists: list[SessionChecklist],
    ) -> list[str]:
        pass


    # 6-4. 턴 처리 내부: 재호출용 실패 사유 문구 (순수 함수)
    def _build_retry_feedback(self, errors: list[str]) -> str:
        pass


    # 6-5. 턴 처리 내부: 모든 시도가 실패했을 때 사용자에게 보낼 고정 문구 (순수 함수)
    def _build_fallback_reply(self) -> str:
        pass


    # 6-6. 턴 처리 내부: 체크리스트 상태 반영 + 질문 횟수 증가 (asked_item_ids)
    async def _apply_checklist_changes(
        self,
        session_id: int,
        output: LlmReplyOutput,
        checklists: list[SessionChecklist],
    ) -> None:
        pass


    # 6-7. 턴 처리 내부: 필수 항목이 모두 done 또는 허용된 skipped인지 (순수 함수)
    # - counsel_end는 요청일 뿐이고, 종료는 이 결과(DB 상태)와 MIN_USER_TURNS로 service가 확정한다.
    def _is_checklist_complete(self, checklists: list[SessionChecklist]) -> bool:
        pass


    # 6-8. 턴 처리 내부: 재전송 시 기존 AI 답변 조회 (사용자 메시지 seq + 1)
    async def _find_reply(self, session_id: int, user_message: Message) -> Message | None:
        pass


    # 6-9. 턴 처리 내부: 트랜잭션 2 저장 묶음
    # - 체크리스트 반영, 답변 메시지 저장, llm_calls 저장(link), 종료 처리, commit
    # - output이 None이면(전부 실패) 고정 문구로 답변 메시지를 만든다.
    async def _save_turn_result(
        self,
        session: ChatSession,
        checklists: list[SessionChecklist],
        output: LlmReplyOutput | None,
        llm_call_records: list[dict[str, Any]],
    ) -> Message:
        pass


    # 6-10. 턴 처리 내부: 잠금 조회 (본인 세션, ACTIVE 상태 확인)
    async def _get_locked_active_session(self, user_id: int, session_id: int) -> ChatSession:
        pass


    # 보류 (repository 함수가 추가된 뒤에 구현)
    # - create_session_summary(session_id): upsert_session_summary 필요
    # - process_session_timeouts(now): expire_scheduled_sessions, end_stale_active_sessions 필요
    #
    # 추후 추가 (방치 세션 처리)
    # - expires_at(필수)은 최초 접속(start_session) 때 한 번만 검증한다. 시작한 뒤에는 expires_at을 다시 검증하지 않는다.
    # - 세션 상태(status)는 외부 표시용이다. 접속 가능 여부의 검증 기준으로 쓰지 않는다.
    # - 시작해 놓고 계속 열어 둔 채 방치된 ACTIVE 세션을 검증하고 정리하는 로직은 아직 없다.
    #   (마지막 활동 시각 기준, 정리 시 상태와 end_reason 처리, 요약 상태 처리 등을 정해서 추가할 예정)



# 레포지토리 주입 팩토리 함수
def get_llm_service(repo: LlmRepository = Depends(get_llm_repository)):
    return LlmService(repo)
