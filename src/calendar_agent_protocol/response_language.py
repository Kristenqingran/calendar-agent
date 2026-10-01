"""Deterministic language selection and user-facing response copy."""

from __future__ import annotations

import unicodedata
from enum import StrEnum
from typing import Iterable


class ResponseLanguage(StrEnum):
    CHINESE = "zh"
    ENGLISH = "en"


def detect_response_language(text: str | None) -> ResponseLanguage | None:
    """Detect Chinese or English from script, independent of host/device locale."""
    if not text:
        return None
    han = 0
    latin = 0
    for character in text:
        name = unicodedata.name(character, "")
        if "CJK UNIFIED IDEOGRAPH" in name or "CJK COMPATIBILITY IDEOGRAPH" in name:
            han += 1
        elif name.startswith("LATIN ") and character.isalpha():
            latin += 1
    if han and han >= latin:
        return ResponseLanguage.CHINESE
    if latin >= 3 and latin > han:
        return ResponseLanguage.ENGLISH
    return None


def resolve_response_language(
    current_text: str | None,
    previous_texts: Iterable[str | None] = (),
) -> ResponseLanguage:
    """Prefer the current utterance, then recent conversation context, then zh."""
    detected = detect_response_language(current_text)
    if detected is not None:
        return detected
    for text in previous_texts:
        detected = detect_response_language(text)
        if detected is not None:
            return detected
    return ResponseLanguage.CHINESE


def clarification_copy(
    language: ResponseLanguage,
    reason: str,
    fields: Iterable[str] = (),
    candidate: str | None = None,
) -> str:
    """Keep matching semantic copy, otherwise use deterministic localized copy."""
    if candidate and detect_response_language(candidate) == language:
        return candidate
    names = set(fields)
    if reason == "missing_required_parameter" and {"start", "end"}.issubset(names):
        return _text(
            language,
            "What time should the meeting start, and how long should it last?",
            "请提供会议的具体开始时间和时长。",
        )
    if reason == "missing_required_parameter" and "start" in names:
        return _text(language, "What date and time should the meeting start?", "请提供会议的具体日期和开始时间。")
    if reason == "missing_required_parameter" and "end" in names:
        return _text(language, "How long should the meeting last?", "请提供会议时长。")
    messages = {
        "missing_required_parameter": (
            "Please provide the missing information.", "请补充完成该操作所需的信息。"
        ),
        "ambiguous_parameter": (
            "Please clarify the ambiguous details.", "请澄清不明确的信息。"
        ),
        "ambiguous_target": (
            "Which matching item do you mean?", "请确认你指的是哪一个事项。"
        ),
        "schedule_conflict": (
            "The requested time conflicts with another event. How would you like to proceed?",
            "请求的时间与其他日程冲突，请确认如何处理。",
        ),
        "possible_duplicate": (
            "A similar event may already exist. Should I continue?",
            "可能已经存在相似日程，请确认是否继续。",
        ),
        "tool_result_uncertain": (
            "I couldn't confirm the operation result. How would you like to proceed?",
            "无法确认操作结果，请告知接下来如何处理。",
        ),
        "recovery_decision_required": (
            "I need your guidance before continuing.", "继续之前需要你确认处理方式。"
        ),
    }
    english, chinese = messages.get(
        reason,
        ("Please provide the information needed to continue.", "请补充继续操作所需的信息。"),
    )
    return _text(language, english, chinese)


def final_copy(
    language: ResponseLanguage,
    status: str,
    *,
    error_code: str | None = None,
    tool: str | None = None,
) -> str:
    """Build concise user-facing Final text for the selected language."""
    if status == "success" and tool == "create_calendar_event":
        return _text(
            language, "The calendar event was created and verified.", "日历事件已创建并验证。"
        )
    if status == "success" and tool == "query_calendar":
        return _text(language, "The calendar query is complete.", "日历查询已完成。")
    if status == "unknown":
        return _text(
            language,
            "I couldn't confirm whether the operation completed.",
            "无法确认操作是否完成。",
        )
    if error_code == "unsupported_operation":
        return _text(
            language, "This operation is not supported yet.", "当前暂不支持此操作。"
        )
    if error_code == "verification_failed":
        return _text(
            language,
            "The calendar event could not be confirmed with the requested details.",
            "无法确认日历事件与请求内容一致。",
        )
    if error_code == "malformed_mac_host_response":
        return _text(
            language,
            "The Calendar service returned an invalid response, so the operation was not confirmed.",
            "日历服务返回了无效响应，因此无法确认操作结果。",
        )
    return _text(
        language, "The requested operation could not be completed.", "请求的操作未能完成。"
    )


def _text(language: ResponseLanguage, english: str, chinese: str) -> str:
    return english if language == ResponseLanguage.ENGLISH else chinese


__all__ = [
    "ResponseLanguage",
    "clarification_copy",
    "detect_response_language",
    "final_copy",
    "resolve_response_language",
]
