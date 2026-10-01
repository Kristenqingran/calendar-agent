from enum import StrEnum


class ObjectType(StrEnum):
    CALENDAR_EVENT = "calendar_event"
    REMINDER = "reminder"


class Intent(StrEnum):
    QUERY = "query"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


class Purpose(StrEnum):
    ANSWER_QUERY = "answer_query"
    CHECK_CONFLICT = "check_conflict"
    DETECT_DUPLICATE = "detect_duplicate"
    FIND_AVAILABILITY = "find_availability"
    RESOLVE_TARGET = "resolve_target"
    VERIFY_STATE = "verify_state"


class QueryScope(StrEnum):
    ALL_INCOMPLETE = "all_incomplete"
    SPECIFIC_LIST = "specific_list"
    TIME_RANGE = "time_range"


class Tool(StrEnum):
    QUERY_CALENDAR = "query_calendar"
    QUERY_REMINDERS = "query_reminders"
    CREATE_CALENDAR_EVENT = "create_calendar_event"
    UPDATE_CALENDAR_EVENT = "update_calendar_event"
    DELETE_CALENDAR_EVENT = "delete_calendar_event"
    CREATE_REMINDER = "create_reminder"
    UPDATE_REMINDER = "update_reminder"
    DELETE_REMINDER = "delete_reminder"

    @property
    def is_query(self) -> bool:
        return self in {self.QUERY_CALENDAR, self.QUERY_REMINDERS}

    @property
    def is_write(self) -> bool:
        return not self.is_query


class TaskStatus(StrEnum):
    RECEIVED = "received"
    VALIDATING_INPUT = "validating_input"
    ANALYZING = "analyzing"
    PLANNING = "planning"
    WAITING_TOOL_RESULT = "waiting_tool_result"
    VALIDATING_TOOL_RESULT = "validating_tool_result"
    WAITING_CLARIFICATION = "waiting_clarification"
    ANALYZING_CLARIFICATION = "analyzing_clarification"
    PRE_EXECUTION_CHECK = "pre_execution_check"
    VERIFYING_FINAL_STATE = "verifying_final_state"
    RECOVERING = "recovering"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"


class ToolStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    UNKNOWN = "unknown"


class OperationStatus(StrEnum):
    PLANNED = "planned"
    DISPATCHED = "dispatched"
    SUCCESS = "success"
    FAILED = "failed"
    UNKNOWN = "unknown"
    VERIFIED_SUCCESS = "verified_success"
    VERIFIED_FAILURE = "verified_failure"


class ResponseType(StrEnum):
    CLARIFICATION = "clarification"
    FINAL = "final"


class InboundMessageType(StrEnum):
    USER_REQUEST = "user_request"
    CLARIFICATION_RESPONSE = "clarification_response"


class FinalStatus(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    UNKNOWN = "unknown"


class ClarificationReason(StrEnum):
    MISSING_REQUIRED_PARAMETER = "missing_required_parameter"
    AMBIGUOUS_PARAMETER = "ambiguous_parameter"
    AMBIGUOUS_TARGET = "ambiguous_target"
    SCHEDULE_CONFLICT = "schedule_conflict"
    POSSIBLE_DUPLICATE = "possible_duplicate"
    TOOL_RESULT_UNCERTAIN = "tool_result_uncertain"
    RECOVERY_DECISION_REQUIRED = "recovery_decision_required"
