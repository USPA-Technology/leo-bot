import asyncio
import json
import os
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4
import asyncpg
import numpy as np
import pytest

from leoai import rag_context_manager
from leoai.ai_core import AIClient
from leoai.db_utils import DATABASE_URL
from leoai.rag_agent import RAGAgent
from leoai.rag_context_manager import ContextManager
from leoai.rag_prompt_builder import AgentOrchestrator, PLACE_FOLLOWUP_INSTRUCTIONS
from leoai.rag_db_manager import ChatDBManager


PLACES = [
    {"id": 1, "name": "Binh Tay Market", "distance_meters": 736.8},
    {"id": 2, "name": "Cho Lon Chinatown", "distance_meters": 1309.9},
    {"id": 3, "name": "Ong Bon Pagoda", "distance_meters": 1350.5},
    {
        "id": 4, "name": "Cha Tam Church", "distance_meters": 1385,
        "address": "25 Hoc Lac, District 5, Ho Chi Minh City",
        "description": "Historic Chinese Catholic church in the Cho Lon neighborhood.",
        "category": "church",
    },
    {"id": 5, "name": "Binh Thai Church", "distance_meters": 1436},
]


def test_summary_refresh_preserves_explicit_place_selection():
    async def scenario():
        stored = {
            "updated_at": datetime.now(timezone.utc) - timedelta(seconds=30),
            "user_profile": {},
            "user_context": {
                "selected_place": deepcopy(PLACES[3]),
                "place_choices": deepcopy(PLACES),
            },
        }
        db = SimpleNamespace(
            get_touchpoint_context=AsyncMock(return_value={"nearby_places": PLACES}),
            save_context_summary=AsyncMock(return_value=True),
        )
        manager = ContextManager(None, None, db)
        manager.get_context_summary = Mock(return_value=stored)
        manager._retrieve_semantic_context = AsyncMock(return_value="user: history")
        manager._summarize_context = AsyncMock(return_value={
            "user_profile": {},
            "user_context": {"location": "Cho Lon"},
            "context_summary": "The user wants historical information.",
        })

        result = await manager.build_context_summary("visitor", "tp", None, "history")
        assert result["user_context"]["selected_place"] == PLACES[3]
        assert result["user_context"]["place_choices"] == PLACES
        persisted = db.save_context_summary.call_args.args[3]
        assert persisted["user_context"]["selected_place"] == PLACES[3]
        assert "updated_at" not in persisted

    asyncio.run(scenario())


def test_prompt_explicitly_resolves_history_to_selected_place():
    prompt = AgentOrchestrator().build_prompt(
        "history", {"user_context": {"selected_place": PLACES[3], "nearby_places": PLACES}},
        "Vietnamese",
    )
    assert "### Selected Place (active conversation subject)" in prompt.prompt_text
    assert "Cha Tam Church" in prompt.prompt_text
    assert "history" in prompt.prompt_text
    assert "Do not ask which place" in prompt.prompt_text


def make_memory_conversation():
    state = {}
    messages = []

    async def save_context(user, touchpoint, profile, context, **kwargs):
        state[(user, touchpoint)] = deepcopy(context)
        state[(user, touchpoint)]["updated_at"] = datetime.now(timezone.utc)
        return True

    def load_context(user, touchpoint, tenant_id="default"):
        return deepcopy(state.get((user, touchpoint)))

    async def save_message(user_id, role, message, *args, **kwargs):
        messages.append(f"{role}: {message}")

    class FakeClient:
        def generate_content(self, prompt, temperature=0.6):
            if "You are a data extractor" in prompt:
                return '```json\n{"user_profile": {}, "user_context": {}, "context_summary": "History requested."}\n```'
            return "Lịch sử Nhà thờ Cha Tam: thông tin theo địa điểm đã chọn."

    db = SimpleNamespace(
        save_context_summary=AsyncMock(side_effect=save_context),
        save_chat_message=AsyncMock(side_effect=save_message),
        get_touchpoint_context=AsyncMock(return_value={"nearby_places": deepcopy(PLACES)}),
    )
    context = ContextManager(None, FakeClient(), db)
    context.get_context_summary = Mock(side_effect=load_context)
    context._retrieve_semantic_context = AsyncMock(
        side_effect=lambda *args, **kwargs: "\n".join(messages)
    )
    agent = RAGAgent.__new__(RAGAgent)
    agent.db = db
    agent.context = context
    agent.agent_orchestrator = AgentOrchestrator()
    agent._safe_generate = AsyncMock(return_value="Lịch sử Cha Tam Church.")
    return agent, state, db


