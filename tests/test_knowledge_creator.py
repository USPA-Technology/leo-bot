import asyncio
import json
import os
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4
from uuid6 import uuid7

import asyncpg
import httpx
import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from leoai import rag_knowledge_manager as knowledge
from leoai.ai_knowledge_models import KnowledgeSourceType
from leoai.db_utils import DATABASE_URL
from leoai.rag_knowledge_manager import (
    KnowledgeCreator, KnowledgeFetchError, KnowledgeInputError,
    KnowledgeRetriever, KnowledgeUpdateResult, PublicWebPageFetcher, WebDocument,
    _WebPageParser,
)
import main_config


URL = "https://www.bigdatavietnam.org/2026/04/rag-vs-cag-giai-quyet-iem-mu-cua-ai-voi.html"
ENRICHMENT_KEY = "test-data-enrichment-key"
ENRICHMENT_HEADERS = {"Authorization": f"Bearer {ENRICHMENT_KEY}"}


class FakeEmbeddingModel:
    dimensions = 768
    provider = "fake"
    model_name = "fake-embedding"

    def encode(self, sentences, **kwargs) -> np.ndarray:
        single = isinstance(sentences, str)
        vectors = np.zeros((1 if single else len(sentences), self.dimensions), dtype=np.float32)
        vectors[:, 0] = 1
        return vectors[0] if single else vectors


def mock_database(monkeypatch):
    conn = SimpleNamespace(execute=AsyncMock(), executemany=AsyncMock())
    events = []

    @asynccontextmanager
    async def transaction():
        events.append("begin")
        try:
            yield
        except Exception:
            events.append("rollback")
            raise
        else:
            events.append("commit")

    conn.transaction = transaction

    @asynccontextmanager
    async def connect():
        yield conn

    monkeypatch.setattr(knowledge, "get_async_pg_conn", connect)
    return conn, events


def test_parser_uses_article_title_and_readable_text():
    parser = _WebPageParser()
    parser.feed("""
        <html><head><title>RAG &amp; CAG</title><style>hidden</style></head>
        <body><nav>Navigation</nav><article>
        <h1>RAG versus CAG</h1><p>First paragraph.</p><p>Second <b>paragraph</b>.</p>
        <script>ignoreMe()</script></article><footer>Footer</footer></body></html>
    """)
    document = parser.document(URL)
    assert document.title == "RAG & CAG"
    assert "RAG versus CAG\n\nFirst paragraph.\n\nSecond paragraph." == document.text
    assert "Navigation" not in document.text
    assert "ignoreMe" not in document.text


def test_parser_supports_blogger_post_body_and_plain_body_fallback():
    parser = _WebPageParser()
    parser.feed("<title>Title</title><div>sidebar</div><div class='post-body entry-content'><p>Article</p></div>")
    assert parser.document(URL).text == "Article"
    parser = _WebPageParser()
    parser.feed("<html><body><p>Fallback content</p></body></html>")
    assert parser.document(URL).text == "Fallback content"


@pytest.mark.parametrize("url", ["ftp://example.com/a", "https://user:password@example.com", "file:///etc/passwd"])
def test_fetcher_rejects_unsupported_and_credential_urls(url):
    with pytest.raises(KnowledgeInputError):
        PublicWebPageFetcher.normalize_url(url)


def test_url_identity_strips_fragment():
    assert str(PublicWebPageFetcher.normalize_url(URL + "#heading")) == URL


