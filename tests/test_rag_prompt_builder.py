import pytest

from leoai.rag_prompt_builder import (
    AgentOrchestrator,
    CURRENT_QUESTION_INSTRUCTIONS,
    DOCUMENT_CHAT_INSTRUCTIONS,
    PLACE_FOLLOWUP_INSTRUCTIONS,
)


@pytest.mark.parametrize(
    "question",
    [
        "How do I write a Python function?",
        "What are the opening hours of the selected church?",
        "2",
        "option 2",
        "chọn 2",
        "history",
        "Why?",
    ],
)
def test_current_request_and_selection_rules_reach_prompt_and_system(question):
    context = {
        "user_context": {
            "selected_place": {"id": 42, "name": "Selected Church"},
            "place_choices": [
                {"id": 42, "name": "Selected Church"},
                {"id": 7, "name": "Local Cafe"},
            ],
        },
        "context_summary": "Previously discussing church history.",
    }

    prompt = AgentOrchestrator().build_prompt(question, context, "English")

    assert CURRENT_QUESTION_INSTRUCTIONS in prompt.prompt_text
    assert CURRENT_QUESTION_INSTRUCTIONS in prompt.system_instruction
    assert PLACE_FOLLOWUP_INSTRUCTIONS in prompt.system_instruction
    assert f"### User’s Current Question\n{question}" in prompt.prompt_text
    assert "Local Cafe" in prompt.prompt_text
    assert prompt.prompt_text.index("### Current request priority") < (
        prompt.prompt_text.index("### User Context")
    )
    assert context["user_context"]["selected_place"]["id"] == 42


@pytest.mark.parametrize(
    ("language", "expected"),
    [("", "the user's language"), ("Vietnamese", "Vietnamese")],
)
def test_language_instruction_is_explicit_with_or_without_target(language, expected):
    prompt = AgentOrchestrator().build_prompt("Why?", {}, language)

    assert f"Respond in {expected}." in prompt.prompt_text
    assert "No place has been selected." in prompt.prompt_text
    assert "End with an insightful remark" not in prompt.prompt_text


@pytest.mark.parametrize(
    "question",
    [
        "Hi, summarize the guide and explain its limitations.",
        "Compare the two policies and cite their sources.",
        "What does the second option mean?",
        "What about its exceptions?",
    ],
)
def test_document_rules_reach_prompt_and_system_without_place_rules(question):
    context = {
        "user_context": {
            "selected_place": {"name": "Cached Church"},
            "place_choices": [{"name": "Cached Market"}],
            "nearby_places": [{"name": "Cached Cafe"}],
            "latitude": 10.75,
            "longitude": 106.65,
            "document_topic": "Policy exceptions",
        },
        "context_summary": "Comparing two document policies.",
    }
    excerpts = "Source: Policy Guide\nURI: https://example.com/guide\nExceptions apply."

    prompt = AgentOrchestrator().build_document_prompt(
        question, context, excerpts, "Vietnamese",
    )

    assert DOCUMENT_CHAT_INSTRUCTIONS in prompt.prompt_text
    assert prompt.system_instruction == DOCUMENT_CHAT_INSTRUCTIONS
    assert CURRENT_QUESTION_INSTRUCTIONS not in prompt.prompt_text
    assert PLACE_FOLLOWUP_INSTRUCTIONS not in prompt.prompt_text
    assert f"### User's current question\n{question}" in prompt.prompt_text
    assert excerpts in prompt.prompt_text
    assert "Policy exceptions" in prompt.prompt_text
    assert "Comparing two document policies." in prompt.prompt_text
    assert "Respond in Vietnamese." in prompt.prompt_text
    for cached_value in ("Cached Church", "Cached Market", "Cached Cafe", "10.75", "106.65"):
        assert cached_value not in prompt.prompt_text
    assert context["user_context"]["selected_place"]["name"] == "Cached Church"


def test_missing_document_evidence_preserves_followup_and_language():
    prompt = AgentOrchestrator().build_document_prompt(
        "What are the exceptions?",
        {"context_summary": "Discussing the policy."},
        "",
    )

    assert DOCUMENT_CHAT_INSTRUCTIONS in prompt.prompt_text
    assert prompt.system_instruction == DOCUMENT_CHAT_INSTRUCTIONS
    assert "No document excerpts are available." in prompt.prompt_text
    assert "Discussing the policy." in prompt.prompt_text
    assert "Respond in the user's language." in prompt.prompt_text
    assert prompt.purpose == "generate_text"
