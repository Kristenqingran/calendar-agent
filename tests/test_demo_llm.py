import pytest

from calendar_agent_protocol.demo import DemoLLM
from calendar_agent_protocol.messages import UserRequest


def request(message: str, current_time: str = "2026-09-24T10:00:00+08:00") -> UserRequest:
    return UserRequest(
        type="user_request", request_id="req_001", conversation_id="conv_001",
        message=message, current_time=current_time,
        assistant_timezone="Asia/Shanghai", source="test",
    )


def test_demo_llm_extracts_calendar_create_semantics():
    result = DemoLLM().analyze(request("明天下午3点和 Bob 开一个小时的会"))
    task = result["tasks"][0]
    parameters = task["parameters"]
    assert task["object"] == "calendar_event"
    assert task["intent"] == "create"
    assert "Bob" in parameters["title"]["value"]
    assert parameters["start"]["value"] == "2026-09-25T15:00:00+08:00"
    assert parameters["end"]["value"] == "2026-09-25T16:00:00+08:00"
    assert parameters["all_day"]["value"] is False
    assert result["needs_clarification"] is False


def test_demo_llm_preserves_morning_nine_as_local_nine():
    result = DemoLLM().analyze(request("明天早上9点和 Bob 开一个小时的会"))
    parameters = result["tasks"][0]["parameters"]

    assert parameters["start"]["value"] == "2026-09-25T09:00:00+08:00"
    assert parameters["end"]["value"] == "2026-09-25T10:00:00+08:00"


def test_demo_llm_uses_request_time_for_tomorrow():
    result = DemoLLM().analyze(request("明天下午3点和 Bob 开一个小时的会", "2027-01-31T23:00:00+08:00"))
    assert result["tasks"][0]["parameters"]["start"]["value"] == "2027-02-01T15:00:00+08:00"


def test_demo_llm_does_not_guess_missing_concrete_time():
    result = DemoLLM().analyze(request("明天和 Bob 开会"))
    assert result["needs_clarification"] is True
    assert result["clarification"]["fields"] == ["start", "end"]
    assert result["clarification"]["message"] == "请提供会议的具体开始时间和时长。"


def test_demo_llm_uses_english_for_english_clarification():
    result = DemoLLM().analyze(request("Create a meeting tomorrow."))

    assert result["needs_clarification"] is True
    assert result["clarification"]["message"] == (
        "What time should the meeting start, and how long should it last?"
    )


def test_demo_llm_does_not_guess_missing_english_duration():
    result = DemoLLM().analyze(request("Create a meeting tomorrow at 3 PM."))
    parameters = result["tasks"][0]["parameters"]

    assert parameters["start"]["value"] == "2026-09-25T15:00:00+08:00"
    assert parameters["start"]["status"] == "valid"
    assert parameters["duration_minutes"]["status"] == "missing"
    assert parameters["end"]["value"] is None
    assert parameters["end"]["status"] == "missing"
    assert result["needs_clarification"] is True
    assert result["clarification"]["fields"] == ["end"]
    assert result["clarification"]["message"] == "How long should the meeting last?"


@pytest.mark.parametrize(
    ("message", "expected_title", "expected_start"),
    [
        (
            "Create a meeting called Test Meeting on September 30 at 3 PM for one hour.",
            "Test Meeting",
            "2026-09-30T15:00:00+08:00",
        ),
        (
            "Create a meeting tomorrow at 3 PM for one hour.",
            "Meeting",
            "2026-09-25T15:00:00+08:00",
        ),
        (
            "Schedule a one-hour meeting with Bob tomorrow at 3 PM.",
            "Meeting with Bob",
            "2026-09-25T15:00:00+08:00",
        ),
    ],
)
def test_demo_llm_extracts_complete_english_calendar_create(
    message: str, expected_title: str, expected_start: str
):
    analysis = DemoLLM().analyze(request(message))
    task = analysis["tasks"][0]
    parameters = task["parameters"]

    assert task["object"] == "calendar_event"
    assert task["intent"] == "create"
    assert parameters["title"]["value"] == expected_title
    assert parameters["title"]["status"] == "valid"
    assert parameters["start"]["value"] == expected_start
    assert parameters["start"]["status"] == "valid"
    start_hour = int(expected_start[11:13])
    expected_end = expected_start[:11] + f"{start_hour + 1:02d}" + expected_start[13:]
    assert parameters["end"]["value"] == expected_end
    assert parameters["end"]["status"] == "valid"
    assert parameters["date"]["value"] == expected_start[:10]
    assert parameters["date"]["status"] == "valid"
    assert parameters["duration_minutes"]["value"] == 60
    assert parameters["duration_minutes"]["status"] == "valid"
    assert parameters["timezone"]["value"] == "Asia/Shanghai"
    assert parameters["timezone"]["source"] == "user_request.assistant_timezone"
    assert analysis["needs_clarification"] is False


def test_demo_llm_does_not_turn_afternoon_into_fixed_time():
    result = DemoLLM().analyze(request("明天下午和 Bob 开会"))
    assert result["needs_clarification"] is True


@pytest.mark.parametrize(
    ("message", "expected_title", "expected_start"),
    [
        (
            "Schedule a meeting with Bob 明天下午3点 for one hour.",
            "Meeting with Bob",
            "2026-09-25T15:00:00+08:00",
        ),
        (
            "明天和 Bob 开会 at 3 PM for one hour.",
            "和 Bob 开会",
            "2026-09-25T15:00:00+08:00",
        ),
        (
            "Create a meeting 明天早上9点 for 一小时.",
            "Meeting",
            "2026-09-25T09:00:00+08:00",
        ),
    ],
)
def test_demo_llm_extracts_calendar_fields_across_languages(
    message: str, expected_title: str, expected_start: str
):
    analysis = DemoLLM().analyze(request(message))
    task = analysis["tasks"][0]
    parameters = task["parameters"]

    assert parameters["title"]["value"] == expected_title
    assert parameters["start"]["value"] == expected_start
    assert parameters["end"]["value"] == (
        expected_start[:11]
        + f"{int(expected_start[11:13]) + 1:02d}"
        + expected_start[13:]
    )
    assert parameters["duration_minutes"]["value"] == 60
    assert analysis["needs_clarification"] is False


def test_demo_llm_supports_explicit_all_day_event():
    result = DemoLLM().analyze(request("明天全天会议"))
    parameters = result["tasks"][0]["parameters"]
    assert parameters["all_day"]["value"] is True
    assert parameters["start_date"]["value"] == "2026-09-25"
    assert parameters["end_date"]["value"] == "2026-09-25"