def test_hi_four_delayed_history_keeps_the_exact_displayed_place():
    async def scenario():
        agent, state, db = make_memory_conversation()
        greeting = await agent.process_chat_message(
            "visitor", "hi", touchpoint_id="tp", answer_in_format="html"
        )
        assert "<ol>" not in greeting
        assert greeting.count("\n") == 6
        assert state[("visitor", "tp")]["user_context"]["place_choices"][3]["name"] == "Cha Tam Church"
        # Reordering fresh geo results must not change what the displayed "4" means.
        db.get_touchpoint_context.return_value = {"nearby_places": list(reversed(PLACES))}
        confirmation = await agent.process_chat_message(
            "visitor", "4", touchpoint_id="tp", answer_in_format="html"
        )
        assert "Cha Tam Church" in confirmation
        assert state[("visitor", "tp")]["user_context"]["selected_place"]["id"] == 4
        state[("visitor", "tp")]["updated_at"] -= timedelta(seconds=30)
        answer = await agent.process_chat_message(
            "visitor", "history", touchpoint_id="tp", answer_in_format="html"
        )
        assert "Cha Tam Church" in answer
        prompt = agent._safe_generate.call_args.args[0]
        assert json.loads(
            prompt.prompt_text.split("### Selected Place (active conversation subject)\n")[1]
            .split("\n\n---")[0]
        )["name"] == "Cha Tam Church"
        assert "Do not ask which place" in prompt.system_instruction
        assert state[("visitor", "tp")]["user_context"]["selected_place"]["id"] == 4

    asyncio.run(scenario())


def test_selected_place_knowledge_is_added_to_answer_context():
    async def scenario():
        agent, _, _ = make_memory_conversation()
        agent.knowledge = SimpleNamespace(
            retrieve_selected_place=AsyncMock(
                return_value="Source: Place Guide\nVerified place history."
            )
        )
        await agent.process_chat_message("visitor", "hi", touchpoint_id="tp")
        await agent.process_chat_message("visitor", "4", touchpoint_id="tp")
        await agent.process_chat_message(
            "visitor", "history", touchpoint_id="tp"
        )

        agent.knowledge.retrieve_selected_place.assert_awaited_once_with(
            PLACES[3], "history", tenant_id="default", limit=3
        )
        prompt = agent._safe_generate.call_args.args[0].prompt_text
        assert "### Selected Place Knowledge" in prompt
        assert "Verified place history." in prompt

    asyncio.run(scenario())


def test_user_can_explicitly_change_selected_place():
    async def scenario():
        agent, state, _ = make_memory_conversation()
        await agent.process_chat_message("visitor", "hi", touchpoint_id="tp")
        await agent.process_chat_message("visitor", "4", touchpoint_id="tp")
        answer = await agent.process_chat_message("visitor", "1", touchpoint_id="tp")
        assert "Binh Tay Market" in answer
        assert state[("visitor", "tp")]["user_context"]["selected_place"]["id"] == 1

    asyncio.run(scenario())


def test_failed_selection_save_is_not_confirmed():
    async def scenario():
        agent, _, db = make_memory_conversation()
        await agent.process_chat_message("visitor", "hi", touchpoint_id="tp")
        # Context reload succeeds, but the subsequent selection save fails.
        original_save = db.save_context_summary.side_effect
        saves = 0

        async def fail_selection(*args, **kwargs):
            nonlocal saves
            saves += 1
            return (
                await original_save(*args, **kwargs)
                if saves == 1
                else False
            )

        db.save_context_summary.side_effect = fail_selection
        answer = await agent.process_chat_message("visitor", "4", touchpoint_id="tp")
        assert "Bạn đã chọn" not in answer
        assert "Failed to save the selected place" in answer

    asyncio.run(scenario())


