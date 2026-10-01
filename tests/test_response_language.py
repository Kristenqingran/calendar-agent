from calendar_agent_protocol.response_language import (
    ResponseLanguage,
    detect_response_language,
    resolve_response_language,
)


def test_detects_chinese_and_english_without_system_locale():
    assert detect_response_language("明天安排会议") == ResponseLanguage.CHINESE
    assert detect_response_language("Create a meeting tomorrow") == ResponseLanguage.ENGLISH


def test_unclear_current_message_inherits_recent_conversation_language():
    assert resolve_response_language("9?", ["Create a meeting tomorrow"]) == ResponseLanguage.ENGLISH
    assert resolve_response_language("好", ["Create a meeting tomorrow"]) == ResponseLanguage.CHINESE


def test_unclear_first_message_uses_deterministic_chinese_fallback():
    assert resolve_response_language("9?", []) == ResponseLanguage.CHINESE
