import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4
from uuid6 import uuid7

import asyncpg
import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from leoai import rag_knowledge_manager
from leoai.db_utils import DATABASE_URL, to_pgvector
from leoai.rag_agent import DOCUMENT_CHAT_TOUCHPOINT_ID, RAGAgent, is_document_chat
from leoai.rag_context_manager import ContextManager
from leoai.rag_knowledge_manager import KnowledgeRetriever
from leoai.rag_prompt_builder import AgentOrchestrator, DOCUMENT_CHAT_INSTRUCTIONS


def make_document_agent():
    agent = RAGAgent.__new__(RAGAgent)
    agent.db = SimpleNamespace(
        save_chat_message=AsyncMock(),
        save_context_summary=AsyncMock(return_value=True),
        find_nearby_places=AsyncMock(),
        get_touchpoint_context=AsyncMock(),
    )
    agent.context = SimpleNamespace(build_context_summary=AsyncMock(return_value={
        "user_context": {}, "context_summary": "Document discussion",
    }))
    agent.knowledge = SimpleNamespace(retrieve=AsyncMock(
        return_value="Source: Guide\nThis guide explains history."
    ))
    agent.agent_orchestrator = AgentOrchestrator()
    agent.create_geolocation_touchpoint = AsyncMock()
    agent._safe_generate = AsyncMock(return_value="Hi! Ask me about your documents.")
    return agent


@pytest.mark.parametrize("context,persona,expected", [
    ("agent", "personal_assistant", True),
    (" agent ", "personal_assistant", True),
    ("chatbot", "personal_assistant", False),
    ("agent", "web_user", False),
])
def test_document_mode_requires_both_fields(context, persona, expected):
    assert is_document_chat(context, persona) is expected


@pytest.fixture
def api_client(monkeypatch):
    from leobot_router import leobot_main_router as routes

    agent = make_document_agent()
    redis = SimpleNamespace(hget=Mock(side_effect=lambda visitor, field:
        "geo-tp" if field == "touchpoint_id" else None
    ))
    monkeypatch.setattr(routes, "rag_agent", agent)
    monkeypatch.setattr(routes, "REDIS_CLIENT", redis)
    monkeypatch.setattr(routes, "is_safe_to_answer", lambda visitor: True)
    app = FastAPI()
    app.include_router(routes.router)
    return TestClient(app), agent, redis


def test_exact_document_agent_payload_never_uses_cached_geolocation(api_client):
    client, agent, redis = api_client
    response = client.post("/_leoai/ask", json={
        "answer_in_format": "html",
        "context": "agent",
        "persona_id": "personal_assistant",
        "prompt": "hi ",
        "question": "hi ",
        "temperature_score": 0.8,
        "visitor_id": "7e7c56b6b2a74869a1b79659711f44d5",
    })
    assert response.status_code == 200
    result = response.json()
    assert result["error_code"] == 0
    assert result["answer"] == "Hi! Ask me about your documents."
    assert result["touchpoint_id"] == DOCUMENT_CHAT_TOUCHPOINT_ID
    assert all(call.args[1] != "touchpoint_id" for call in redis.hget.call_args_list)
    agent.create_geolocation_touchpoint.assert_not_awaited()
    agent.db.find_nearby_places.assert_not_awaited()
    agent.knowledge.retrieve.assert_not_awaited()
    assert agent._safe_generate.call_args.args[1] == 0.8
    prompt = agent._safe_generate.call_args.args[0]
    assert prompt.system_instruction == DOCUMENT_CHAT_INSTRUCTIONS
    assert "### Selected Place" not in prompt.prompt_text
    agent.context.build_context_summary.assert_awaited_once_with(
        "7e7c56b6b2a74869a1b79659711f44d5", DOCUMENT_CHAT_TOUCHPOINT_ID, None, "hi ",
        include_location=False, tenant_id="default",
    )