def test_invalid_visitor_and_unsupported_source_type_fail_before_fetch():
    async def scenario():
        fetcher = SimpleNamespace(fetch=AsyncMock())
        creator = KnowledgeCreator(FakeEmbeddingModel(), fetcher)
        for visitor in ["", " ", "x" * 51]:
            with pytest.raises(KnowledgeInputError):
                await creator.upsert_url(URL, visitor_id=visitor)
        with pytest.raises(KnowledgeInputError, match="web_page only"):
            await creator.upsert_url(
                URL, visitor_id="visitor", source_type=KnowledgeSourceType.UPLOADED_DOCUMENT
            )
        fetcher.fetch.assert_not_awaited()

    asyncio.run(scenario())


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1"])
def test_fetcher_rejects_local_addresses(monkeypatch, address):
    async def scenario():
        loop = asyncio.get_running_loop()
        monkeypatch.setattr(loop, "getaddrinfo", AsyncMock(return_value=[
            (2, 1, 6, "", (address, 443))
        ]))
        with pytest.raises(KnowledgeInputError, match="private or local"):
            await PublicWebPageFetcher()._public_address(httpx.URL("https://example.com"))

    asyncio.run(scenario())


def setup_http(monkeypatch, handler):
    real_client = httpx.AsyncClient
    factory_calls = []

    def client(**kwargs):
        factory_calls.append(kwargs)
        return real_client(**kwargs, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(knowledge.httpx, "AsyncClient", client)
    fetcher = PublicWebPageFetcher()
    resolver = AsyncMock(return_value="93.184.216.34")
    monkeypatch.setattr(fetcher, "_public_address", resolver)
    return fetcher, factory_calls, resolver


def test_http_fetcher_pins_address_and_validates_redirects(monkeypatch):
    async def scenario():
        requests = []

        def handler(request):
            requests.append(request)
            if request.url.path == "/start":
                return httpx.Response(302, headers={"location": "https://article.example/final"})
            return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"},
                                  text="<title>Title</title><article><p>Hello world.</p></article>")

        fetcher, options, resolver = setup_http(monkeypatch, handler)
        document = await fetcher.fetch("https://start.example/start")
        assert document.text == "Hello world."
        assert document.fetched_url == "https://article.example/final"
        assert len(resolver.call_args_list) == 2
        assert requests[0].url.host == "93.184.216.34"
        assert requests[0].headers["host"] == "start.example"
        assert requests[0].extensions["sni_hostname"] == "start.example"
        assert requests[1].headers["host"] == "article.example"
        assert options[0]["trust_env"] is False
        assert options[0]["follow_redirects"] is False

    asyncio.run(scenario())


def test_redirect_to_private_host_is_not_downloaded(monkeypatch):
    async def scenario():
        fetcher, _, resolver = setup_http(monkeypatch, lambda request:
            httpx.Response(302, headers={"location": "http://127.0.0.1/private"})
        )
        resolver.side_effect = [
            "93.184.216.34", KnowledgeInputError("private or local network")
        ]
        with pytest.raises(KnowledgeInputError):
            await fetcher.fetch("https://example.com")

    asyncio.run(scenario())


@pytest.mark.parametrize("status,content_type,expected", [
    (404, "text/html", KnowledgeFetchError),
    (200, "application/pdf", KnowledgeInputError),
])
def test_fetcher_reports_http_errors_and_unsupported_formats(monkeypatch, status, content_type, expected):
    async def scenario():
        fetcher, _, _ = setup_http(monkeypatch, lambda request:
            httpx.Response(status, headers={"content-type": content_type}, text="test")
        )
        with pytest.raises(expected):
            await fetcher.fetch(URL)

    asyncio.run(scenario())


def test_fetcher_limits_download_size(monkeypatch):
    async def scenario():
        fetcher, _, _ = setup_http(monkeypatch, lambda request:
            httpx.Response(200, headers={"content-type": "text/plain"}, text="too many bytes")
        )
        fetcher.MAX_BYTES = 3
        with pytest.raises(KnowledgeInputError, match="download limit"):
            await fetcher.fetch(URL)

    asyncio.run(scenario())


def test_fetcher_limits_redirect_count(monkeypatch):
    async def scenario():
        fetcher, _, _ = setup_http(monkeypatch, lambda request:
            httpx.Response(302, headers={"location": URL})
        )
        fetcher.MAX_REDIRECTS = 1
        with pytest.raises(KnowledgeFetchError, match="too many redirects"):
            await fetcher.fetch(URL)

    asyncio.run(scenario())


