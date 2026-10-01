from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

ProtocolId = Annotated[str, Field(min_length=3, max_length=128, pattern=r"^[a-z]+_[A-Za-z0-9_-]+$")]
RequestId = ProtocolId
ExecutionId = Annotated[str, Field(min_length=3, max_length=128, pattern=r"^exec_[A-Za-z0-9_-]+$")]
OperationExecutionId = ExecutionId
CauseRequestId = ProtocolId
ConversationId = ProtocolId
TaskId = ProtocolId
StepId = ProtocolId
OperationId = ProtocolId
StableId = Annotated[str, Field(min_length=1)]
NonEmptyString = Annotated[str, Field(min_length=1)]


def _aware_datetime(value: datetime) -> datetime:
    if value.utcoffset() is None:
        raise ValueError("datetime must include a UTC offset")
    return value


OffsetDateTime = Annotated[datetime, AfterValidator(_aware_datetime)]


def _iana_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("timezone must be a valid IANA timezone name") from exc
    return value


IanaTimezone = Annotated[str, Field(min_length=1), AfterValidator(_iana_timezone)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TimeRange(StrictModel):
    start: OffsetDateTime
    end: OffsetDateTime

    @model_validator(mode="after")
    def end_is_after_start(self) -> TimeRange:
        if self.end <= self.start:
            raise ValueError("end must be later than start")
        return self


class DefaultCalendar(StrictModel):
    calendar_id: StableId | None
    name: NonEmptyString


class ErrorModel(StrictModel):
    code: NonEmptyString
    message: NonEmptyString
    retryable: bool
    details: dict[str, Any] | None = None


class TimedCalendarEvent(StrictModel):
    event_id: StableId
    title: NonEmptyString
    all_day: bool
    start: OffsetDateTime
    end: OffsetDateTime
    calendar_id: StableId | None = None
    location: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def validate_timed_event(self) -> TimedCalendarEvent:
        if self.all_day:
            raise ValueError("timed event must have all_day=false")
        if self.end <= self.start:
            raise ValueError("end must be later than start")
        return self


class AllDayCalendarEvent(StrictModel):
    event_id: StableId
    title: NonEmptyString
    all_day: bool
    start_date: date
    end_date: date
    calendar_id: StableId | None = None
    location: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def validate_all_day_event(self) -> AllDayCalendarEvent:
        if not self.all_day:
            raise ValueError("all-day event must have all_day=true")
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class Reminder(StrictModel):
    reminder_id: StableId
    title: NonEmptyString
    completed: bool
    list_id: StableId | None = None
    reminder_time: OffsetDateTime | None = None
    notes: str | None = None
