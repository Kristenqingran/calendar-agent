from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from calendar_agent_protocol import repository as repository_module
from calendar_agent_protocol.domain import TaskEntity
from calendar_agent_protocol.enums import Intent, ObjectType, OperationStatus, Tool
from calendar_agent_protocol.persistence import Base, StateTransitionRow, make_engine
from calendar_agent_protocol.repository import (
    ClarificationRepository,
    ConcurrencyError,
    ConversationRepository,
    DuplicateId,
    InboundReceiptRepository,
    OperationRepository,
    StepRepository,
    TaskRepository,
    ToolExchangeRepository,
)


def test_conversation_duplicate_id_raises_duplicate_id_and_preserves_original(
    tmp_path: Path,
) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'conversation-duplicate.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        conversations = ConversationRepository(session)
        conversations.create("conv_duplicate", "Asia/Shanghai")
        session.commit()

        with pytest.raises(DuplicateId):
            conversations.create("conv_duplicate", "America/New_York")
        session.rollback()

    with Session(engine) as verification_session:
        original = ConversationRepository(verification_session).get("conv_duplicate")
        assert original is not None
        assert original.assistant_timezone == "Asia/Shanghai"


def test_conversation_not_found_read_and_mutation_have_distinct_semantics(
    tmp_path: Path,
) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'conversation-not-found.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        conversations = ConversationRepository(session)
        conversations.create("conv_existing", "Asia/Shanghai")
        session.commit()

        assert conversations.get("conv_missing") is None
        with pytest.raises(KeyError, match="conv_missing"):
            conversations.update_timezone("conv_missing", "America/New_York")
        session.commit()

    with Session(engine) as verification_session:
        conversations = ConversationRepository(verification_session)
        assert conversations.get("conv_missing") is None
        existing = conversations.get("conv_existing")
        assert existing is not None
        assert existing.assistant_timezone == "Asia/Shanghai"


