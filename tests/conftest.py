import sys
import os

import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock

# add repo root to python import path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@pytest.fixture(autouse=True)
def stub_application_intent_detection(monkeypatch):
    """Keep route tests offline while unit tests cover AIClient separately."""
    from leoai.ai_intent_detection import IntentDetectionResult, IntentType
    from leobot_router import leobot_main_router
    from leoai import rag_agent

    class StubIntentDetector:
        async def detect_async(self, message, context=None):
            if (
                context
                and context.context == "agent"
                and context.persona_id == "personal_assistant"
            ):
                primary_intent = IntentType.DOCUMENT_CHAT
            elif any(
                cue in message.casefold()
                for cue in (
                    "near me",
                    "nearby",
                    "gần tôi",
                    "gần toi",
                    "gần đây",
                    "gan day",
                )
            ):
                primary_intent = IntentType.LOCATION_CHAT
            else:
                primary_intent = IntentType.GENERAL_CHAT
            return IntentDetectionResult(
                primary_intent=primary_intent,
                purpose="generate_text",
                confidence=1.0,
            )

    detector = StubIntentDetector()
    monkeypatch.setattr(leobot_main_router, "intent_detector", detector)
    monkeypatch.setattr(rag_agent, "intent_detector", detector)


@pytest.fixture(autouse=True)
def disable_external_chat_cache(monkeypatch):
    from leobot_router import leobot_main_router, leobot_knowledge_router

    cache = SimpleNamespace(
        lookup=AsyncMock(return_value=(None, None)),
        store=AsyncMock(),
        invalidate_visitor=AsyncMock(),
        invalidate_places=AsyncMock(),
    )
    monkeypatch.setattr(leobot_main_router, "chat_response_cache", cache)
    monkeypatch.setattr(leobot_knowledge_router, "chat_response_cache", cache)
