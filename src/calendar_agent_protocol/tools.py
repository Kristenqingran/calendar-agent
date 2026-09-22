from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal

from pydantic import Field, model_validator

from .enums import Purpose, QueryScope, Tool
from .types import (
    NonEmptyString,
    OffsetDateTime,
    OperationId,
    ProtocolId,
    StableId,
    StrictModel,
)


class QueryCalendarArguments(StrictModel):
    start: OffsetDateTime | None = None
    end: OffsetDateTime | None = None
    required_duration_minutes: int | None = Field(default=None, ge=1)
    target_id: StableId | None = None
    candidate: dict[str, Any] | None = None
    filters: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_range(self) -> QueryCalendarArguments:
        if (self.start is None) != (self.end is None):
            raise ValueError("start and end must be supplied together")
        if self.start is not None and self.end is not None and self.end <= self.start:
            raise ValueError("end must be later than start")
        return self


class AllIncompleteReminderQuery(StrictModel):
    query_scope: Literal[QueryScope.ALL_INCOMPLETE]
    filters: dict[str, Any] | None = None


class SpecificListReminderQuery(StrictModel):
    query_scope: Literal[QueryScope.SPECIFIC_LIST]
    list_id: StableId
    filters: dict[str, Any] | None = None


class TimeRangeReminderQuery(StrictModel):
    query_scope: Literal[QueryScope.TIME_RANGE]
    start: OffsetDateTime
    end: OffsetDateTime
    filters: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_range(self) -> TimeRangeReminderQuery:
        if self.end <= self.start:
            raise ValueError("end must be later than start")
        return self


ReminderQueryArguments = Annotated[
    AllIncompleteReminderQuery | SpecificListReminderQuery | TimeRangeReminderQuery,
    Field(discriminator="query_scope"),
]


class TimedEventCreateArguments(StrictModel):
    title: NonEmptyString
    all_day: Literal[False]
    start: OffsetDateTime
    end: OffsetDateTime
    calendar_id: StableId | None = None
    calendar_name: str | None = None
    location: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def validate_range(self) -> TimedEventCreateArguments:
        if self.end <= self.start:
            raise ValueError("end must be later than start")
        return self


class AllDayEventCreateArguments(StrictModel):
    title: NonEmptyString
    all_day: Literal[True]
    start_date: date
    end_date: date
    calendar_id: StableId | None = None
    calendar_name: str | None = None
    location: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def validate_range(self) -> AllDayEventCreateArguments:
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


CalendarCreateArguments = Annotated[
    TimedEventCreateArguments | AllDayEventCreateArguments,
    Field(discriminator="all_day"),
]


class CalendarEventChanges(StrictModel):
    title: NonEmptyString | None = None
    start: OffsetDateTime | None = None
    end: OffsetDateTime | None = None
    all_day: bool | None = None
    start_date: date | None = None
    end_date: date | None = None
    location: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def at_least_one_change(self) -> CalendarEventChanges:
        if not self.model_fields_set:
            raise ValueError("changes must contain at least one field")
        if self.start is not None and self.end is not None and self.end <= self.start:
            raise ValueError("end must be later than start")
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.end_date < self.start_date
        ):
            raise ValueError("end_date must be on or after start_date")
        return self


class UpdateCalendarArguments(StrictModel):
    event_id: StableId
    changes: CalendarEventChanges
    calendar_id: StableId | None = None


class DeleteCalendarArguments(StrictModel):
    event_id: StableId
    calendar_id: StableId | None = None


class CreateReminderArguments(StrictModel):
    title: NonEmptyString
    reminder_time: OffsetDateTime
    list_id: StableId | None = None
    notes: str | None = None


class ReminderChanges(StrictModel):
    title: NonEmptyString | None = None
    reminder_time: OffsetDateTime | None = None
    completed: bool | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def at_least_one_change(self) -> ReminderChanges:
        if not self.model_fields_set:
            raise ValueError("changes must contain at least one field")
        return self


class UpdateReminderArguments(StrictModel):
    reminder_id: StableId
    changes: ReminderChanges
    list_id: StableId | None = None


class DeleteReminderArguments(StrictModel):
    reminder_id: StableId
    list_id: StableId | None = None


class ToolRequestBase(StrictModel):
    type: Literal["tool_request"]
    request_id: ProtocolId
    conversation_id: ProtocolId
    task_id: ProtocolId
    step_id: ProtocolId


class QueryCalendarRequest(ToolRequestBase):
    tool: Literal[Tool.QUERY_CALENDAR]
    purpose: Purpose
    arguments: QueryCalendarArguments


class QueryRemindersRequest(ToolRequestBase):
    tool: Literal[Tool.QUERY_REMINDERS]
    purpose: Purpose
    arguments: ReminderQueryArguments


class WriteRequestBase(ToolRequestBase):
    operation_id: OperationId


class CreateCalendarEventRequest(WriteRequestBase):
    tool: Literal[Tool.CREATE_CALENDAR_EVENT]
    arguments: CalendarCreateArguments


class UpdateCalendarEventRequest(WriteRequestBase):
    tool: Literal[Tool.UPDATE_CALENDAR_EVENT]
    arguments: UpdateCalendarArguments


class DeleteCalendarEventRequest(WriteRequestBase):
    tool: Literal[Tool.DELETE_CALENDAR_EVENT]
    arguments: DeleteCalendarArguments


class CreateReminderRequest(WriteRequestBase):
    tool: Literal[Tool.CREATE_REMINDER]
    arguments: CreateReminderArguments


class UpdateReminderRequest(WriteRequestBase):
    tool: Literal[Tool.UPDATE_REMINDER]
    arguments: UpdateReminderArguments


class DeleteReminderRequest(WriteRequestBase):
    tool: Literal[Tool.DELETE_REMINDER]
    arguments: DeleteReminderArguments


ToolRequest = Annotated[
    QueryCalendarRequest
    | QueryRemindersRequest
    | CreateCalendarEventRequest
    | UpdateCalendarEventRequest
    | DeleteCalendarEventRequest
    | CreateReminderRequest
    | UpdateReminderRequest
    | DeleteReminderRequest,
    Field(discriminator="tool"),
]