@pytest.mark.parametrize("question", ["4", "history", "top 0 churches near me"])
def test_document_questions_use_document_retrieval_not_place_selection(api_client, question):
    client, agent, _ = api_client
    agent.context.build_context_summary.return_value["user_context"] = {
        "selected_place": {"name": "Cha Tam Church"},
        "nearby_places": [{"name": "Binh Tay Market"}],
        "latitude": 10.747904,
    }
    response = client.post("/_leoai/ask", json={
        "visitor_id": "visitor", "question": question,
        "context": "agent", "persona_id": "personal_assistant",
        "touchpoint_id": "geo-tp", "latitude": 10.747904,
    })
    assert response.status_code == 200
    agent.knowledge.retrieve.assert_awaited_once_with(
        question, "default", user_id="visitor",
    )
    agent.db.find_nearby_places.assert_not_awaited()
    agent.create_geolocation_touchpoint.assert_not_awaited()
    prompt = agent._safe_generate.call_args.args[0]
    assert "Source: Guide" in prompt.prompt_text
    assert "Cha Tam Church" not in prompt.prompt_text
    assert "Binh Tay Market" not in prompt.prompt_text
    assert all(
        call.args[5] == DOCUMENT_CHAT_TOUCHPOINT_ID
        for call in agent.db.save_chat_message.call_args_list
    )


def test_missing_document_excerpts_prompt_requests_documents_not_location():
    prompt = AgentOrchestrator().build_document_prompt("hi", {}, "", "Vietnamese")
    assert "No document excerpts are available." in prompt.prompt_text
    assert "invite a question about their documents" in prompt.system_instruction
    assert prompt.purpose == "generate_text"
    assert "PLACE_FOLLOWUP" not in prompt.system_instruction


def test_document_summary_never_reads_or_preserves_location_state():
    async def scenario():
        db = SimpleNamespace(
            get_touchpoint_context=AsyncMock(),
            save_context_summary=AsyncMock(return_value=True),
        )
        manager = ContextManager(None, None, db)
        manager.get_context_summary = Mock(return_value={
            "updated_at": datetime.now(timezone.utc),
            "user_context": {
                "selected_place": {"name": "Cha Tam Church"},
                "place_choices": [{"name": "Binh Tay Market"}],
                "latitude": 10,
                "longitude": 106,
                "nearby_places": [],
                "datetime": "2026-10-06 17:36",
            },
        })
        result = await manager.build_context_summary(
            "visitor", DOCUMENT_CHAT_TOUCHPOINT_ID, None, "hi", include_location=False
        )
        assert result["user_context"] == {"datetime": "2026-10-06 17:36"}
        db.get_touchpoint_context.assert_not_awaited()
        persisted = db.save_context_summary.call_args.args[3]
        assert "selected_place" not in persisted["user_context"]

    asyncio.run(scenario())


def test_document_retriever_uses_asyncpg_and_scopes_active_sources_to_visitor(monkeypatch):
    async def scenario():
        conn = SimpleNamespace(fetch=AsyncMock(return_value=[{
            "content": "Verified document excerpt.",
            "source_name": "User Guide", "uri": "https://example.com/guide",
        }]))

        @asynccontextmanager
        async def connect():
            yield conn

        monkeypatch.setattr(rag_knowledge_manager, "get_async_pg_conn", connect)
        model = SimpleNamespace(encode=lambda *args, **kwargs: np.ones(768))
        result = await KnowledgeRetriever(model).retrieve("history", "default", user_id="visitor")
        assert "Source: User Guide" in result
        assert "Verified document excerpt." in result
        assert "https://example.com/guide" in result
        sql, tenant, user, vector, limit = conn.fetch.call_args.args
        assert tenant == "default" and user == "visitor"
        assert "ks.user_id = $2" in sql and "ks.status = 'active'" in sql
        assert "LIMIT $4" in sql
        assert vector.startswith("[") and limit == 5
        conn.fetch.return_value = []
        assert await KnowledgeRetriever(model).retrieve(
            "history", "default", user_id="visitor"
        ) == ""

    asyncio.run(scenario())


