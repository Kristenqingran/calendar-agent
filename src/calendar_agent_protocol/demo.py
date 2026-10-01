"""Small local demo for the semantic-analysis and planning runtime slice."""

from __future__ import annotations

import argparse
import calendar
import json
import re
from datetime import date, datetime, timedelta
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from .apple_shortcut import AppleShortcutToolAdapter
from .dispatcher import MockToolAdapter, ToolDispatcher
from .enums import Tool
from .messages import UserRequest
from .persistence import Base, make_engine
from .repository import TaskRepository
from .response_language import (
    ResponseLanguage,
    clarification_copy,
    resolve_response_language,
)
from .runtime import AgentRuntime


class DemoLLM:
    """Deterministic local semantic adapter; no network or model call is made."""

    def __init__(self, needs_clarification: bool = False) -> None:
        self.needs_clarification = needs_clarification

    def analyze(self, request: UserRequest, context: Mapping[str, Any] | None = None) -> dict[str, Any]:
        context = context or {}
        turns = context.get("clarification_turns", [])
        prior_answers = [
            turn.get("answer") for turn in reversed(turns)
            if isinstance(turn, Mapping) and isinstance(turn.get("answer"), str)
        ]
        original_message = context.get("original_message")
        semantic_parts = [request.message, *prior_answers]
        if isinstance(original_message, str):
            semantic_parts.append(original_message)
        semantic_request = request.model_copy(update={"message": " ".join(semantic_parts)})
        parameters = _calendar_parameters(semantic_request)
        # Preserve facts already confirmed by earlier analysis if this answer
        # does not restate them; newly explicit text is first in semantic_parts.
        for name, previous in context.get("prior_parameters", {}).items():
            if not isinstance(previous, Mapping) or previous.get("status") != "valid":
                continue
            current = parameters.get(name)
            if current is None or current.get("status") != "valid" or current.get("value") is None:
                parameters[name] = dict(previous)
        language = resolve_response_language(
            request.message, [*prior_answers, original_message]
        )
        missing_fields = parameters.pop("_missing_fields", ["start", "end"])
        clarification = (
            _time_clarification(language, missing_fields)
            if self.needs_clarification or parameters.get("_needs_clarification")
            else None
        )
        parameters.pop("_needs_clarification", None)
        return {
            "actionable": True,
            "tasks": [{
                "sequence": 1,
                "object": "calendar_event",
                "intent": "create",
                "batch_write": False,
                "parameters": parameters,
            }],
            "background": [],
            "constraints": [],
            "needs_clarification": self.needs_clarification or clarification is not None,
            "clarification": clarification,
        }


def _calendar_parameters(request: UserRequest) -> dict[str, Any]:
    return _multilingual_calendar_parameters(request)