def test_malformed_summary_does_not_erase_saved_selection():
    async def scenario():
        agent, state, _ = make_memory_conversation()
        await agent.process_chat_message("visitor", "hi", touchpoint_id="tp")
        await agent.process_chat_message("visitor", "4", touchpoint_id="tp")
        state[("visitor", "tp")]["updated_at"] -= timedelta(seconds=30)
        agent.context.client = SimpleNamespace(generate_content=lambda prompt: "not JSON")
        await agent.process_chat_message("visitor", "history", touchpoint_id="tp")
        assert state[("visitor", "tp")]["user_context"]["selected_place"]["id"] == 4

    asyncio.run(scenario())


def test_ai_summary_cannot_invent_a_selected_place():
    async def scenario():
        agent, state, _ = make_memory_conversation()
        agent.context._summarize_context = AsyncMock(return_value={
            "user_profile": {},
            "user_context": {"selected_place": PLACES[0], "place_choices": []},
        })
        await agent.process_chat_message("visitor", "hi", touchpoint_id="tp")
        assert "selected_place" not in state[("visitor", "tp")]["user_context"]
        assert len(state[("visitor", "tp")]["user_context"]["place_choices"]) == 5

    asyncio.run(scenario())


def test_other_touchpoints_do_not_inherit_the_selection():
    async def scenario():
        agent, state, _ = make_memory_conversation()
        await agent.process_chat_message("visitor", "hi", touchpoint_id="tp")
        await agent.process_chat_message("visitor", "4", touchpoint_id="tp")
        await agent.process_chat_message("visitor", "hi", touchpoint_id="other")
        assert "selected_place" not in state[("visitor", "other")]["user_context"]

    asyncio.run(scenario())


def test_recent_and_semantic_history_are_touchpoint_scoped_and_chronological(monkeypatch):
    async def scenario():
        from contextlib import asynccontextmanager

        now = datetime.now(timezone.utc)
        recent = [
            {"message_hash": "3", "role": "user", "message": "history", "created_at": now},
            {"message_hash": "2", "role": "bot", "message": "Selected Cha Tam Church", "created_at": now - timedelta(seconds=1)},
        ]
        semantic = [
            {"message_hash": "2", "role": "bot", "message": "Selected Cha Tam Church", "created_at": now - timedelta(seconds=1)},
            {"message_hash": "1", "role": "user", "message": "4", "created_at": now - timedelta(seconds=2)},
        ]
        conn = SimpleNamespace(fetch=AsyncMock(side_effect=[recent, semantic]))

        @asynccontextmanager
        async def connect():
            yield conn

        monkeypatch.setattr(rag_context_manager, "get_async_pg_conn", connect)
        model = SimpleNamespace(encode=lambda *args, **kwargs: np.ones(768))
        manager = ContextManager(model, None, None)
        history = await manager._retrieve_semantic_context("visitor", "history", "tp")
        assert history.splitlines() == [
            "user: 4", "bot: Selected Cha Tam Church", "user: history",
        ]
        for call in conn.fetch.call_args_list:
            assert call.args[1:4] == ("default", "visitor", "tp")
            assert "tenant_id = $1" in call.args[0]
            assert "user_id = $2" in call.args[0]
            assert "touchpoint_id = $3" in call.args[0]

    asyncio.run(scenario())


@pytest.mark.parametrize("topic", ["history", "lịch sử", "opening hours", "directions", "it"])
def test_short_followup_prompt_prioritizes_active_place(topic):
    prompt = AgentOrchestrator().build_prompt(
        topic, {"user_context": {"selected_place": PLACES[3], "nearby_places": PLACES}},
        "Vietnamese",
    )
    assert "### Selected Place (active conversation subject)" in prompt.prompt_text
    assert topic in prompt.prompt_text
    assert PLACE_FOLLOWUP_INSTRUCTIONS in prompt.system_instruction
    assert "('You are LEO" not in prompt.prompt_text


