from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from calendar_agent_protocol.domain import StepStatus, StepType, TaskEntity
from calendar_agent_protocol.enums import Intent, ObjectType
from calendar_agent_protocol.persistence import Base, make_engine
from calendar_agent_protocol.repository import (
    ConversationRepository,
    StepRepository,
    TaskRepository,
    ToolExchangeRepository,
)


def config_for(path: Path) -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{path}")
    return cfg


def columns(path: Path) -> set[str]:
    return {
        item["name"]
        for item in inspect(create_engine(f"sqlite:///{path}")).get_columns("tool_exchanges")
    }


def test_0001_is_stable_snapshot_and_0002_owns_dependency_column(tmp_path: Path) -> None:
    source = Path("migrations/versions/0001_phase2.py").read_text()
    assert "Base.metadata" not in source
    db = tmp_path / "migration.db"
    cfg = config_for(db)
    command.upgrade(cfg, "0001_phase2")
    assert "dependency_parameters" not in columns(db)
    command.upgrade(cfg, "head")
    assert "dependency_parameters" in columns(db)
    command.downgrade(cfg, "0001_phase2")
    assert "dependency_parameters" not in columns(db)
    command.upgrade(cfg, "head")
    assert "dependency_parameters" in columns(db)


def test_dependency_parameters_orm_and_restart_snapshot(tmp_path: Path) -> None:
    db = tmp_path / "roundtrip.db"
    engine = make_engine(f"sqlite:///{db}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ConversationRepository(session).create("conv_a", "Asia/Shanghai")
        TaskRepository(session).create(
            TaskEntity("task_a", "conv_a", "测试", ObjectType.CALENDAR_EVENT, Intent.QUERY)
        )
        StepRepository(session).create(
            step_id="step_a",
            task_id="task_a",
            step_type=StepType.TOOL_QUERY.value,
            status=StepStatus.IN_PROGRESS.value,
        )
        ToolExchangeRepository(session).save_request(
            step_id="step_a",
            task_id="task_a",
            tool="query_calendar",
            purpose="check_conflict",
            request_payload={},
            dependency_parameters={"start_time", "duration"},
        )
        session.commit()
    engine.dispose()
    restarted = make_engine(f"sqlite:///{db}")
    with Session(restarted) as session:
        exchange = TaskRepository(session).snapshot("task_a").tool_exchanges[0]
        assert exchange["dependency_parameters"] == ["duration", "start_time"]


def test_empty_dependency_set_is_valid(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ConversationRepository(session).create("conv_b", "UTC")
        TaskRepository(session).create(
            TaskEntity("task_b", "conv_b", "测试", ObjectType.REMINDER, Intent.QUERY)
        )
        StepRepository(session).create(
            step_id="step_b", task_id="task_b", step_type="tool_query", status="in_progress"
        )
        row = ToolExchangeRepository(session).save_request(
            step_id="step_b",
            task_id="task_b",
            tool="query_reminders",
            purpose="answer_query",
            request_payload={},
            dependency_parameters=set(),
        )
        assert row.dependency_parameters == []