def _multilingual_calendar_parameters(request: UserRequest) -> dict[str, Any]:
    message = request.message
    timezone = ZoneInfo(request.assistant_timezone)
    local_now = request.current_time.astimezone(timezone)
    is_chinese_request = re.search(r"[\u3400-\u9fff]", message) is not None
    has_english_calendar_terms = re.search(r"\b(?:meeting|event|schedule|create)\b", message, re.IGNORECASE) is not None
    if "全天" in message or re.search(r"\ball[- ]day\b", message, re.IGNORECASE):
        event_date, date_status, date_evidence = _event_date(message, local_now.date())
        return {
            "title": _semantic_parameter(
                "Meeting" if has_english_calendar_terms or not is_chinese_request else "会议",
                "inferred_from_request",
                "valid",
                message,
            ),
            "all_day": _semantic_parameter(True, "explicit_request", "valid", "全天" if "全天" in message else "all day"),
            "date": _semantic_parameter(
                event_date.isoformat() if event_date else None,
                "explicit_request" if date_evidence else "missing",
                date_status,
                date_evidence or message,
            ),
            "start_date": _semantic_parameter(
                event_date.isoformat() if event_date else None,
                "explicit_request" if date_evidence else "missing",
                date_status,
                date_evidence or message,
            ),
            "end_date": _semantic_parameter(
                event_date.isoformat() if event_date else None,
                "explicit_request" if date_evidence else "missing",
                date_status,
                date_evidence or message,
            ),
        }

    title_match = re.search(
        r"\b(?:meeting|event)\s+(?:called|named)\s+[\"']?(.+?)"
        r"[\"']?(?=\s+(?:on|today|tomorrow)\b|\s*(?:明天|今天|上午|下午|晚上|早上|中午)|[.!?,]|$)",
        message,
        re.IGNORECASE,
    )
    if title_match:
        title = title_match.group(1).strip().strip("\"'")
        title_source = "explicit"
        title_evidence = title_match.group(0)
    else:
        person_match = re.search(
            r"\bmeeting\s+with\s+(.+?)(?=\s+(?:on|today|tomorrow|at)\b|\s*(?:明天|今天|上午|下午|晚上|早上|中午)|[,.!?]|$)",
            message,
            re.IGNORECASE,
        )
        chinese_person_match = re.search(
            r"和\s*(.+?)\s*(?=开|安排|创建|定|schedule\b|create\b)",
            message,
            re.IGNORECASE,
        )
        person = (
            person_match.group(1).strip()
            if person_match
            else chinese_person_match.group(1).strip()
            if chinese_person_match
            else None
        )
        if chinese_person_match and not person_match:
            title = f"和 {person} 开会"
            title_evidence = chinese_person_match.group(0)
        else:
            title = f"Meeting with {person}" if person else (
                "Meeting" if has_english_calendar_terms or not is_chinese_request else "会议"
            )
            title_evidence = person_match.group(0) if person_match else ("meeting" if not is_chinese_request else message)
        title_source = "inferred_from_request"

    parameters: dict[str, Any] = {
        "title": _semantic_parameter(title, title_source, "valid", title_evidence),
        "all_day": _semantic_parameter(False, "inferred_timed_event", "valid", message),
        "timezone": _semantic_parameter(
            request.assistant_timezone,
            "user_request.assistant_timezone",
            "valid",
            request.assistant_timezone,
        ),
    }

    event_date, date_status, date_evidence = _event_date(message, local_now.date())
    parameters["date"] = _semantic_parameter(
        event_date.isoformat() if event_date is not None else None,
        "explicit_request" if date_evidence else "missing",
        date_status,
        date_evidence or message,
    )

    english_time_match = re.search(
        r"\b(?:at\s+)?(?P<hour>1[0-2]|0?[1-9])(?::(?P<minute>[0-5]\d))?\s*"
        r"(?P<period>a\.?m\.?|p\.?m\.?)\b",
        message,
        re.IGNORECASE,
    )
    chinese_time_match = re.search(
        r"(?P<period>早上|上午|中午|下午|晚上)?\s*(?P<hour>\d{1,2})"
        r"(?:点|时)(?:(?P<minute>\d{1,2})分?)?",
        message,
    )
    time_match = english_time_match or chinese_time_match
    start: datetime | None = None
    if event_date is not None and time_match is not None:
        hour = int(time_match.group("hour"))
        period = time_match.groupdict().get("period")
        if english_time_match:
            hour %= 12
            if period.lower().startswith("p"):
                hour += 12
        elif period in {"下午", "晚上"} and hour < 12:
            hour += 12
        elif period == "上午" and hour == 12:
            hour = 0
        elif period == "中午" and hour < 11:
            hour += 12
        start = datetime.combine(
            event_date,
            datetime.min.time(),
            tzinfo=timezone,
        ).replace(hour=hour, minute=int(time_match.group("minute") or 0))
    parameters["start"] = _semantic_parameter(
        start.isoformat() if start else None,
        "explicit_request" if start else "missing",
        "valid" if start else "missing",
        time_match.group(0) if time_match else message,
    )

    english_duration_match = re.search(
        r"\b(?:for\s+)?(?P<amount>\d+(?:\.\d+)?|a|an|one|two|three|four|five|"
        r"six|seven|eight|nine|ten|eleven|twelve)\s*[- ]?\s*"
        r"(?P<unit>hours?|hrs?|minutes?|mins?)\b",
        message,
        re.IGNORECASE,
    )
    chinese_duration_match = re.search(
        r"(?P<amount>\d+|一|二|两|三|四|五|六|七|八|九|十)\s*(?:个)?小时|半小时",
        message,
    )
    duration_minutes = (
        _english_duration_minutes(english_duration_match)
        if english_duration_match
        else 30 if chinese_duration_match and chinese_duration_match.group(0) == "半小时"
        else _chinese_number(chinese_duration_match.group("amount")) * 60
        if chinese_duration_match
        else None
    )
    duration_match = english_duration_match or chinese_duration_match
    parameters["duration_minutes"] = _semantic_parameter(
        duration_minutes,
        "explicit_request" if duration_minutes is not None else "missing",
        "valid" if duration_minutes is not None else "missing",
        duration_match.group(0) if duration_match else message,
    )
    end = start + timedelta(minutes=duration_minutes) if start and duration_minutes else None
    parameters["end"] = _semantic_parameter(
        end.isoformat() if end else None,
        "derived_from_start_and_explicit_duration" if end else "missing",
        "valid" if end else "missing",
        duration_match.group(0) if duration_match else message,
    )

    missing_fields = []
    if start is None:
        missing_fields.append("start")
    if end is None:
        missing_fields.append("end")
    if missing_fields:
        parameters["_needs_clarification"] = True
        parameters["_missing_fields"] = missing_fields
    return parameters


