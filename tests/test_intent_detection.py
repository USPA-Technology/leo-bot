import logging

import pytest

from leoai.ai_intent_detection import (
    IntentDetector,
    IntentType,
    PurposeType,
    RequestContext,
)


class FakeAIClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def generate_json(self, prompt, json_schema, *, system_instruction=None):
        self.calls.append((prompt, json_schema, system_instruction))
        return self.response


def intent_response(
    primary_intent,
    *,
    purpose="generate_text",
    confidence=0.95,
    secondary=None,
    entities=None,
):
    return {
        "primary_intent": primary_intent,
        "purpose": purpose,
        "secondary_intents": secondary or [],
        "confidence": confidence,
        "entities": entities or {},
        "needs_clarification": False,
    }


def test_detector_uses_question_and_request_context_in_structured_prompt():
    client = FakeAIClient(intent_response("document_chat"))
    detector = IntentDetector(ai_client=client)
    context = RequestContext(
        channel="facebook_messenger",
        visitor_id="visitor",
        context="agent",
        persona_id="personal_assistant",
    )

    result = detector.detect("What does the guide say?", context)

    assert result.primary_intent is IntentType.DOCUMENT_CHAT
    assert result.purpose is PurposeType.GENERATE_TEXT
    prompt, schema, system_instruction = client.calls[0]
    assert "What does the guide say?" in prompt
    assert '"channel": "facebook_messenger"' in prompt
    assert "visitor" not in prompt
    assert "tenant_id" not in prompt
    assert "touchpoint_id" not in prompt
    assert schema["properties"]["primary_intent"]["enum"]
    assert {
        "place_type",
        "search_terms",
        "search_name",
        "date_range",
        "customer_id",
        "campaign_id",
        "operation",
        "result_limit",
        "radius_meters",
    } <= schema["properties"]["entities"]["properties"].keys()
    assert schema["properties"]["entities"]["properties"]["search_terms"] == {
        "type": "array",
        "items": {"type": "string"},
        "maxItems": 6,
    }
    assert "the channel a message arrived on is not an intent" in system_instruction


def test_location_intent_extracts_result_limit_and_radius_in_meters():
    client = FakeAIClient(intent_response(
        "location_chat",
        entities={
            "place_type": "coffee",
            "search_terms": ["coffee"],
            "search_name": "coffee",
            "result_limit": 5,
            "radius_meters": 1500,
        },
    ))

    result = IntentDetector(ai_client=client).detect(
        "Find 5 coffee shops within 1.5 km",
    )

    assert result.entities["result_limit"] == 5
    assert result.entities["radius_meters"] == 1500.0
    assert "Convert kilometers or kilometres to meters" in client.calls[0][2]


@pytest.mark.parametrize("entity,value", [
    ("result_limit", 0),
    ("result_limit", 2.5),
    ("result_limit", True),
    ("radius_meters", float("inf")),
    ("radius_meters", True),
])
def test_location_intent_rejects_invalid_result_limit_or_radius(entity, value):
    client = FakeAIClient(intent_response(
        "location_chat",
        entities={
            "place_type": "coffee",
            "search_terms": ["coffee"],
            "search_name": "coffee",
            entity: value,
        },
    ))

    result = IntentDetector(ai_client=client).detect("Find coffee nearby")

    assert result.primary_intent is IntentType.GENERAL_CHAT
    assert result.needs_clarification is True


@pytest.mark.parametrize("radius", [0, -100])
def test_location_intent_preserves_nonpositive_radius_for_request_validation(radius):
    client = FakeAIClient(intent_response(
        "location_chat",
        entities={
            "place_type": "coffee",
            "search_terms": ["coffee"],
            "search_name": "coffee",
            "radius_meters": radius,
        },
    ))

    result = IntentDetector(ai_client=client).detect("Find coffee nearby")

    assert result.primary_intent is IntentType.LOCATION_CHAT
    assert result.entities["radius_meters"] == float(radius)


def test_location_intent_is_separate_from_facebook_channel():
    client = FakeAIClient(intent_response(
        "location_chat",
        entities={
            "place_type": "church",
            "search_terms": ["church"],
            "search_name": "church",
        },
    ))
    result = IntentDetector(ai_client=client).detect(
        "Find a church near me",
        RequestContext(channel="facebook_messenger"),
    )

    assert result.primary_intent is IntentType.LOCATION_CHAT
    assert result.entities["place_type"] == "church"


def test_location_result_without_search_entities_falls_back_to_clarification():
    client = FakeAIClient(intent_response("location_chat"))

    result = IntentDetector(ai_client=client).detect("Find a place nearby")

    assert result.primary_intent is IntentType.GENERAL_CHAT
    assert result.needs_clarification is True


def test_ambiguous_multi_intent_request_requires_clarification():
    client = FakeAIClient(intent_response(
        "general_chat",
        purpose="generate_answer",
        confidence=0.35,
        secondary=["data_analytics_chat", "facebook_page_chat"],
    ))

    result = IntentDetector(ai_client=client).detect(
        "Show KPI dashboard and Facebook Page engagement"
    )

    assert result.primary_intent is IntentType.GENERAL_CHAT
    assert result.purpose is PurposeType.GENERATE_ANSWER
    assert set(result.secondary_intents) == {
        IntentType.DATA_ANALYTICS_CHAT,
        IntentType.FACEBOOK_PAGE_CHAT,
    }
    assert result.needs_clarification is True


def test_low_confidence_result_is_marked_for_clarification():
    client = FakeAIClient(intent_response("general_chat", confidence=0.5))

    result = IntentDetector(ai_client=client).detect("Maybe something about data")

    assert result.confidence == 0.5
    assert result.needs_clarification is True


def test_invalid_ai_result_falls_back_to_safe_clarification():
    client = FakeAIClient({"primary_intent": "not_a_supported_intent"})

    result = IntentDetector(ai_client=client).detect("Do something")

    assert result.primary_intent is IntentType.GENERAL_CHAT
    assert result.confidence == 0.0
    assert result.needs_clarification is True


def test_detector_logs_raw_and_validated_intent_json(caplog):
    client = FakeAIClient(intent_response("general_chat"))
    detector = IntentDetector(ai_client=client)
    caplog.set_level(logging.DEBUG, logger="leoai.ai_intent_detection")

    detector.detect("Find a place")

    assert "Intent detection raw JSON" in caplog.text
    assert "Intent detection validated result" in caplog.text
