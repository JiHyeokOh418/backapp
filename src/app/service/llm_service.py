from datetime import datetime
from typing import Any, NoReturn

from fastapi import Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.repository.llm_repository import LlmRepository, get_llm_repository
from app.models.chat_session_model import ChatSession
from app.models.message_model import Message
from app.models.session_checklist_model import SessionChecklist
from app.models.session_summary_model import SessionSummary
from app.models.emotion_analysis_model import EmotionAnalysis
from app.enums.chat_session_enum import (
    ChatSessionEndReason,
    ChatSessionStatus,
    ChatSessionSummaryStatus,
    ChatSessionType,
)
from app.enums.message_enum import MessageInputType, MessageRole, MessageSystemRecordStatus
from app.enums.llm_call_enum import LlmCallParseStatus
from app.enums.common_enum import ChecklistStatus
from app.enums.session_checklist_enum import SessionChecklistSkipReason
from app.schema.llm_schema import (
    KST,
    LlmReplyOutput,
    LlmSummaryOutput,
    ScheduledSessionCreateDTO,
    ChatSessionResponseDTO,
    MainSessionResponseDTO,
    MessageResponseDTO,
    MessageListResponseDTO,
    SendMessageResponseDTO,
)

# LLM 호출 + 검증을 반복하는 최대 횟수 (첫 호출 1회 + 재시도 1회)
MAX_LLM_ATTEMPTS = 2

# 세션 종료 판정에 필요한 최소 사용자 메시지 수
# TODO: 임시값. 확정 필요
MIN_USER_TURNS = 3

# 필수 항목에서 "완료로 인정"하는 건너뜀 사유 (UNCLEAR는 인정하지 않고 재질문)
# TODO: 임시값. 확정 필요
ALLOWED_REQUIRED_SKIP_REASONS = {SessionChecklistSkipReason.USER_DECLINED, SessionChecklistSkipReason.NOT_APPLICABLE}

# 모든 LLM 시도가 실패했을 때 프론트에 내려줄 오류 문구 (messages에는 저장하지 않는다)
FALLBACK_REPLY_TEXT = "llm답변 오류!"

# 감정분석 6종 (emotion_analyses 컬럼명). 사후요약 LLM 입력에 메시지별로 붙인다.
EMOTION_FIELDS = ("anger", "joy", "anxiety", "embarrassment", "sadness", "hurt")