def test_creator_upserts_source_and_replaces_chunks_in_one_transaction(monkeypatch):
    async def scenario():
        conn, events = mock_database(monkeypatch)
        fetcher = SimpleNamespace(fetch=AsyncMock(return_value=WebDocument(
            "RAG and CAG", "first second third fourth fifth sixth", URL
        )))
        creator = KnowledgeCreator(FakeEmbeddingModel(), fetcher)
        first = await creator.upsert_url(URL, visitor_id="visitor")
        second = await creator.upsert_url(URL, visitor_id="visitor")
        assert first.source_id == second.source_id
        assert first.chunk_count == 1
        assert first.status == "active"
        assert first.embedding_dimensions == 768
        assert events == ["begin", "commit", "begin", "commit"]
        sql, source_id, visitor, tenant, source_type, name, uri, metadata = conn.execute.call_args_list[0].args
        assert "ON CONFLICT (id)" in sql
        assert visitor == "visitor" and tenant == "default"
        assert source_type == "web_page" and name == "RAG and CAG" and uri == URL
        assert json.loads(metadata)["embedding_model"] == "fake-embedding"
        assert "DELETE FROM knowledge_chunks" in conn.execute.call_args_list[1].args[0]
        rows = conn.executemany.call_args.args[1]
        assert rows[0][1] == source_id and rows[0][2] == "default" and rows[0][5] == 0
        assert len(json.loads(rows[0][4])) == 768
        other = await creator.upsert_url(URL, visitor_id="different")
        assert other.source_id != first.source_id

    asyncio.run(scenario())


def test_creator_chunks_long_text_using_existing_overlap(monkeypatch):
    async def scenario():
        conn, _ = mock_database(monkeypatch)
        result = await KnowledgeCreator(FakeEmbeddingModel()).upsert_text(
            "one two three four five six seven eight nine", uri=URL,
            visitor_id="visitor", name="Test", max_tokens=4, overlap_tokens=1,
        )
        rows = conn.executemany.call_args.args[1]
        assert result.chunk_count == 3
        assert [row[3] for row in rows] == [
            "one two three four", "four five six seven", "seven eight nine",
        ]
        assert [row[5] for row in rows] == [0, 1, 2]

    asyncio.run(scenario())


@pytest.mark.parametrize("text", [" ", "a" * 100001])
def test_invalid_text_fails_before_database_changes(monkeypatch, text):
    async def scenario():
        conn, events = mock_database(monkeypatch)
        with pytest.raises(KnowledgeInputError):
            await KnowledgeCreator(FakeEmbeddingModel()).upsert_text(
                text, uri=URL, visitor_id="visitor", name="Test"
            )
        assert events == []
        conn.execute.assert_not_awaited()

    asyncio.run(scenario())


def test_provider_failure_does_not_start_a_database_transaction(monkeypatch):
    async def scenario():
        conn, events = mock_database(monkeypatch)

        class FailingModel(FakeEmbeddingModel):
            def encode(self, sentences, **kwargs) -> np.ndarray:
                raise RuntimeError("provider unavailable")

        with pytest.raises(RuntimeError, match="provider unavailable"):
            await KnowledgeCreator(FailingModel()).upsert_text(
                "source text", uri=URL, visitor_id="visitor", name="Test"
            )
        assert events == []
        conn.execute.assert_not_awaited()

    asyncio.run(scenario())


@pytest.mark.parametrize("shape,value", [((1, 384), 1), ((0, 768), 1), ((1, 768), np.nan), ((1, 768), 0)])
def test_invalid_embeddings_do_not_modify_saved_knowledge(monkeypatch, shape, value):
    async def scenario():
        conn, events = mock_database(monkeypatch)
        model = FakeEmbeddingModel()
        model.encode = lambda *args, **kwargs: np.full(shape, value)
        with pytest.raises(RuntimeError, match="invalid chunk"):
            await KnowledgeCreator(model).upsert_text(
                "source text", uri=URL, visitor_id="visitor", name="Test"
            )
        assert events == []
        conn.execute.assert_not_awaited()

    asyncio.run(scenario())


