import pytest
from pydantic import TypeAdapter, ValidationError

from calendar_agent_protocol.types import (
    AllDayCalendarEvent,
    Reminder,
    TimedCalendarEvent,
)


def test_timed_calendar_event() -> None:
    event = TimedCalendarEvent.model_validate(
        {
            "event_id": "event_123",
            "calendar_id": "cal_123",
            "title": "客户会议",
            "all_day": False,
            "start": "2026-09-05T15:00:00+08:00",
            "end": "2026-09-05T16:00:00+08:00",
        }
    )
    assert event.all_day is False


def test_all_day_calendar_event_uses_inclusive_local_dates() -> None:
    event = AllDayCalendarEvent.model_validate(
        {
            "event_id": "event_124",
            "title": "休假",
            "all_day": True,
            "start_date": "2026-09-05",
            "end_date": "2026-09-05",
        }
    )
    assert event.start_date == event.end_date


def test_all_day_calendar_event_rejects_reverse_dates() -> None:
    with pytest.raises(ValidationError):
        AllDayCalendarEvent.model_validate(
            {
                "event_id": "event_124",
                "title": "休假",
                "all_day": True,
                "start_date": "2026-09-06",
                "end_date": "2026-09-05",
            }
        )


def test_reminder_contract() -> None:
    reminder = Reminder.model_validate(
        {
            "reminder_id": "rem_123",
            "list_id": "list_123",
            "title": "交报告",
            "reminder_time": "2026-09-05T17:00:00+08:00",
            "completed": False,
        }
    )
    assert reminder.completed is False


def test_calendar_event_discriminator_shape_is_exclusive() -> None:
    adapter = TypeAdapter(TimedCalendarEvent | AllDayCalendarEvent)
    with pytest.raises(ValidationError):
        adapter.validate_python(
            {
                "event_id": "event_123",
                "title": "错误混合事件",
                "all_day": True,
                "start": "2026-09-05T15:00:00+08:00",
                "end": "2026-09-05T16:00:00+08:00",
            }
        )