# 예외처리
# 트랜잭션 관리 (commit / rollback은 이 service에서 정한다. repository는 flush까지만)
#
# 안전필터, 감정분석은 나중에 끼워 넣는다. (send_message 안의 표시된 위치)
# 세션 사후요약은 6번(create_session_summary). 호출 위치는 아직 정하지 않았다.
# 타임아웃 배치는 repository 함수가 추가된 뒤에 구현한다. (파일 맨 아래 메모)
# 세션 종료 경로는 두 가지다. 둘 다 종료할 때 summary_status=PENDING을 넣는다. (종료 전에는 null)
# - 체크리스트 완료: send_message의 종료 판정 (end_reason=COMPLETED)
# - 중간 이탈: 프론트가 상담 화면을 떠날 때 end_session으로 통지 (end_reason=USER). 종료 버튼은 없다.
# - 시작한 적 없이 마감(expires_at)이 지난 예정 세션은 process_session_timeouts가 MISSED로 바꾼다. (요청 시 처리)
# - TIMEOUT은 나중에 강제 종료 등으로 방치된 ACTIVE 세션을 정리할 때 쓴다. (파일 맨 아래 메모, 지금은 다루지 않음)
class LlmService:

    def __init__(self, repo: LlmRepository):
        self.repo = repo


    # 예외가 나면 rollback하고 다시 던진다. (HTTPException 포함. 잠금도 함께 풀린다)
    async def _rollback_and_raise(self, error: Exception) -> NoReturn:
        await self.repo.rollback()
        raise error


    # 세션 ORM -> 응답 DTO
    @staticmethod
    def _to_session_response(session: ChatSession) -> ChatSessionResponseDTO:
        return ChatSessionResponseDTO.model_validate(session)


    # 지금 접속할 수 있는 시간대인지: scheduled_at <= 현재 < expires_at
    @staticmethod
    def _is_within_access_window(session: ChatSession, now: datetime) -> bool:
        if session.scheduled_at and now < session.scheduled_at:
            return False
        if session.expires_at and now >= session.expires_at:
            return False
        return True


    # 1. 의사: 예정 세션 생성 (한 번 호출에 세션 1건)
    # - 담당 환자인지 확인: exists_care_relation (아니면 403). 담당 관계는 이 함수에서 한 번만 검증한다.
    # - 접속 기간 중복 확인: exists_overlapping_session (같은 환자의 기존 세션과 겹치면 409)
    # - 직전 세션: find_latest_session_summary(user_id)로 환자의 가장 최근 세션 요약을 찾아
    #   그 session_id를 prev_session_id로 넣는다. 없으면 None
    #   (요약이 아직 없는 세션은 직전 세션으로 잡히지 않는다)
    # - 체크리스트: find_checklist_items로 항목 검증(없거나 is_active=False면 거절)
    #   -> create_session_checklist(required, sort_order 포함)
    #   sort_order는 NOT NULL이라, 요청에 없으면 요청 목록의 순서(1부터)로 채운다.
    # - summary_status는 넣지 않는다. (null, 세션이 종료될 때 PENDING이 된다)
    # - 한 트랜잭션으로 묶어 commit
    async def create_scheduled_session(
        self,
        doctor_id: int,
        request: ScheduledSessionCreateDTO,
    ) -> ChatSessionResponseDTO:
        try:
            # 1. 담당 환자 확인 (403)
            if not await self.repo.exists_care_relation(doctor_id, request.user_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="담당 환자가 아닙니다."
                )

            # 2. 접속 기간 중복 확인 (409)
            if await self.repo.exists_overlapping_session(
                request.user_id, request.scheduled_at, request.expires_at
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="해당 환자의 다른 세션과 접속 기간이 겹칩니다."
                )

            # 3. 체크리스트 항목 검증 (없거나 비활성이면 400)
            item_ids = [item.item_id for item in request.checklist_items]
            items = await self.repo.find_checklist_items(item_ids)
            if len(items) != len(item_ids) or any(not item.is_active for item in items):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="존재하지 않거나 사용할 수 없는 체크리스트 항목이 포함되어 있습니다."
                )

            # 4. 직전 세션 (없으면 None)
            latest_summary = await self.repo.find_latest_session_summary(request.user_id)
            prev_session_id = latest_summary.session_id if latest_summary else None

            # 5. 세션 + 체크리스트 생성
            session = ChatSession(
                user_id=request.user_id,
                prev_session_id=prev_session_id,
                status=ChatSessionStatus.SCHEDULED,
                session_type=request.session_type,
                scheduled_at=request.scheduled_at,
                expires_at=request.expires_at,
            )
            await self.repo.create_sessions([session])
            await self.repo.create_session_checklist(
                session.id,
                [
                    {
                        "item_id": item.item_id,
                        "required": item.required,
                        "sort_order": item.sort_order if item.sort_order is not None else index,
                    }
                    for index, item in enumerate(request.checklist_items, start=1)
                ],
            )
            await self.repo.commit()
        except Exception as error:
            await self._rollback_and_raise(error)

        return self._to_session_response(session)


    # 2. 환자: 상담 메인 (진행 중 세션, 없으면 다음 예정 세션)
    # - available(지금 접속 가능 여부)은 service가 scheduled_at과 비교해 계산
    # - 세션 상태를 화면에 보여 주는 요청이므로, 먼저 이 환자의 마감 지난 예정 세션을 MISSED로 정리한다. (7번)
    async def get_main_session(self, user_id: int) -> MainSessionResponseDTO | None:
        await self.process_session_timeouts(user_id)

        session = await self.repo.find_active_or_next_session(user_id)
        if session is None:
            return None

        # ACTIVE이면 항상 접속 가능, 예정 세션이면 접속 시간대 안인지 확인
        if session.status == ChatSessionStatus.ACTIVE:
            available = True
        else:
            available = self._is_within_access_window(session, datetime.now(KST))

        base = self._to_session_response(session)
        return MainSessionResponseDTO(**base.model_dump(), available=available)


    # 3. 환자: 세션 시작 (SCHEDULED -> ACTIVE)
    # - 본인 세션인지(user_id) 확인한다. 아니면 404
    # - expires_at 검증은 이때 한 번만 한다. (시작한 뒤에는 다시 검증하지 않는다)
    # - 환자당 ACTIVE 1개는 DB의 부분 unique 인덱스(uix_chat_sessions_user_active)로도 막힌다.
    #   다른 세션 두 개를 동시에 시작하면 exists_active_session을 둘 다 통과할 수 있는데,
    #   이때 뒤쪽 요청은 flush에서 IntegrityError가 나므로 409로 바꿔서 돌려준다.
    async def start_session(self, user_id: int, session_id: int) -> ChatSessionResponseDTO:
        try:
            session = await self.repo.find_session_by_id(session_id, user_id=user_id, for_update=True)
            if session is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="세션이 존재하지 않습니다."
                )
            if session.status != ChatSessionStatus.SCHEDULED:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="시작할 수 있는 상태의 세션이 아닙니다."
                )
            if await self.repo.exists_active_session(user_id):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="이미 진행 중인 세션이 있습니다."
                )

            now = datetime.now(KST)
            if session.scheduled_at and now < session.scheduled_at:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="아직 접속할 수 있는 시간이 아닙니다."
                )
            if session.expires_at and now >= session.expires_at:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="접속 가능 시간이 지났습니다."
                )

            await self.repo.update_session(session, status=ChatSessionStatus.ACTIVE, started_at=now)
            await self.repo.commit()
        except IntegrityError:
            await self._rollback_and_raise(HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="이미 진행 중인 세션이 있습니다."
            ))
        except Exception as error:
            await self._rollback_and_raise(error)

        return self._to_session_response(session)


    # 3-1. 환자: 세션 이탈 종료 (프론트가 상담 화면을 떠날 때 통지)
    # - 설계: AI 상담은 접속하면 끝날 때까지 진행한다. 중간에 나가면 그 세션은 종료된다.
    # - ACTIVE -> ENDED, end_reason=USER, ended_at=now, summary_status=PENDING (사후요약 대상)
    # - 이미 ENDED면 바꾸지 않고 현재 상태를 돌려준다. (체크리스트 완료 후 나가는 경우, 통지가 두 번 오는 경우)
    # - 그 밖의 상태(SCHEDULED 등)는 409
    # - 진행 중인 send_message가 있으면, 그 턴의 트랜잭션 2가 재잠금에서 409가 되어 답변은 저장되지 않는다.
    async def end_session(self, user_id: int, session_id: int) -> ChatSessionResponseDTO:
        try:
            session = await self.repo.find_session_by_id(session_id, user_id=user_id, for_update=True)
            if session is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="세션이 존재하지 않습니다."
                )

            if session.status == ChatSessionStatus.ACTIVE:
                await self.repo.update_session(
                    session,
                    status=ChatSessionStatus.ENDED,
                    end_reason=ChatSessionEndReason.USER,
                    ended_at=datetime.now(KST),
                    summary_status=ChatSessionSummaryStatus.PENDING,
                )
            elif session.status != ChatSessionStatus.ENDED:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="진행 중인 세션이 아닙니다."
                )

            await self.repo.commit() # 이미 ENDED면 변경 없이 잠금만 푼다.
        except Exception as error:
            await self._rollback_and_raise(error)

        return self._to_session_response(session)


    # 4. 환자: 화면용 대화 기록 조회 (커서 방식)
    async def get_messages(
        self,
        user_id: int,
        session_id: int,
        after_seq: int | None,
        limit: int,
    ) -> MessageListResponseDTO:
        # 본인 세션인지만 확인한다. (타인 세션도 404로 존재를 숨긴다)
        session = await self.repo.find_session_by_id(session_id, user_id=user_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="세션이 존재하지 않습니다."
            )

        messages, next_cursor = await self.repo.find_messages(session_id, after_seq, limit)
        return MessageListResponseDTO(
            items=[MessageResponseDTO.model_validate(message) for message in messages],
            next_cursor=next_cursor,
        )


    # 5. 환자: 사용자 메시지 전송 (한 턴 전체를 처리하고 AI 답변과 세션 상태를 반환)
    #
    # [트랜잭션 1: 세션 잠금]
    #  - _get_locked_active_session으로 잠금 조회 (본인 세션, ACTIVE)
    #  - 재전송 확인: find_message_by_client_id가 있으면 _find_reply로 기존 답변을 돌려주고 끝
    #  - 사용자 메시지 저장(create_message), commit (잠금 해제)
    #  - (나중에) 입력 안전필터
    # [프롬프트 조립 + LLM 호출 / 검증 루프, 최대 MAX_LLM_ATTEMPTS회]
    #  - _build_prompt_context -> _call_llm -> _validate_llm_output
    #  - 오류가 있으면 _build_retry_feedback으로 사유를 만들어 다시 호출
    #  - 호출 기록은 메모리에 모은다. (llm_calls.message_id가 NOT NULL이라 연결할 메시지가 정해진 뒤에 저장)
    #  - 모두 실패하면 _save_failed_turn: 오류 문구는 messages에 저장하지 않고 502 응답으로만 내려준다.
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
        input_type: MessageInputType,
    ) -> SendMessageResponseDTO:
        # --- 트랜잭션 1: 세션 잠금 -> 재전송 확인 -> 사용자 메시지 저장 ---
        try:
            session = await self._get_locked_active_session(user_id, session_id)

            # 재전송이면 이미 만든 답변을 그대로 돌려준다.
            existing = await self.repo.find_message_by_client_id(session_id, client_message_id)
            if existing is not None:
                reply = await self._find_reply(session_id, existing)
                if reply is None:
                    # 같은 메시지를 아직 처리 중이거나, LLM 오류로 답변을 만들지 못한 메시지
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="이미 처리 중이거나 답변을 만들지 못한 메시지입니다."
                    )
                response = SendMessageResponseDTO(
                    message=MessageResponseDTO.model_validate(reply),
                    session_status=session.status,
                )
                await self.repo.commit() # 변경 없이 잠금만 푼다.
                return response

            await self.repo.create_message(
                session_id,
                MessageRole.USER,
                content,
                client_message_id=client_message_id,
                input_type=input_type,
            )
            await self.repo.commit() # 잠금 해제. 이후 LLM 호출 동안 세션을 잠그지 않는다.
        except Exception as error:
            await self._rollback_and_raise(error)

        # TODO: 입력 안전필터 (guard_checks gate=IN)

        # --- 프롬프트 조립 + LLM 호출 / 검증 루프 ---
        messages, checklists = await self._build_prompt_context(session_id)
        await self.repo.commit() # 읽기 트랜잭션을 닫는다. (LLM 호출 중 연결을 붙잡지 않기 위함)

        output: LlmReplyOutput | None = None
        llm_call_records: list[dict[str, Any]] = []
        feedback: str | None = None

        for attempt in range(1, MAX_LLM_ATTEMPTS + 1):
            parsed, record = await self._call_llm(messages, checklists, feedback, attempt)

            if parsed is None:
                errors = ["응답을 지정된 JSON 형식으로 해석하지 못했습니다."]
            else:
                errors = await self._validate_llm_output(session_id, parsed, checklists)

            record["validation_errors"] = errors or None
            if errors:
                record["parse_status"] = LlmCallParseStatus.FAILED
            else:
                record["parse_status"] = LlmCallParseStatus.OK if attempt == 1 else LlmCallParseStatus.RETRIED_OK
            llm_call_records.append(record)

            if not errors:
                output = parsed
                break
            feedback = self._build_retry_feedback(errors)

        # 모든 시도 실패: 호출 기록만 남기고 502로 오류 문구를 내려준다.
        if output is None:
            await self._save_failed_turn(llm_call_records)

        # --- 트랜잭션 2: 재잠금 -> 저장 -> commit ---
        try:
            session = await self._get_locked_active_session(user_id, session_id)
            # TODO: 출력 안전필터 (guard_checks gate=OUT), 감정분석
            reply = await self._save_turn_result(session, checklists, output, llm_call_records)
        except Exception as error:
            await self._rollback_and_raise(error)

        return SendMessageResponseDTO(
            message=MessageResponseDTO.model_validate(reply),
            session_status=session.status,
        )


    # 5-1. 턴 처리 내부: 프롬프트 재료 조회 (세션 원문, 체크리스트)
    async def _build_prompt_context(
        self, session_id: int
    ) -> tuple[list[Message], list[SessionChecklist]]:
        messages = await self.repo.find_messages_for_prompt(session_id)
        checklists = await self.repo.find_session_checklist(session_id)
        return messages, checklists


    # 5-2. 턴 처리 내부: LLM 호출 1회 (재시도 루프는 send_message가 돈다)
    # - feedback: 이전 시도의 검증 실패 사유 (첫 호출은 None)
    # - 반환: (파싱된 출력, create_llm_call에 넘길 호출 기록). 파싱에 실패하면 출력은 None
    # - 호출 기록 필드: purpose=LlmCallPurpose.REPLY, model, prompt_version, attempt, tokens_in, tokens_out,
    #   latency_ms, status, error (parse_status와 validation_errors는 send_message가 채운다)
    #   llm_calls에서 prompt_version, status, parse_status는 NOT NULL이다. 빠뜨리면 저장할 때 오류가 난다.
    #
    # TODO: chat_engine 미구현
    # - LlamaIndex + ChromaDB 조합으로 구성하고, Claude에서 LlmReplyOutput 스키마의 JSON으로 출력을 받을 예정
    # - 프롬프트와 LLM 클라이언트는 아직 없다. 둘 곳(경로)도 추후 정한다.
    # - 모델명, API 키, 타임아웃은 os.getenv로 읽는다.
    # - LlamaIndex를 거치면 토큰 사용량이 감싸져서 나오므로 tokens_in/tokens_out은 원본 응답(raw)에서 꺼내야 할 수 있다.
    async def _call_llm(
        self,
        messages: list[Message],
        checklists: list[SessionChecklist],
        feedback: str | None,
        attempt: int,
    ) -> tuple[LlmReplyOutput | None, dict[str, Any]]:
        raise NotImplementedError("chat_engine(LlamaIndex + ChromaDB)이 아직 구현되지 않았습니다.")


    # 5-3. 턴 처리 내부: LLM 출력 검증
    # - item_id가 이 세션 항목인지, 상태 전이, value와 answer_type, skip_reason, evidence_seq(사용자 메시지) 확인
    # - 반환: 오류 목록 (비어 있으면 통과)
    async def _validate_llm_output(
        self,
        session_id: int,
        output: LlmReplyOutput,
        checklists: list[SessionChecklist],
    ) -> list[str]:
        errors: list[str] = []
        checklist_by_item = {checklist.item_id: checklist for checklist in checklists}

        # 1. 이번 턴에 질문한 항목
        for item_id in output.asked_item_ids:
            if item_id not in checklist_by_item:
                errors.append(f"asked_item_ids의 {item_id}는 이 세션의 체크리스트 항목이 아닙니다.")

        # 2. 상태가 바뀐 항목
        seen_item_ids: set[int] = set()
        for change in output.checklist_changes:
            item_id = change.item_id
            checklist = checklist_by_item.get(item_id)
            if checklist is None:
                errors.append(f"item_id {item_id}는 이 세션의 체크리스트 항목이 아닙니다.")
                continue
            if item_id in seen_item_ids:
                errors.append(f"item_id {item_id}가 checklist_changes에 중복되었습니다.")
                continue
            seen_item_ids.add(item_id)

            if change.status == "skipped":
                # skipped: skip_reason 필수, value는 null
                if change.skip_reason is None:
                    errors.append(f"item_id {item_id}: skipped이면 skip_reason이 필요합니다.")
                if change.value is not None:
                    errors.append(f"item_id {item_id}: skipped이면 value는 null이어야 합니다.")
            else:
                # done: skip_reason은 null, value와 근거 메시지(evidence_seq) 필수
                if change.skip_reason is not None:
                    errors.append(f"item_id {item_id}: done이면 skip_reason은 null이어야 합니다.")
                if change.value is None:
                    errors.append(f"item_id {item_id}: done이면 value가 필요합니다.")
                else:
                    value_error = self._check_value(checklist, change.value)
                    if value_error:
                        errors.append(f"item_id {item_id}: {value_error}")
                if change.evidence_seq is None:
                    errors.append(f"item_id {item_id}: done이면 근거가 된 evidence_seq가 필요합니다.")

            # evidence_seq: 이 세션의 사용자 메시지여야 한다.
            if change.evidence_seq is not None:
                evidence = await self.repo.find_message_by_seq(session_id, change.evidence_seq)
                if evidence is None or evidence.role != MessageRole.USER:
                    errors.append(f"item_id {item_id}: evidence_seq {change.evidence_seq}는 이 세션의 사용자 메시지가 아닙니다.")

        # 3. 종료 요청의 일관성: counsel_end가 true일 때만 end_reason이 있다.
        if output.counsel_end and output.end_reason is None:
            errors.append("counsel_end가 true이면 end_reason이 필요합니다.")
        if not output.counsel_end and output.end_reason is not None:
            errors.append("counsel_end가 false이면 end_reason은 null이어야 합니다.")

        return errors


    # 5-3-1. 검증 내부: value가 항목의 answer_type과 응답 범위에 맞는지 (맞으면 None, 아니면 사유)
    # - 응답 범위는 checklist_items.options(글로벌 체크리스트의 "발생 가능한 응답 범위")에 있다. (checklist.item.options)
    # TODO: answer_type(boolean / number / scale / choice / text)별 검증 함수는 구상 후 작성한다.
    #       지금은 모든 값을 통과시킨다.
    @staticmethod
    def _check_value(checklist: SessionChecklist, value: Any) -> str | None:
        return None


    # 5-4. 턴 처리 내부: 재호출용 실패 사유 문구 (순수 함수)
    def _build_retry_feedback(self, errors: list[str]) -> str:
        lines = "\n".join(f"- {error}" for error in errors)
        return f"직전 응답에 다음 문제가 있었습니다. 모두 고쳐서 다시 응답하세요.\n{lines}"


    # 5-5. 턴 처리 내부: 모든 시도가 실패했을 때 프론트에 내려줄 오류 문구 (순수 함수)
    def _build_fallback_reply(self) -> str:
        return FALLBACK_REPLY_TEXT


    # 5-6. 턴 처리 내부: 체크리스트 상태 반영 + 질문 횟수 증가 (asked_item_ids)
    # - _validate_llm_output을 통과한 출력만 받는다. (item_id, 상태, 값은 검증이 끝난 상태)
    # - session_checklist.value 형식
    #   - done: {"message_id": 근거 사용자 메시지 id, "answer": answer_type에 맞춘 답변 값}
    #   - skipped: null
    # - evidence_message_id 컬럼에도 같은 메시지 id를 채운다. (value 안의 message_id와 둘 다)
    async def _apply_checklist_changes(
        self,
        session_id: int,
        output: LlmReplyOutput,
        checklists: list[SessionChecklist],
    ) -> None:
        checklist_by_item = {checklist.item_id: checklist for checklist in checklists}

        for change in output.checklist_changes:
            evidence_message_id = None
            if change.evidence_seq is not None:
                evidence = await self.repo.find_message_by_seq(session_id, change.evidence_seq)
                evidence_message_id = evidence.id if evidence else None

            if change.status == "done":
                value = {"message_id": evidence_message_id, "answer": change.value}
                skip_reason = None
            else:
                value = None
                skip_reason = change.skip_reason

            await self.repo.record_checklist_change(
                checklist_by_item[change.item_id],
                to_status=ChecklistStatus(change.status),
                value=value,
                skip_reason=skip_reason,
                evidence_message_id=evidence_message_id,
            )

        # 같은 항목을 두 번 적었어도 이번 턴의 질문은 1회
        await self.repo.increment_ask_count(session_id, list(set(output.asked_item_ids)))


    # 5-7. 턴 처리 내부: 필수 항목이 모두 done 또는 허용된 skipped인지 (순수 함수)
    # - counsel_end는 요청일 뿐이고, 종료는 이 결과(DB 상태)와 MIN_USER_TURNS로 service가 확정한다.
    def _is_checklist_complete(self, checklists: list[SessionChecklist]) -> bool:
        for checklist in checklists:
            if not checklist.required:
                continue
            if checklist.status == ChecklistStatus.DONE:
                continue
            if (
                checklist.status == ChecklistStatus.SKIPPED
                and checklist.skip_reason in ALLOWED_REQUIRED_SKIP_REASONS
            ):
                continue
            return False
        return True


    # 5-8. 턴 처리 내부: 재전송 시 기존 AI 답변 조회
    # - 재전송된 사용자 메시지(seq)보다 뒤에 있는 가장 최근 ASSISTANT 메시지. 없으면 None
    async def _find_reply(self, session_id: int, user_message: Message) -> Message | None:
        return await self.repo.find_reply(session_id, user_message.seq)


    # 5-9. 턴 처리 내부: 트랜잭션 2 저장 묶음 (LLM 출력이 검증을 통과한 턴)
    # - 체크리스트 반영, 답변 메시지 저장, llm_calls 저장, 종료 처리, commit
    # - 답변 메시지가 먼저 생기므로 llm_calls는 message_id를 바로 채워 저장한다. (link_llm_calls 불필요)
    async def _save_turn_result(
        self,
        session: ChatSession,
        checklists: list[SessionChecklist],
        output: LlmReplyOutput,
        llm_call_records: list[dict[str, Any]],
    ) -> Message:
        # 1. 체크리스트 반영
        await self._apply_checklist_changes(session.id, output, checklists)

        # 2. 답변 메시지 저장
        reply = await self.repo.create_message(
            session.id,
            MessageRole.ASSISTANT,
            output.reply_text,
            expression=output.expression.value,
            system_record_status=MessageSystemRecordStatus.OK,
        )

        # 3. 호출 기록 저장
        for record in llm_call_records:
            await self.repo.create_llm_call(message_id=reply.id, **record)

        # 4. 종료 판정: counsel_end는 요청일 뿐. DB의 체크리스트 상태와 최소 턴 수로 확정한다.
        # TODO: end_reason="safety"는 안전필터를 붙일 때 처리한다. 지금은 "completed"만 종료로 본다.
        if output.counsel_end and output.end_reason == "completed":
            fresh_checklists = await self.repo.find_session_checklist(session.id)
            user_turns = await self.repo.count_user_messages(session.id)
            if self._is_checklist_complete(fresh_checklists) and user_turns >= MIN_USER_TURNS:
                await self.repo.update_session(
                    session,
                    status=ChatSessionStatus.ENDED,
                    end_reason=ChatSessionEndReason.COMPLETED,
                    ended_at=datetime.now(KST),
                    summary_status=ChatSessionSummaryStatus.PENDING,
                )

        await self.repo.commit()
        return reply


    # 5-10. 턴 처리 내부: 모든 시도가 실패한 턴
    # - 오류 문구는 messages에 저장하지 않고 502 응답의 detail로만 내려준다. (프론트가 채팅창에 표시)
    # - llm_calls.message_id는 "이 호출이 설명하는 assistant 메시지"이고 장애일 때는 null이다. (모델 주석)
    #   답변 메시지가 없으므로 이 턴의 호출 기록은 message_id=None으로 남긴다.
    # - 답변이 없으므로 같은 client_message_id로 재전송하면 409가 된다. (프론트는 새 id로 보내야 한다)
    async def _save_failed_turn(self, llm_call_records: list[dict[str, Any]]) -> NoReturn:
        try:
            for record in llm_call_records:
                await self.repo.create_llm_call(message_id=None, **record)
            await self.repo.commit()
        except Exception as error:
            await self._rollback_and_raise(error)

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=self._build_fallback_reply()
        )


    # 5-11. 턴 처리 내부: 잠금 조회 (본인 세션, ACTIVE 상태 확인)
    # - 없거나 타인 세션이면 404, ACTIVE가 아니면 409
    # - 호출한 쪽이 commit 또는 rollback으로 잠금을 푼다.
    async def _get_locked_active_session(self, user_id: int, session_id: int) -> ChatSession:
        session = await self.repo.find_session_by_id(session_id, user_id=user_id, for_update=True)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="세션이 존재하지 않습니다."
            )
        if session.status != ChatSessionStatus.ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="진행 중인 세션이 아닙니다."
            )
        return session


    # 6. 세션 사후요약 생성 (세션당 1건)
    # - 대상: status=ENDED이고 summary_status=PENDING인 세션. 대상이 아니면 아무것도 하지 않고 None
    # - 호출 위치(종료 직후 BackgroundTasks / 배치)는 아직 정하지 않았다. 어디서 부르든 이 함수 하나로 처리한다.
    #   BackgroundTasks로 부를 경우 요청의 DB 세션이 닫힌 뒤이므로, 새 AsyncSession으로 만든 LlmService를 써야 한다.
    # - 저장 형식은 session_summaries 모델을 따른다.
    #   - context_summary(text), topics(JSONB, 키워드 배열), findings(JSONB, [{label, evidence}]): LLM 출력 그대로
    #   - chief_complaint(text): 사전 문진(INTAKE) 세션만 저장한다. 그 밖의 세션은 LLM이 보내도 None
    #   - mood_summary(JSONB, NOT NULL) = {dominant, distribution, intensity, evidence_seqs}
    #     dominant, distribution: 사용자 메시지의 감정분석 6종 평균으로 service가 계산한다. (_build_mood_summary)
    #     intensity, evidence_seqs: LLM 출력(mood)
    #     감정분석이 한 건도 없으면(감정분석 모델 적용 전) 네 값이 모두 비어 있는 구조로 저장한다. (NOT NULL이라)
    # - send_message처럼 LLM 호출을 잠금 밖에서 한다.
    #   [트랜잭션 1: 세션 잠금 -> 대상 확인 -> 원문 + 감정분석 조회 -> commit]
    #   [LLM 호출 / 검증 루프 (최대 MAX_LLM_ATTEMPTS회)]
    #   [트랜잭션 2: 재잠금 -> 호출 기록 저장 -> 대상 재확인 -> 요약 저장 + READY, 또는 FAILED -> commit]
    # - 동시에 두 번 불리면 LLM은 두 번 호출될 수 있지만, 트랜잭션 2의 재확인 때문에 요약 저장은 한 번만 된다.
    # - 실패하면 summary_status=FAILED만 남기고 요약은 저장하지 않는다. (FAILED 재시도는 아직 없다)
    # - 호출 기록은 llm_calls에 purpose=SUMMARY, message_id=None으로 남긴다.
    async def create_session_summary(self, session_id: int) -> SessionSummary | None:
        # --- 트랜잭션 1: 잠금 -> 대상 확인 -> 원문 + 감정분석 조회 ---
        try:
            session = await self.repo.find_session_by_id(session_id, for_update=True)
            if not self._is_summary_target(session):
                await self.repo.commit() # 변경 없이 잠금만 푼다.
                return None

            rows = await self.repo.find_messages_with_emotions(session_id)
            if not rows:
                # 요약할 대화가 없다.
                await self.repo.update_session(session, summary_status=ChatSessionSummaryStatus.SKIPPED)
                await self.repo.commit()
                return None

            session_type = session.session_type
            await self.repo.commit() # 잠금 해제. 이후 LLM 호출 동안 세션을 잠그지 않는다.
        except Exception as error:
            await self._rollback_and_raise(error)

        summary_input = self._build_summary_input(rows)
        has_emotion = any(item["emotion"] is not None for item in summary_input)

        # --- LLM 호출 / 검증 루프 ---
        output: LlmSummaryOutput | None = None
        llm_call_records: list[dict[str, Any]] = []
        feedback: str | None = None

        for attempt in range(1, MAX_LLM_ATTEMPTS + 1):
            parsed, record = await self._call_summary_llm(
                summary_input, session_type, has_emotion, feedback, attempt
            )

            if parsed is None:
                errors = ["응답을 지정된 JSON 형식으로 해석하지 못했습니다."]
            else:
                errors = self._validate_summary_output(parsed, summary_input, has_emotion)

            # parse_status는 NOT NULL이라 모든 기록에 채운다. (send_message와 같은 규칙)
            record["validation_errors"] = errors or None
            if errors:
                record["parse_status"] = LlmCallParseStatus.FAILED
            else:
                record["parse_status"] = LlmCallParseStatus.OK if attempt == 1 else LlmCallParseStatus.RETRIED_OK
            llm_call_records.append(record)

            if not errors:
                output = parsed
                break
            feedback = self._build_retry_feedback(errors)

        # --- 트랜잭션 2: 재잠금 -> 호출 기록 저장 -> 대상 재확인 -> 요약 저장 또는 FAILED ---
        try:
            session = await self.repo.find_session_by_id(session_id, for_update=True)

            # 호출 기록은 요약 저장 여부와 관계없이 남긴다. (실제로 호출했으므로)
            for record in llm_call_records:
                await self.repo.create_llm_call(message_id=None, **record)

            if not self._is_summary_target(session):
                # 그 사이 다른 호출이 먼저 처리했다.
                await self.repo.commit()
                return None

            if output is None:
                await self.repo.update_session(session, summary_status=ChatSessionSummaryStatus.FAILED)
                await self.repo.commit()
                return None

            summary = await self.repo.upsert_session_summary(
                session_id,
                context_summary=output.context_summary,
                mood_summary=self._build_mood_summary(summary_input, output, has_emotion),
                topics=output.topics,
                chief_complaint=(
                    output.chief_complaint if session_type == ChatSessionType.INTAKE else None
                ),
                findings=[finding.model_dump() for finding in output.findings],
            )
            await self.repo.update_session(session, summary_status=ChatSessionSummaryStatus.READY)
            await self.repo.commit()
            return summary
        except Exception as error:
            await self._rollback_and_raise(error)


    # 6-1. 사후요약 내부: 요약 대상인지 (순수 함수)
    @staticmethod
    def _is_summary_target(session: ChatSession | None) -> bool:
        return (
            session is not None
            and session.status == ChatSessionStatus.ENDED
            and session.summary_status == ChatSessionSummaryStatus.PENDING
        )


    # 6-2. 사후요약 내부: LLM 입력 만들기 (순수 함수)
    # - 메시지마다 seq, role, content를 넣는다. role이 있어야 환자의 말과 AI의 답변을 구분할 수 있다.
    # - emotion: 감정분석 6종 점수(Decimal -> float). 감정분석이 없는 메시지(AI 답변, 분석 전)는 None
    @staticmethod
    def _build_summary_input(
        rows: list[tuple[Message, EmotionAnalysis | None]],
    ) -> list[dict[str, Any]]:
        summary_input: list[dict[str, Any]] = []
        for message, emotion in rows:
            summary_input.append({
                "seq": message.seq,
                "role": MessageRole(message.role).value,
                "content": message.content,
                "emotion": (
                    {field: float(getattr(emotion, field)) for field in EMOTION_FIELDS}
                    if emotion is not None else None
                ),
            })
        return summary_input


    # 6-3. 사후요약 내부: LLM 호출 1회 (재시도 루프는 create_session_summary가 돈다)
    # - _call_llm과 같은 계약: 예외를 던지지 않고 (파싱된 출력 또는 None, 호출 기록)을 반환한다.
    # - 호출 기록 필드: purpose=LlmCallPurpose.SUMMARY, model, prompt_version, attempt, tokens_in, tokens_out,
    #   latency_ms, status, error (prompt_version, status는 NOT NULL. parse_status와 validation_errors는 호출한 쪽이 채운다)
    # - session_type이 INTAKE일 때만 chief_complaint를 요청하고, 아니면 null로 내라고 지시한다.
    # - has_emotion이 False면 mood를 null로 내라고 지시한다.
    #
    # TODO: 사후요약 전용 프롬프트와 LLM 클라이언트 미구현 (_call_llm과 같은 클라이언트를 쓸 예정)
    # - 출력은 LlmSummaryOutput 스키마의 JSON으로 받는다.
    # - 주호소(chief_complaint)와 AI 참고 소견(findings)은 이 프롬프트의 출력으로 요청한다.
    async def _call_summary_llm(
        self,
        summary_input: list[dict[str, Any]],
        session_type: ChatSessionType,
        has_emotion: bool,
        feedback: str | None,
        attempt: int,
    ) -> tuple[LlmSummaryOutput | None, dict[str, Any]]:
        raise NotImplementedError("사후요약 프롬프트와 LLM 클라이언트가 아직 구현되지 않았습니다.")


    # 6-4. 사후요약 내부: LLM 출력 검증 (오류 목록 반환, 비어 있으면 통과)
    # - context_summary가 비어 있지 않은지, findings의 label이 비어 있지 않은지
    # - 감정분석이 있는데 mood가 없으면 재요청한다. (감정분석이 없을 때 온 mood는 저장할 때 버린다)
    # - mood.evidence_seqs는 이 세션의 사용자 메시지 seq여야 한다.
    @staticmethod
    def _validate_summary_output(
        output: LlmSummaryOutput,
        summary_input: list[dict[str, Any]],
        has_emotion: bool,
    ) -> list[str]:
        errors: list[str] = []

        if not output.context_summary.strip():
            errors.append("context_summary가 비어 있습니다.")
        for index, finding in enumerate(output.findings):
            if not finding.label.strip():
                errors.append(f"findings[{index}]의 label이 비어 있습니다.")

        if has_emotion:
            if output.mood is None:
                errors.append("감정분석 데이터가 있으므로 mood가 필요합니다.")
            else:
                user_seqs = {
                    item["seq"] for item in summary_input if item["role"] == MessageRole.USER.value
                }
                for seq in output.mood.evidence_seqs:
                    if seq not in user_seqs:
                        errors.append(f"mood.evidence_seqs의 {seq}는 이 세션의 사용자 메시지가 아닙니다.")

        return errors


    # 6-5. 사후요약 내부: mood_summary 만들기 (순수 함수)
    # - distribution: 감정분석이 있는 메시지들의 6종 평균 (소수 셋째 자리 반올림)
    # - dominant: distribution에서 가장 높은 감정
    # - intensity, evidence_seqs: LLM 출력
    # - 감정분석이 없으면 모두 비운 구조를 돌려준다. (mood_summary는 NOT NULL)
    @staticmethod
    def _build_mood_summary(
        summary_input: list[dict[str, Any]],
        output: LlmSummaryOutput,
        has_emotion: bool,
    ) -> dict[str, Any]:
        scores = [item["emotion"] for item in summary_input if item["emotion"] is not None]
        if not has_emotion or not scores or output.mood is None:
            return {"dominant": None, "distribution": None, "intensity": None, "evidence_seqs": []}

        distribution = {
            field: round(sum(score[field] for score in scores) / len(scores), 3)
            for field in EMOTION_FIELDS
        }
        return {
            "dominant": max(distribution, key=distribution.get),
            "distribution": distribution,
            "intensity": output.mood.intensity,
            "evidence_seqs": output.mood.evidence_seqs,
        }


    # 7. 세션 마감 정리: 한 번도 시작하지 않고 expires_at이 지난 예정 세션 -> MISSED
    # - 세션 종료 조건은 세 가지다.
    #   (1) LLM 출력의 정상 종료 신호 -> send_message의 종료 판정 (ENDED / COMPLETED)
    #   (2) 상담 중 이탈 -> 프론트가 end API 호출, end_session (ENDED / USER)
    #   (3) 시작한 적 없이 expires_at이 지남 -> 이 함수 (MISSED)
    # - 스케줄러 없이 "요청이 들어올 때" 처리한다. 세션 상태를 프론트에 보여 줘야 하는 요청의 맨 앞에서 부른다.
    #   지금은 get_main_session(환자 상담 메인)에서 부른다. 세션 목록·상태를 보여 주는 API(예: 의사용 세션 조회)가
    #   생기면 그 앞에서도 부른다. (의사 화면이면 user_id=환자 id)
    # - 기능상 접속은 이 함수 없이도 막힌다. (start_session이 expires_at을 400으로 막고, 상담 메인 조회도 마감 지난 세션을 제외)
    #   이 함수는 DB의 status를 실제 상태와 맞추는 역할이다.
    # - user_id를 주면 그 환자의 세션만 정리한다. None이면 전체 (나중에 배치로 돌릴 때)
    # - 변경한 세션 수를 반환한다.
    async def process_session_timeouts(self, user_id: int | None = None) -> int:
        try:
            count = await self.repo.expire_scheduled_sessions(datetime.now(KST), user_id=user_id)
            await self.repo.commit()
        except Exception as error:
            await self._rollback_and_raise(error)
        return count


    # 방치 세션 처리 (예외 상황, 지금은 다루지 않는다)
    # - 설계: AI 상담은 접속하면 끝날 때까지 진행하고, 중간에 나가면 세션을 종료한다. (end_session)
    # - expires_at(필수)은 최초 접속(start_session) 때 한 번만 검증한다. 시작한 뒤에는 expires_at을 다시 검증하지 않는다.
    # - 세션 상태(status)는 외부 표시용이다. 접속 가능 여부의 검증 기준으로 쓰지 않는다.
    # TODO: 이탈 통지가 오지 않는 경우(앱 강제 종료, 네트워크 끊김)는 아직 처리하지 않는다.
    #   그런 세션은 ACTIVE로 남아, 환자당 ACTIVE 1개 제약(exists_active_session, uix_chat_sessions_user_active) 때문에
    #   다음 세션 시작(start_session)이 409가 된다. expires_at은 시작할 때만 검증하므로 7번에서도 잡히지 않는다.
    #   처리 방안 후보: 마지막 메시지 이후 일정 시간이 지나면 ENDED / TIMEOUT으로 정리,
    #   또는 start_session에서 남아 있는 ACTIVE 세션을 먼저 닫고 새 세션을 연다.



# 레포지토리 주입 팩토리 함수
def get_llm_service(repo: LlmRepository = Depends(get_llm_repository)):
    return LlmService(repo)