def test_endpoint_selection_then_history_flow(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from leobot_router import leobot_main_router as routes

    agent, state, _ = make_memory_conversation()
    monkeypatch.setattr(routes, "rag_agent", agent)
    monkeypatch.setattr(routes, "REDIS_CLIENT", SimpleNamespace(
        hget=lambda user, field: "tp" if field == "touchpoint_id" else None
    ))
    monkeypatch.setattr(routes, "is_safe_to_answer", lambda user: True)
    app = FastAPI()
    app.include_router(routes.router)
    client = TestClient(app)
    for question in ["hi", "4"]:
        response = client.post("/_leoai/ask", json={
            "visitor_id": "visitor", "question": question, "answer_in_language": "Vietnamese",
        })
        assert response.status_code == 200
        assert response.json()["error_code"] == 0
    state[("visitor", "tp")]["updated_at"] -= timedelta(seconds=30)
    response = client.post("/_leoai/ask", json={
        "visitor_id": "visitor", "question": "history", "answer_in_language": "Vietnamese",
    })
    assert "Cha Tam Church" in response.json()["answer"]
    assert agent._safe_generate.call_args.args[0].system_instruction


def test_rag_generation_passes_continuity_rules_as_system_instruction():
    async def scenario():
        models = SimpleNamespace(generate_content=Mock(
            return_value=SimpleNamespace(text="History of Cha Tam Church")
        ))
        client = AIClient.__new__(AIClient)
        client.provider = "google"
        client.model_name = "fake"
        client.client = SimpleNamespace(models=models)
        agent = RAGAgent.__new__(RAGAgent)
        agent.client = client
        prompt = AgentOrchestrator().build_prompt(
            "history", {"user_context": {"selected_place": PLACES[3]}}, "English"
        )
        assert await agent._safe_generate(prompt, 0.3) == "History of Cha Tam Church"
        request = models.generate_content.call_args.kwargs
        assert request["config"].system_instruction == prompt.system_instruction
        assert "Cha Tam Church" in request["contents"]

    asyncio.run(scenario())


@pytest.mark.skipif(
    os.getenv("RUN_CONVERSATION_DB_TESTS") != "1",
    reason="Enable for rollback-only PostgreSQL context persistence validation.",
)
def test_postgres_selection_survives_summary_refresh(monkeypatch):
    async def scenario():
        from contextlib import asynccontextmanager

        conn = await asyncpg.connect(DATABASE_URL)
        tx = conn.transaction()
        await tx.start()
        try:
            schema = f"conversation_test_{uuid4().hex}"
            await conn.execute(f'CREATE SCHEMA "{schema}"')
            await conn.execute(f'SET LOCAL search_path TO "{schema}", public')
            await conn.execute(
                "CREATE TABLE conversational_context "
                "(LIKE public.conversational_context INCLUDING ALL)"
            )

            @asynccontextmanager
            async def connect():
                yield conn

            from leoai import rag_db_manager
            monkeypatch.setattr(rag_db_manager, "get_async_pg_conn", connect)
            db = ChatDBManager(SimpleNamespace(encode=lambda *args, **kwargs: np.ones(768)))
            original = {
                "user_profile": {},
                "user_context": {"selected_place": PLACES[3], "place_choices": PLACES},
            }
            assert await db.save_context_summary("visitor", "tp", None, original)
            await conn.execute(
                "UPDATE conversational_context SET updated_at=now()-interval '30 seconds'"
            )
            stored = await conn.fetchrow(
                "SELECT context_data, updated_at FROM conversational_context "
                "WHERE user_id='visitor' AND touchpoint_id='tp'"
            )
            loaded = json.loads(stored["context_data"])
            loaded["updated_at"] = stored["updated_at"]
            db.get_touchpoint_context = AsyncMock(return_value={"nearby_places": PLACES})
            manager = ContextManager(None, None, db)
            manager.get_context_summary = Mock(return_value=loaded)
            manager._retrieve_semantic_context = AsyncMock(return_value="user: history")
            manager._summarize_context = AsyncMock(return_value={
                "user_profile": {}, "user_context": {},
                "context_summary": "The user asked for history.",
            })
            result = await manager.build_context_summary("visitor", "tp", None, "history")
            assert result["user_context"]["selected_place"]["name"] == "Cha Tam Church"
            saved = json.loads(await conn.fetchval(
                "SELECT context_data FROM conversational_context "
                "WHERE user_id='visitor' AND touchpoint_id='tp'"
            ))
            assert saved["user_context"]["selected_place"]["id"] == 4
            assert saved["user_context"]["place_choices"] == PLACES
            assert await conn.fetchval(
                "SELECT vector_dims(embedding) FROM conversational_context"
            ) == 768
        finally:
            await tx.rollback()
            await conn.close()

    asyncio.run(scenario())