def _semantic_parameter(value: Any, source: str, status: str, evidence: str) -> dict[str, Any]:
    return {"value": value, "source": source, "status": status, "evidence": evidence}


def _event_date(message: str, today: date) -> tuple[date | None, str, str | None]:
    if re.search(r"\btomorrow\b", message, re.IGNORECASE):
        return today + timedelta(days=1), "valid", "tomorrow"
    if re.search(r"\btoday\b", message, re.IGNORECASE):
        return today, "valid", "today"
    if "明天" in message:
        return today + timedelta(days=1), "valid", "明天"
    if "今天" in message:
        return today, "valid", "今天"

    chinese_date_match = re.search(r"(?P<month>\d{1,2})月(?P<day>\d{1,2})日?", message)
    if chinese_date_match:
        try:
            selected = date(today.year, int(chinese_date_match.group("month")), int(chinese_date_match.group("day")))
        except ValueError:
            return None, "invalid", chinese_date_match.group(0)
        if selected < today:
            selected = date(today.year + 1, selected.month, selected.day)
        return selected, "valid", chinese_date_match.group(0)

    months = sorted(
        {name for name in (*calendar.month_name[1:], *calendar.month_abbr[1:])},
        key=len,
        reverse=True,
    )
    month_pattern = "|".join(re.escape(name) for name in months)
    match = re.search(
        rf"\b(?P<month>{month_pattern})\s+(?P<day>\d{{1,2}})(?:st|nd|rd|th)?"
        rf"(?:,\s*(?P<year>\d{{4}}))?\b",
        message,
        re.IGNORECASE,
    )
    if match is None:
        return None, "missing", None

    month_lookup = {
        name.casefold(): index
        for index in range(1, 13)
        for name in (calendar.month_name[index], calendar.month_abbr[index])
    }
    year = int(match.group("year") or today.year)
    try:
        selected = date(year, month_lookup[match.group("month").casefold()], int(match.group("day")))
    except ValueError:
        return None, "invalid", match.group(0)
    if match.group("year") is None and selected < today:
        selected = date(year + 1, selected.month, selected.day)
    return selected, "valid", match.group(0)


def _english_duration_minutes(match: re.Match[str]) -> int | None:
    amount_text = match.group("amount").casefold()
    amounts = {
        "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4,
        "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
        "ten": 10, "eleven": 11, "twelve": 12,
    }
    amount = float(amounts[amount_text]) if amount_text in amounts else float(amount_text)
    multiplier = 60 if match.group("unit").casefold().startswith(("h",)) else 1
    minutes = amount * multiplier
    return int(minutes) if minutes > 0 and minutes.is_integer() else None


def _time_clarification(
    language: ResponseLanguage = ResponseLanguage.CHINESE,
    fields: list[str] | None = None,
) -> dict[str, Any]:
    fields = fields or ["start", "end"]
    return {
        "reason": "missing_required_parameter",
        "message": clarification_copy(language, "missing_required_parameter", fields),
        "fields": fields,
        "expected_answer_type": "datetime_range",
    }


def _chinese_number(value: str) -> int:
    if value.isdigit():
        return int(value)
    return {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
            "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}[value]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local Calendar Agent runtime demo")
    parser.add_argument("message", nargs="?", default="安排一个演示会议")
    parser.add_argument("--clarify", action="store_true", help="demo the clarification response")
    parser.add_argument("--real-shortcut", action="store_true", help="use APPLE_SHORTCUT_URL instead of the Mock adapter")
    args = parser.parse_args()

    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    request = UserRequest(
        type="user_request",
        request_id="req_demo_001",
        conversation_id="conv_demo_001",
        message=args.message,
        current_time="2026-09-24T10:00:00+08:00",
        assistant_timezone="Asia/Shanghai",
        source="local-cli-demo",
    )
    with Session(engine) as session:
        adapter = AppleShortcutToolAdapter() if args.real_shortcut else MockToolAdapter()
        dispatcher = ToolDispatcher({Tool.CREATE_CALENDAR_EVENT: adapter})
        response = AgentRuntime(session, DemoLLM(args.clarify), dispatcher).handle(request)
        output: dict[str, Any]
        if response.type == "tool_result":
            output = {"tool_result": response.model_dump(mode="json")}
            output["runtime_state"] = TaskRepository(session).snapshot(response.task_id).task.current_state.value
        else:
            output = {"response": response.model_dump(mode="json")}
        print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