def test_selected_place_retriever_uses_place_metadata_and_returns_three_results(monkeypatch):
    async def scenario():
        conn = SimpleNamespace(fetch=AsyncMock(return_value=[
            {
                "content": "Verified place excerpt.",
                "source_name": "Place Guide",
                "uri": "https://example.com/place",
            },
        ]))

        @asynccontextmanager
        async def connect():
            yield conn

        monkeypatch.setattr(rag_knowledge_manager, "get_async_pg_conn", connect)
        encoded_queries = []

        def encode(text, **kwargs):
            encoded_queries.append(text)
            return np.ones(768)

        model = SimpleNamespace(encode=encode)
        result = await KnowledgeRetriever(model).retrieve_selected_place(
            {"id": "place-1", "name": "Cha Tam Church"},
            "history",
        )
        assert "Source: Place Guide" in result
        assert "Verified place excerpt." in result
        sql, tenant, place_id, query, vector, limit = conn.fetch.call_args.args
        assert tenant == "default"
        assert place_id == "place-1"
        assert "Cha Tam Church" in query
        assert "history" in encoded_queries[0]
        assert "ks.metadata->>'geo_place_id'" in sql
        assert "plainto_tsquery" in sql
        assert vector.startswith("[") and limit == 3

    asyncio.run(scenario())


@pytest.mark.skipif(
    os.getenv("RUN_DOCUMENT_DB_TESTS") != "1",
    reason="Enable for rollback-only PostgreSQL document retrieval validation.",
)
def test_postgres_document_retrieval_excludes_other_users_tenants_and_inactive_sources(monkeypatch):
    async def scenario():
        conn = await asyncpg.connect(DATABASE_URL)
        tx = conn.transaction()
        await tx.start()
        try:
            schema = f"document_test_{uuid4().hex}"
            await conn.execute(f'CREATE SCHEMA "{schema}"')
            await conn.execute(f'SET LOCAL search_path TO "{schema}", public')
            await conn.execute("""
                CREATE TABLE knowledge_sources (
                    id uuid PRIMARY KEY, user_id text, tenant_id text, status text,
                    name text, uri text
                );
                CREATE TABLE knowledge_chunks (
                    source_id uuid REFERENCES knowledge_sources(id), content text,
                    embedding vector(768)
                );
            """)
            vector = to_pgvector([1.0] + [0.0] * 767)
            for user, tenant, status, content in [
                ("visitor", "default", "active", "Own document answer."),
                ("other", "default", "active", "Other user document."),
                ("visitor", "other", "active", "Other tenant document."),
                ("visitor", "default", "pending", "Unprocessed document."),
            ]:
                source_id = uuid7()
                await conn.execute(
                    "INSERT INTO knowledge_sources VALUES ($1,$2,$3,$4,$5,$6)",
                    source_id, user, tenant, status, "Test guide", "https://example.com/guide",
                )
                await conn.execute(
                    "INSERT INTO knowledge_chunks VALUES ($1,$2,$3::vector)",
                    source_id, content, vector,
                )

            @asynccontextmanager
            async def connect():
                yield conn

            monkeypatch.setattr(rag_knowledge_manager, "get_async_pg_conn", connect)
            model = SimpleNamespace(encode=lambda *args, **kwargs: np.array([1.0] + [0.0] * 767))
            answer = await KnowledgeRetriever(model).retrieve(
                "document question", "default", user_id="visitor"
            )
            assert "Own document answer." in answer
            assert "Other user document." not in answer
            assert "Other tenant document." not in answer
            assert "Unprocessed document." not in answer
            assert "Source: Test guide" in answer
        finally:
            await tx.rollback()
            await conn.close()

    asyncio.run(scenario())