def test_conversation_flushed_update_is_restored_by_caller_rollback(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'conversation-rollback.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        conversations = ConversationRepository(session)
        conversations.create("conv_rollback", "Asia/Shanghai")
        session.commit()

        conversations.update_timezone("conv_rollback", "America/New_York")
        observed_before_rollback = conversations.get("conv_rollback")
        assert observed_before_rollback is not None
        assert observed_before_rollback.assistant_timezone == "America/New_York"

        session.rollback()

    with Session(engine) as verification_session:
        persisted = ConversationRepository(verification_session).get("conv_rollback")
        assert persisted is not None
        assert persisted.assistant_timezone == "Asia/Shanghai"


def test_inbound_receipt_accept_commit_and_get(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'receipt-get.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ConversationRepository(session).create("conv_receipt", "UTC")
        TaskRepository(session).create(
            TaskEntity(
                "task_receipt",
                "conv_receipt",
                "查询日程",
                ObjectType.CALENDAR_EVENT,
                Intent.QUERY,
            )
        )
        receipts = InboundReceiptRepository(session)
        receipts.accept(
            request_id="req_receipt",
            conversation_id="conv_receipt",
            task_id="task_receipt",
            message_type="user_request",
            payload_hash="hash_receipt",
            response_payload={"type": "tool_request"},
        )
        session.commit()
        session.expire_all()

        receipt = receipts.get("req_receipt")
        assert receipt is not None
        assert receipt.payload_hash == "hash_receipt"
        assert receipt.response_payload == {"type": "tool_request"}


def test_inbound_receipt_replay_does_not_overwrite_cached_response(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'receipt-replay.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ConversationRepository(session).create("conv_receipt_replay", "UTC")
        TaskRepository(session).create(
            TaskEntity(
                "task_receipt_replay",
                "conv_receipt_replay",
                "查询日程",
                ObjectType.CALENDAR_EVENT,
                Intent.QUERY,
            )
        )
        receipts = InboundReceiptRepository(session)
        receipt_data = {
            "request_id": "req_receipt_replay",
            "conversation_id": "conv_receipt_replay",
            "task_id": "task_receipt_replay",
            "message_type": "user_request",
            "payload_hash": "a" * 64,
        }
        response_a = {"type": "tool_request", "step_id": "step_a"}
        response_b = {"type": "final", "status": "success"}
        receipts.accept(**receipt_data, response_payload=response_a)
        session.commit()

        replayed, created = receipts.accept(**receipt_data, response_payload=response_b)
        assert not created
        assert replayed.response_payload == response_a
        session.commit()

    with Session(engine) as verification_session:
        persisted = InboundReceiptRepository(verification_session).get("req_receipt_replay")
        assert persisted is not None
        assert persisted.response_payload == response_a


def test_transition_append_persists_immutable_audit_record(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'transition-append.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ConversationRepository(session).create("conv_transition", "UTC")
        TaskRepository(session).create(
            TaskEntity(
                "task_transition",
                "conv_transition",
                "查询日程",
                ObjectType.CALENDAR_EVENT,
                Intent.QUERY,
            )
        )
        transitions = repository_module.TransitionRepository(session)
        appended = transitions.append(
            task_id="task_transition",
            from_state="received",
            to_state="validating_input",
            reason="input_received",
        )
        transition_id = appended.id
        session.commit()
        session.expire_all()

        persisted = session.get(StateTransitionRow, transition_id)
        assert persisted is not None
        assert persisted.task_id == "task_transition"
        assert persisted.from_state == "received"
        assert persisted.to_state == "validating_input"
        assert persisted.reason == "input_received"


def test_transition_list_returns_only_task_records_in_stable_order(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'transition-list.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ConversationRepository(session).create("conv_transition_list", "UTC")
        tasks = TaskRepository(session)
        tasks.create(
            TaskEntity(
                "task_transition_list",
                "conv_transition_list",
                "查询日程",
                ObjectType.CALENDAR_EVENT,
                Intent.QUERY,
            )
        )
        tasks.create(
            TaskEntity(
                "task_transition_other",
                "conv_transition_list",
                "创建提醒",
                ObjectType.REMINDER,
                Intent.CREATE,
            )
        )
        transitions = repository_module.TransitionRepository(session)
        transitions.append(
            task_id="task_transition_list",
            from_state="received",
            to_state="validating_input",
            reason="first",
        )
        transitions.append(
            task_id="task_transition_other",
            from_state="received",
            to_state="validating_input",
            reason="other-task",
        )
        transitions.append(
            task_id="task_transition_list",
            from_state="validating_input",
            to_state="analyzing",
            reason="second",
        )
        session.commit()
        session.expire_all()

        records = transitions.list("task_transition_list")
        assert [record.reason for record in records] == ["first", "second"]
        assert [record.id for record in records] == sorted(record.id for record in records)


def test_conversation_update_timezone_persists(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'repository.db'}")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        repository = ConversationRepository(session)
        repository.create("conv_task_b", "Asia/Shanghai")
        session.commit()

        repository.update_timezone("conv_task_b", "America/New_York")
        session.commit()
        session.expire_all()

        persisted = repository.get("conv_task_b")
        assert persisted is not None
        assert persisted.assistant_timezone == "America/New_York"


def test_task_update_current_step_with_optimistic_version(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'task-update.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ConversationRepository(session).create("conv_task", "UTC")
        TaskRepository(session).create(
            TaskEntity("task_update", "conv_task", "测试", ObjectType.REMINDER, Intent.QUERY)
        )
        session.commit()

        TaskRepository(session).update_with_version(
            "task_update", expected_version=1, current_step_id="step_next"
        )
        session.commit()
        session.expire_all()

        task = TaskRepository(session).get("task_update")
        assert task is not None
        assert task.current_step_id == "step_next"
        assert task.version == 2


def test_task_stale_version_update_preserves_version_and_current_step(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'task-stale-update.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ConversationRepository(session).create("conv_stale_update", "UTC")
        TaskRepository(session).create(
            TaskEntity(
                "task_stale_update",
                "conv_stale_update",
                "查询日程",
                ObjectType.CALENDAR_EVENT,
                Intent.QUERY,
                current_step_id="step_old",
                version=3,
            )
        )
        session.commit()

        with pytest.raises(ConcurrencyError, match="task_stale_update"):
            TaskRepository(session).update_with_version(
                "task_stale_update",
                expected_version=2,
                current_step_id="step_new",
            )
        session.rollback()

    with Session(engine) as verification_session:
        persisted = TaskRepository(verification_session).get("task_stale_update")
        assert persisted is not None
        assert persisted.version == 3
        assert persisted.current_step_id == "step_old"


def test_task_parameter_upsert_and_get_persist_latest_value(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'parameter.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ConversationRepository(session).create("conv_parameter", "UTC")
        TaskRepository(session).create(
            TaskEntity(
                "task_parameter",
                "conv_parameter",
                "安排会议",
                ObjectType.CALENDAR_EVENT,
                Intent.CREATE,
            )
        )
        session.commit()

        parameters = repository_module.TaskParameterRepository(session)
        parameters.upsert(
            "task_parameter",
            "start_time",
            value="15:00",
            source="explicit",
            status="valid",
            evidence="用户说下午三点",
        )
        parameters.upsert(
            "task_parameter",
            "start_time",
            value="16:00",
            source="explicit",
            status="valid",
            evidence="用户澄清改成四点",
        )
        session.commit()
        session.expire_all()

        parameter = parameters.get("task_parameter", "start_time")
        assert parameter is not None
        assert parameter.value == "16:00"
        assert parameter.evidence == "用户澄清改成四点"


def test_task_parameter_list_returns_only_task_parameters_in_name_order(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'parameter-list.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ConversationRepository(session).create("conv_list", "UTC")
        tasks = TaskRepository(session)
        tasks.create(TaskEntity("task_list", "conv_list", "A", ObjectType.REMINDER, Intent.CREATE))
        tasks.create(TaskEntity("task_other", "conv_list", "B", ObjectType.REMINDER, Intent.CREATE))
        parameters = repository_module.TaskParameterRepository(session)
        for task_id, name in [
            ("task_list", "title"),
            ("task_list", "start_time"),
            ("task_other", "notes"),
        ]:
            parameters.upsert(
                task_id,
                name,
                value=name,
                source="explicit",
                status="valid",
                evidence=None,
            )
        session.commit()
        session.expire_all()

        assert [row.name for row in parameters.list("task_list")] == ["start_time", "title"]


def test_task_step_create_commit_and_get(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'step-get.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ConversationRepository(session).create("conv_step", "UTC")
        TaskRepository(session).create(
            TaskEntity(
                "task_step",
                "conv_step",
                "查询日程",
                ObjectType.CALENDAR_EVENT,
                Intent.QUERY,
            )
        )
        steps = StepRepository(session)
        steps.create(
            step_id="step_get",
            task_id="task_step",
            step_type="tool_query",
            status="in_progress",
            input_summary={"purpose": "answer_query"},
        )
        session.commit()
        session.expire_all()

        step = steps.get("step_get")
        assert step is not None
        assert step.task_id == "task_step"
        assert step.input_summary == {"purpose": "answer_query"}


def test_task_step_complete_persists_completion_fields(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'step-complete.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ConversationRepository(session).create("conv_step_complete", "UTC")
        TaskRepository(session).create(
            TaskEntity(
                "task_step_complete",
                "conv_step_complete",
                "查询日程",
                ObjectType.CALENDAR_EVENT,
                Intent.QUERY,
            )
        )
        steps = StepRepository(session)
        steps.create(
            step_id="step_complete",
            task_id="task_step_complete",
            step_type="tool_query",
            status="in_progress",
        )
        session.commit()

        steps.complete(
            "step_complete",
            output_summary={"result": "calendar query accepted"},
        )
        session.commit()
        session.expire_all()

        completed = steps.get("step_complete")
        assert completed is not None
        assert completed.status == "completed"
        assert completed.output_summary == {"result": "calendar query accepted"}
        assert completed.completed_at is not None


def test_tool_exchange_create_commit_and_get_with_dependencies(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'exchange-get.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ConversationRepository(session).create("conv_exchange", "UTC")
        TaskRepository(session).create(
            TaskEntity(
                "task_exchange",
                "conv_exchange",
                "检查冲突",
                ObjectType.CALENDAR_EVENT,
                Intent.CREATE,
            )
        )
        StepRepository(session).create(
            step_id="step_exchange",
            task_id="task_exchange",
            step_type="tool_query",
            status="in_progress",
        )
        exchanges = ToolExchangeRepository(session)
        exchanges.save_request(
            step_id="step_exchange",
            task_id="task_exchange",
            tool="query_calendar",
            purpose="check_conflict",
            request_payload={"tool": "query_calendar"},
            dependency_parameters={"start_time", "duration"},
        )
        session.commit()
        session.expire_all()

        exchange = exchanges.get("step_exchange")
        assert exchange is not None
        assert exchange.status == "pending"
        assert exchange.dependency_parameters == ["duration", "start_time"]


def test_tool_exchange_invalidate_persists_stale_metadata(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'exchange-invalidate.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ConversationRepository(session).create("conv_invalidate", "UTC")
        TaskRepository(session).create(
            TaskEntity(
                "task_invalidate",
                "conv_invalidate",
                "检查日程冲突",
                ObjectType.CALENDAR_EVENT,
                Intent.CREATE,
            )
        )
        StepRepository(session).create(
            step_id="step_invalidate",
            task_id="task_invalidate",
            step_type="tool_query",
            status="in_progress",
        )
        exchanges = ToolExchangeRepository(session)
        exchanges.save_request(
            step_id="step_invalidate",
            task_id="task_invalidate",
            tool="query_calendar",
            purpose="check_conflict",
            request_payload={"tool": "query_calendar"},
            dependency_parameters={"start_time"},
        )
        session.commit()

        before = exchanges.get("step_invalidate")
        assert before is not None
        assert before.is_stale is False
        assert before.stale_reason is None
        assert before.invalidated_at is None

        exchanges.invalidate("step_invalidate", "start_time changed")
        after = exchanges.get("step_invalidate")
        assert after is not None
        assert after.is_stale is True
        assert after.stale_reason == "start_time changed"
        assert after.invalidated_at is not None
        session.commit()

    with Session(engine) as verification_session:
        persisted = ToolExchangeRepository(verification_session).get("step_invalidate")
        assert persisted is not None
        assert persisted.is_stale is True
        assert persisted.stale_reason == "start_time changed"
        assert persisted.invalidated_at is not None


def test_clarification_get_pending_after_commit(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'clarification-get.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ConversationRepository(session).create("conv_clarification", "UTC")
        TaskRepository(session).create(
            TaskEntity(
                "task_clarification",
                "conv_clarification",
                "安排会议",
                ObjectType.CALENDAR_EVENT,
                Intent.CREATE,
            )
        )
        StepRepository(session).create(
            step_id="step_clarification",
            task_id="task_clarification",
            step_type="clarification",
            status="in_progress",
        )
        clarifications = ClarificationRepository(session)
        clarifications.save(
            step_id="step_clarification",
            task_id="task_clarification",
            reason="missing_required_parameter",
            message="会议持续多久？",
            expected_answer={"type": "duration"},
            missing_fields=["duration"],
            ambiguous_fields=None,
            blocked_from_state="planning",
        )
        session.commit()
        session.expire_all()

        pending = clarifications.get_pending("task_clarification")
        assert pending is not None
        assert pending.step_id == "step_clarification"
        assert pending.blocked_from_state == "planning"


def test_operation_create_commit_and_get(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'operation-get.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ConversationRepository(session).create("conv_operation", "UTC")
        TaskRepository(session).create(
            TaskEntity(
                "task_operation",
                "conv_operation",
                "创建提醒",
                ObjectType.REMINDER,
                Intent.CREATE,
            )
        )
        operations = OperationRepository(session)
        operations.create_or_replay(
            "op_get",
            "task_operation",
            Tool.CREATE_REMINDER,
            {"title": "提交报告"},
        )
        session.commit()
        session.expire_all()

        operation = operations.get("op_get")
        assert operation is not None
        assert operation.task_id == "task_operation"
        assert operation.status == "planned"


def test_operation_mark_dispatched_persists_controlled_fields(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'operation-dispatch.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ConversationRepository(session).create("conv_dispatch", "UTC")
        TaskRepository(session).create(
            TaskEntity(
                "task_dispatch",
                "conv_dispatch",
                "创建提醒",
                ObjectType.REMINDER,
                Intent.CREATE,
            )
        )
        operations = OperationRepository(session)
        operation, _ = operations.create_or_replay(
            "op_dispatch",
            "task_dispatch",
            Tool.CREATE_REMINDER,
            {"title": "提交报告"},
        )
        original_updated_at = operation.updated_at
        session.commit()

        operations.mark_dispatched("op_dispatch")
        session.commit()
        session.expire_all()

        persisted = operations.get("op_dispatch")
        assert persisted is not None
        assert persisted.status == "dispatched"
        assert persisted.updated_at.replace(tzinfo=None) >= original_updated_at.replace(tzinfo=None)


def test_operation_record_result_persists_status_and_payload(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'operation-result.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ConversationRepository(session).create("conv_result", "UTC")
        TaskRepository(session).create(
            TaskEntity(
                "task_result",
                "conv_result",
                "创建提醒",
                ObjectType.REMINDER,
                Intent.CREATE,
            )
        )
        operations = OperationRepository(session)
        operation, _ = operations.create_or_replay(
            "op_result",
            "task_result",
            Tool.CREATE_REMINDER,
            {"title": "提交报告"},
        )
        original_hash = operation.arguments_hash
        session.commit()

        operations.record_result(
            "op_result",
            status=OperationStatus.SUCCESS,
            result_payload={"reminder_id": "reminder_123"},
        )
        session.commit()
        session.expire_all()

        persisted = operations.get("op_result")
        assert persisted is not None
        assert persisted.status == "success"
        assert persisted.result_payload == {"reminder_id": "reminder_123"}
        assert persisted.arguments_hash == original_hash


def test_operation_record_verification_persists_verified_status(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'operation-verification.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ConversationRepository(session).create("conv_verification", "UTC")
        TaskRepository(session).create(
            TaskEntity(
                "task_verification",
                "conv_verification",
                "创建提醒",
                ObjectType.REMINDER,
                Intent.CREATE,
            )
        )
        operations = OperationRepository(session)
        operations.create_or_replay(
            "op_verification",
            "task_verification",
            Tool.CREATE_REMINDER,
            {"title": "提交报告"},
        )
        session.commit()

        operations.record_verification(
            "op_verification",
            status=OperationStatus.VERIFIED_SUCCESS,
        )
        session.commit()
        session.expire_all()

        persisted = operations.get("op_verification")
        assert persisted is not None
        assert persisted.status == "verified_success"
        assert persisted.verification_status == "verified_success"
