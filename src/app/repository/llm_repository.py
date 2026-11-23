from datetime import datetime, timedelta, timezone
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.infrastructure.postgresql import get_postgresql_db
from fastapi import Depends

# 모델, ORM
from app.model.chat_session_model import ChatSession
from app.model.message_model import Message
from app.model.checklist_item_model import ChecklistItem
from app.model.session_checklist_model import SessionChecklist
from app.model.checklist_event_model import ChecklistEvent
from app.model.llm_call_model import LlmCall
from app.model.session_summary_model import SessionSummary
from app.enum.chat_enum import SessionStatus, MessageRole
from app.enum.checklist_enum import ChecklistStatus, SkipReason
from sqlalchemy import select, update, func, exists

KST = timezone(timedelta(hours=9)) # UTC+9


# AI 상담(세션, 메시지, 체크리스트, LLM 호출) DB 접근
# - 다른 repository와 달리 함수 안에서 commit하지 않는다. (flush까지만)
#   한 턴의 저장(답변 메시지 + 체크리스트 갱신 + 이력 + 호출 기록 연결)을 한 트랜잭션으로 묶어야 하기 때문.
#   commit / rollback 시점은 service가 아래 commit(), rollback()으로 정한다.
class LlmRepository:

    # 생성자 주입
    def __init__(self, db: AsyncSession):
        self.db = db


    # 트랜잭션
    # 0-1. 확정
    async def commit(self) -> None:
        await self.db.commit()


    # 0-2. 되돌리기
    async def rollback(self) -> None:
        await self.db.rollback()


    # 세션
    # 1. 예정 세션 일괄 생성 (의사 등록)
    # - flush하면 각 세션의 id가 채워져서, 같은 트랜잭션 안에서 바로 체크리스트 생성에 쓸 수 있다.
    # - prev_session_id(직전 세션)는 service가 find_latest_session_summary로 미리 찾아서 ChatSession에 넣은 뒤 넘긴다. (없으면 None)
    async def create_sessions(self, sessions: list[ChatSession]) -> list[ChatSession]:
        self.db.add_all(sessions)
        await self.db.flush()
        return sessions


    # 2. 세션 1건 조회
    # - user_id를 주면 본인 세션만 (환자용), 안 주면 id로만 (의사용)
    # - for_update=True: 행 잠금(SELECT ... FOR UPDATE). 시작, 메시지 저장, 종료처럼 상태를 바꿀 때 사용
    #   잠금은 트랜잭션이 끝날 때(commit/rollback) 풀린다. 잠근 채로 LLM을 호출하지 않는다.
    async def find_session_by_id(
        self, session_id: int, user_id: int | None = None, for_update: bool = False
    ) -> ChatSession | None:
        query = select(ChatSession).where(ChatSession.id == session_id)

        if user_id is not None:
            query = query.where(ChatSession.user_id == user_id)
        if for_update:
            query = query.with_for_update()

        result = await self.db.execute(query)
        return result.scalar_one_or_none()


    # 3. 상담 메인: 진행 중(active) 세션, 없으면 가장 가까운 예정(scheduled) 세션
    # - 접속 마감(expires_at)이 지난 예정 세션은 제외
    # - 지금 접속 가능한지(available)는 service가 scheduled_at과 비교해 계산
    async def find_active_or_next_session(self, user_id: int) -> ChatSession | None:
        active_query = (
            select(ChatSession)
            .where(
                ChatSession.user_id == user_id,
                ChatSession.status == SessionStatus.ACTIVE
            )
            .limit(1)
        )
        result = await self.db.execute(active_query)
        active_session = result.scalar_one_or_none()
        if active_session:
            return active_session

        now = datetime.now(KST)
        next_query = (
            select(ChatSession)
            .where(
                ChatSession.user_id == user_id,
                ChatSession.status == SessionStatus.SCHEDULED,
                (ChatSession.expires_at.is_(None)) | (ChatSession.expires_at > now)
            )
            .order_by(ChatSession.scheduled_at.asc(), ChatSession.id.asc())
            .limit(1)
        )
        result = await self.db.execute(next_query)
        return result.scalar_one_or_none()


    # 4. 진행 중인 세션이 있는지 (세션 시작 전 확인)
    async def exists_active_session(self, user_id: int) -> bool:
        query = select(
            exists().where(
                ChatSession.user_id == user_id,
                ChatSession.status == SessionStatus.ACTIVE
            )
        )
        result = await self.db.execute(query)
        return bool(result.scalar())


    # 5. 세션 상태 갱신
    # - find_session_by_id(..., for_update=True)로 잠가서 읽은 객체를 넘긴다.
    #   (id로 UPDATE를 따로 보내면 메모리의 객체와 DB 값이 어긋난다)
    # - 예: update_session(session, status=SessionStatus.ENDED, end_reason=SessionEndReason.COMPLETED, ended_at=now)
    async def update_session(self, session: ChatSession, **fields: Any) -> ChatSession:
        for key, value in fields.items():
            if not hasattr(ChatSession, key):
                raise AttributeError(f"chat_sessions에 없는 컬럼: {key}")
            setattr(session, key, value)

        await self.db.flush()
        return session


    # 메시지
    # 6. 새 메시지 생성 (다음 seq 자동 부여)
    # - 반드시 find_session_by_id(..., for_update=True)로 세션을 잠근 상태에서 호출
    #   (잠금 없이 동시에 부르면 같은 seq가 계산되어 uq_messages_session_id_seq에 걸린다)
    # - fields: expression, client_message_id, system_record_status, input_type
    async def create_message(
        self, session_id: int, role: MessageRole, content: str, **fields: Any
    ) -> Message:
        seq_query = (
            select(func.coalesce(func.max(Message.seq), 0) + 1)
            .where(Message.session_id == session_id)
        )
        result = await self.db.execute(seq_query)
        next_seq = result.scalar_one()

        message = Message(session_id=session_id, seq=next_seq, role=role, content=content, **fields)
        self.db.add(message)
        await self.db.flush()
        return message


    # 7. 재전송 확인: 같은 client_message_id로 이미 저장된 사용자 메시지
    async def find_message_by_client_id(self, session_id: int, client_message_id: str) -> Message | None:
        query = (
            select(Message)
            .where(
                Message.session_id == session_id,
                Message.role == MessageRole.USER,
                Message.client_message_id == client_message_id
            )
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()


    # 8. 사용자 메시지에 대한 AI 답변 (재전송 시 이미 만든 답을 돌려주기 위함)
    # TODO: messages.reply_to_id 컬럼을 추가해야 동작한다. 추가 전에 호출하면 AttributeError
    async def find_reply(self, user_message_id: int) -> Message | None:
        query = select(Message).where(Message.reply_to_id == user_message_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()


    # 9. 순번(seq)으로 메시지 조회 (LLM이 준 evidence_seq -> evidence_message_id 변환)
    async def find_message_by_seq(self, session_id: int, seq: int) -> Message | None:
        query = (
            select(Message)
            .where(
                Message.session_id == session_id,
                Message.seq == seq
            )
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()


    # 10. 프롬프트용 세션 원문 전체 (seq 순)
    async def find_messages_for_prompt(self, session_id: int) -> list[Message]:
        query = (
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.seq.asc())
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())


    # 11. 화면용 대화 기록 (after_seq 이후 limit개, 커서 방식)
    # - limit + 1개를 읽어서 다음 페이지가 있는지 판단한다.
    # - 반환: (메시지 목록, 다음 커서). 다음이 없으면 커서는 None
    async def find_messages(
        self, session_id: int, after_seq: int | None, limit: int
    ) -> tuple[list[Message], int | None]:
        query = select(Message).where(Message.session_id == session_id)

        if after_seq is not None:
            query = query.where(Message.seq > after_seq)

        query = query.order_by(Message.seq.asc()).limit(limit + 1)

        result = await self.db.execute(query)
        messages = list(result.scalars().all())

        has_next = len(messages) > limit
        messages = messages[:limit]
        next_cursor = messages[-1].seq if has_next else None
        return messages, next_cursor


    # 12. 사용자 메시지 수 (종료 판정의 최소 턴 수)
    async def count_user_messages(self, session_id: int) -> int:
        query = (
            select(func.count(Message.id))
            .where(
                Message.session_id == session_id,
                Message.role == MessageRole.USER
            )
        )
        result = await self.db.execute(query)
        return result.scalar_one()


    # 체크리스트
    # 13. 카탈로그 항목 조회 (의사가 고른 항목이 실제로 있는지, 활성인지 검증용)
    # - 받은 개수가 요청한 개수보다 적거나 is_active=False가 섞여 있으면 service가 거절
    async def find_checklist_items(self, item_ids: list[int]) -> list[ChecklistItem]:
        if not item_ids:
            return []

        query = select(ChecklistItem).where(ChecklistItem.id.in_(item_ids))
        result = await self.db.execute(query)
        return list(result.scalars().all())


    # 14. 세션에 체크리스트 생성
    # - rows = [{"item_id": 3, "required": True, "sort_order": 1}, ...]
    # - status=pending, ask_count=0으로 시작
    async def create_session_checklist(self, session_id: int, rows: list[dict]) -> list[SessionChecklist]:
        checklists = [
            SessionChecklist(
                session_id=session_id,
                item_id=row["item_id"],
                required=row.get("required", False),
                sort_order=row.get("sort_order"),
                status=ChecklistStatus.PENDING,
                ask_count=0
            )
            for row in rows
        ]
        self.db.add_all(checklists)
        await self.db.flush()
        return checklists


    # 15. 세션에 지정된 체크리스트 (sort_order 순)
    # - 원본 항목(label, instruction, answer_type, options)을 selectinload로 함께 불러온다.
    #   (비동기에서는 지연 로딩이 안 되므로 row.item을 쓰려면 미리 불러와야 한다)
    # - 프롬프트 조립, LLM 출력 검증, 종료 판정(필수 항목이 모두 done/skipped인지)에 공통으로 쓴다.
    async def find_session_checklist(self, session_id: int) -> list[SessionChecklist]:
        query = (
            select(SessionChecklist)
            .options(selectinload(SessionChecklist.item))
            .where(SessionChecklist.session_id == session_id)
            .order_by(SessionChecklist.sort_order.asc(), SessionChecklist.id.asc())
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())


    # 16. 체크리스트 항목 상태 변경 + 이력(checklist_events) 추가
    # - 둘을 한 함수로 묶어서 이력이 빠지는 일을 막는다.
    # - 상태 전이가 허용되는지(예: done -> pending 금지)는 호출 전에 service가 검증한다.
    async def record_checklist_change(
        self,
        checklist: SessionChecklist,
        to_status: ChecklistStatus,
        value: Any = None,
        skip_reason: SkipReason | None = None,
        evidence_message_id: int | None = None
    ) -> ChecklistEvent:
        event = ChecklistEvent(
            checklist_id=checklist.id,
            from_status=checklist.status,
            to_status=to_status,
            value=value
        )

        checklist.status = to_status
        checklist.value = value
        checklist.skip_reason = skip_reason
        checklist.evidence_message_id = evidence_message_id

        self.db.add(event)
        await self.db.flush()
        return event


    # 17. 이번 턴에 물어본 항목의 질문 횟수 +1
    # - 일괄 UPDATE라서 이미 읽어 둔 SessionChecklist 객체의 ask_count는 바뀌지 않는다.
    #   같은 턴에서 다시 볼 일이 있으면 find_session_checklist로 새로 읽는다.
    async def increment_ask_count(self, session_id: int, item_ids: list[int]) -> None:
        if not item_ids:
            return

        query = (
            update(SessionChecklist)
            .where(
                SessionChecklist.session_id == session_id,
                SessionChecklist.item_id.in_(item_ids)
            )
            .values(ask_count=SessionChecklist.ask_count + 1)
        )
        await self.db.execute(query)


    # LLM 호출 기록
    # 18. LLM 호출 1회 기록 (재시도도 1회씩)
    # - fields: message_id, purpose, model, prompt_version, attempt, parse_status,
    #   validation_errors, tokens_in, tokens_out, latency_ms, status, error
    # - 주의: 현재 모델은 llm_calls.message_id가 NOT NULL이라, 답변 메시지가 생기기 전에는 저장할 수 없다.
    async def create_llm_call(self, **fields: Any) -> LlmCall:
        llm_call = LlmCall(**fields)
        self.db.add(llm_call)
        await self.db.flush()
        return llm_call


    # 19. 이번 턴의 호출 기록들을 AI 답변 메시지에 연결
    async def link_llm_calls(self, llm_call_ids: list[int], message_id: int) -> None:
        if not llm_call_ids:
            return

        query = (
            update(LlmCall)
            .where(LlmCall.id.in_(llm_call_ids))
            .values(message_id=message_id)
        )
        await self.db.execute(query)


    # 세션 요약
    # 20. 유저의 가장 최근 세션 요약
    # - 세션 등록 때 직전 세션(prev_session_id)을 찾는 데 쓴다. 반환값의 session_id가 직전 세션 id이다.
    # - 요약이 아직 없는 세션(진행 중, 요약 대기·실패·건너뜀)은 대상에서 빠진다. 없으면 None
    async def find_latest_session_summary(self, user_id: int) -> SessionSummary | None:
        query = (
            select(SessionSummary)
            .join(ChatSession, SessionSummary.session_id == ChatSession.id)
            .where(ChatSession.user_id == user_id)
            .order_by(SessionSummary.created_at.desc(), SessionSummary.id.desc())
            .limit(1)
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    

# 주입 팩토리 메서드
def get_llm_repository(db: AsyncSession = Depends(get_postgresql_db)):
    return LlmRepository(db)
