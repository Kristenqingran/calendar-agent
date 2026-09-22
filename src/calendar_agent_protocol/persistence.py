from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    event,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .domain import utc_now


class Base(DeclarativeBase):
    pass


class ConversationRow(Base):
    __tablename__ = "conversations"
    conversation_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    assistant_timezone: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class TaskRow(Base):
    __tablename__ = "tasks"
    task_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.conversation_id"))
    original_message: Mapped[str] = mapped_column(Text)
    object: Mapped[str] = mapped_column(String(32))
    intent: Mapped[str] = mapped_column(String(16))
    current_state: Mapped[str] = mapped_column(String(40))
    final_status: Mapped[str | None] = mapped_column(String(16))
    current_step_id: Mapped[str | None] = mapped_column(String(128))
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class TaskParameterRow(Base):
    __tablename__ = "task_parameters"
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.task_id"), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)
    source: Mapped[str | None] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20))
    evidence: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class TaskStepRow(Base):
    __tablename__ = "task_steps"
    step_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.task_id"))
    step_type: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20))
    input_summary: Mapped[Any | None] = mapped_column(JSON)
    output_summary: Mapped[Any | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ToolExchangeRow(Base):
    __tablename__ = "tool_exchanges"
    step_id: Mapped[str] = mapped_column(ForeignKey("task_steps.step_id"), primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.task_id"))
    tool: Mapped[str] = mapped_column(String(50))
    purpose: Mapped[str | None] = mapped_column(String(40))
    dependency_parameters: Mapped[list[str]] = mapped_column(JSON, default=list)
    request_payload: Mapped[Any] = mapped_column(JSON)
    result_payload: Mapped[Any | None] = mapped_column(JSON)
    result_hash: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))
    queried_range: Mapped[Any | None] = mapped_column(JSON)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_stale: Mapped[bool] = mapped_column(Boolean, default=False)
    stale_reason: Mapped[str | None] = mapped_column(Text)
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class OperationRow(Base):
    __tablename__ = "operations"
    operation_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.task_id"))
    tool: Mapped[str] = mapped_column(String(50))
    arguments_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30))
    result_payload: Mapped[Any | None] = mapped_column(JSON)
    verification_status: Mapped[str | None] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ClarificationRow(Base):
    __tablename__ = "clarifications"
    step_id: Mapped[str] = mapped_column(ForeignKey("task_steps.step_id"), primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.task_id"))
    reason: Mapped[str] = mapped_column(String(50))
    message: Mapped[str] = mapped_column(Text)
    expected_answer: Mapped[Any] = mapped_column(JSON)
    missing_fields: Mapped[Any | None] = mapped_column(JSON)
    ambiguous_fields: Mapped[Any | None] = mapped_column(JSON)
    blocked_from_state: Mapped[str] = mapped_column(String(40))
    user_response: Mapped[Any | None] = mapped_column(JSON)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StateTransitionRow(Base):
    __tablename__ = "state_transitions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.task_id"))
    from_state: Mapped[str] = mapped_column(String(40))
    to_state: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class InboundReceiptRow(Base):
    __tablename__ = "inbound_receipts"
    request_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.conversation_id"))
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.task_id"))
    message_type: Mapped[str] = mapped_column(String(40))
    payload_hash: Mapped[str] = mapped_column(String(64))
    response_payload: Mapped[Any | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


def make_engine(url: str) -> Engine:
    engine = create_engine(url)
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def fk(dbapi_connection: Any, _: Any) -> None:
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

    return engine