def test_write_failure_rolls_back_and_propagates(monkeypatch):
    async def scenario():
        conn, events = mock_database(monkeypatch)
        conn.executemany.side_effect = RuntimeError("write failed")
        with pytest.raises(RuntimeError, match="write failed"):
            await KnowledgeCreator(FakeEmbeddingModel()).upsert_text(
                "source text", uri=URL, visitor_id="visitor", name="Test"
            )
        assert events == ["begin", "rollback"]

    asyncio.run(scenario())


@pytest.fixture
def api(monkeypatch):
    from leobot_router import leobot_knowledge_router as routes

    monkeypatch.setattr(main_config, "LEO_DATA_ENRICHMENT_KEY", ENRICHMENT_KEY)
    creator = SimpleNamespace(upsert_url=AsyncMock(return_value=KnowledgeUpdateResult(
        source_id=uuid7(), visitor_id="visitor", tenant_id="default",
        source_type=KnowledgeSourceType.WEB_PAGE, url=URL, name="Test", status="active",
        chunk_count=2, embedding_dimensions=768,
    )))
    monkeypatch.setattr(routes, "creator", creator)
    app = FastAPI()
    app.include_router(routes.router)
    return TestClient(app), app, creator


def test_update_api_requires_auth_and_valid_query(api):
    client, app, creator = api
    params = {"url": URL, "source_type": "web_page", "visitor_id": "visitor"}
    assert client.post("/_leoai/update-knowledge", params=params).status_code == 401
    assert client.post(
        "/_leoai/update-knowledge",
        params=params,
        headers={"Authorization": "Bearer incorrect-token"},
    ).status_code == 401
    assert client.post(
        "/_leoai/update-knowledge", params=params, auth=("admin", "password"),
    ).status_code == 401
    creator.upsert_url.assert_not_awaited()
    response = client.post(
        "/_leoai/update-knowledge", params=params, headers=ENRICHMENT_HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["chunk_count"] == 2
    assert response.json()["embedding_dimensions"] == 768
    creator.upsert_url.assert_awaited_once_with(
        URL, visitor_id="visitor", source_type=KnowledgeSourceType.WEB_PAGE, name=None,
    )
    assert client.get("/_leoai/update-knowledge", params=params).status_code == 405
    for overrides in [{"visitor_id": ""}, {"visitor_id": " "}, {"visitor_id": "a" * 51},
                      {"url": "not a URL"}, {"source_type": "unknown"}]:
        assert client.post(
            "/_leoai/update-knowledge",
            params={**params, **overrides},
            headers=ENRICHMENT_HEADERS,
        ).status_code == 422
    assert client.post(
        "/update-knowledge", params=params, headers=ENRICHMENT_HEADERS,
    ).status_code == 200


def test_update_api_fails_closed_when_enrichment_key_is_not_configured(
    api, monkeypatch,
):
    client, _, creator = api
    monkeypatch.setattr(main_config, "LEO_DATA_ENRICHMENT_KEY", "")

    response = client.post(
        "/_leoai/update-knowledge",
        params={"url": URL, "visitor_id": "visitor"},
        headers=ENRICHMENT_HEADERS,
    )

    assert response.status_code == 503
    creator.upsert_url.assert_not_awaited()


@pytest.mark.parametrize("error,status", [
    (KnowledgeInputError("Empty page"), 400),
    (KnowledgeFetchError("Download failed"), 502),
    (RuntimeError("sensitive connection error"), 500),
])
def test_update_api_surfaces_errors_without_exposing_internal_details(api, error, status):
    client, _, creator = api
    creator.upsert_url.side_effect = error
    response = client.post(
        "/_leoai/update-knowledge",
        params={"url": URL, "visitor_id": "visitor"},
        headers=ENRICHMENT_HEADERS,
    )
    assert response.status_code == status
    assert "sensitive" not in response.text


def test_application_mounts_the_knowledge_endpoint():
    from main_app import create_app

    schema = create_app().openapi()
    assert "/_leoai/update-knowledge" in schema["paths"]
    operation = schema["paths"]["/_leoai/update-knowledge"]["post"]
    assert operation["security"] == [{"HTTPBearer": []}]
    assert {"visitor_id", "url", "source_type"}.issubset(
        parameter["name"] for parameter in operation["parameters"]
    )


@pytest.mark.skipif(
    os.getenv("RUN_KNOWLEDGE_DB_TESTS") != "1",
    reason="Enable for rollback-only knowledge creation/retrieval validation.",
)
def test_real_database_upsert_replacement_and_document_retrieval(monkeypatch):
    async def scenario():
        conn = await asyncpg.connect(DATABASE_URL)
        tx = conn.transaction()
        await tx.start()
        try:
            schema = f"knowledge_create_test_{uuid4().hex}"
            await conn.execute(f'CREATE SCHEMA "{schema}"')
            await conn.execute(f'SET LOCAL search_path TO "{schema}", public')
            await conn.execute("""
                CREATE TABLE knowledge_sources (
                    id uuid PRIMARY KEY, user_id varchar(50) NOT NULL, tenant_id varchar(50),
                    source_type knowledge_source_type, name text, uri text,
                    status processing_status, metadata jsonb,
                    created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now()
                );
                CREATE TABLE knowledge_chunks (
                    id uuid PRIMARY KEY, source_id uuid REFERENCES knowledge_sources(id),
                    content text NOT NULL, embedding vector(768) NOT NULL,
                    chunk_sequence int, metadata jsonb
                );
            """)

            @asynccontextmanager
            async def connect():
                yield conn

            monkeypatch.setattr(knowledge, "get_async_pg_conn", connect)
            model = FakeEmbeddingModel()
            creator = KnowledgeCreator(model)
            initial = await creator.upsert_text(
                "first second third fourth fifth sixth", uri=URL, name="Guide",
                visitor_id="visitor", max_tokens=4, overlap_tokens=1,
            )
            assert initial.chunk_count == 2
            updated = await creator.upsert_text(
                "Updated RAG CAG knowledge.", uri=URL, name="Updated Guide", visitor_id="visitor",
            )
            assert updated.source_id == initial.source_id
            assert await conn.fetchval("SELECT count(*) FROM knowledge_sources") == 1
            assert await conn.fetchval("SELECT count(*) FROM knowledge_chunks") == 1
            assert await conn.fetchval("SELECT vector_dims(embedding) FROM knowledge_chunks") == 768
            answer = await KnowledgeRetriever(model).retrieve("RAG", "default", user_id="visitor")
            assert "Updated RAG CAG knowledge." in answer
            assert "Source: Updated Guide" in answer
            assert await KnowledgeRetriever(model).retrieve("RAG", "default", user_id="other") == ""
            # Force insertion to fail after deletion; the nested transaction must
            # restore the previous source title and chunk.
            await conn.execute("ALTER TABLE knowledge_chunks ADD CONSTRAINT reject_failure CHECK (content <> 'Fail')")
            with pytest.raises(asyncpg.CheckViolationError):
                await creator.upsert_text("Fail", uri=URL, name="Bad Guide", visitor_id="visitor")
            assert await conn.fetchval("SELECT name FROM knowledge_sources") == "Updated Guide"
            assert await conn.fetchval("SELECT content FROM knowledge_chunks") == "Updated RAG CAG knowledge."
            await creator.upsert_text("Other visitor.", uri=URL, name="Other Guide", visitor_id="other")
            assert await conn.fetchval("SELECT count(*) FROM knowledge_sources") == 2
        finally:
            await tx.rollback()
            await conn.close()

    asyncio.run(scenario())
