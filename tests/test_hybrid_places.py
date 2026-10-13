import asyncio
import math
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import asyncpg
import numpy as np
import pytest

from leoai import rag_db_manager
from leoai.db_utils import DATABASE_URL


def place(name, distance):
    return {
        "id": uuid4(), "name": name, "address": None, "description": None,
        "category": "pho", "tags": [], "distance_meters": distance,
    }


def connection_stub(monkeypatch, lexical, semantic=(), has_vectors=True):
    conn = SimpleNamespace(
        fetch=AsyncMock(side_effect=[lexical, list(semantic)]),
        fetchval=AsyncMock(return_value=has_vectors),
    )

    @asynccontextmanager
    async def connect():
        yield conn

    monkeypatch.setattr(rag_db_manager, "get_async_pg_conn", connect)
    return conn


def test_full_lexical_results_skip_embedding_provider(monkeypatch):
    lexical = [place("Pho A", 50), place("Pho B", 100)]
    conn = connection_stub(monkeypatch, lexical)
    model = Mock()
    results = asyncio.run(rag_db_manager.ChatDBManager(model).find_nearby_places(
        None, ["pho"], 2, user_id="visitor", latitude=10.79, longitude=106.67,
    ))
    assert len(results) == 2
    model.encode.assert_not_called()
    conn.fetchval.assert_not_awaited()
    assert "plainto_tsquery('simple', term)" in conn.fetch.call_args.args[0]


def test_vector_recommendations_are_separate_from_name_matches(monkeypatch):
    lexical = [place("Pho A", 100)]
    semantic = [place("Noodle House", 50)]
    conn = connection_stub(monkeypatch, lexical, semantic)
    model = Mock()
    model.encode.return_value = np.array([1.0] + [0.0] * 767)
    similar = []
    results = asyncio.run(rag_db_manager.ChatDBManager(model).find_nearby_places(
        None, ["pho"], 4, user_id="visitor", latitude=10.79, longitude=106.67,
        radius_meters=5_000, tenant_id="tenant-a",
        similar_places=similar,
    ))
    assert [row["name"] for row in results] == ["Pho A"]
    assert [row["name"] for row in similar] == ["Noodle House"]
    model.encode.assert_called_once_with("pho", normalize_embeddings=True)
    sql, longitude, latitude, radius, missing, tenant, vector, threshold, excluded = (
        conn.fetch.call_args.args
    )
    assert (longitude, latitude, radius, missing, tenant) == (
        106.67, 10.79, 5_000, 4, "tenant-a",
    )
    assert excluded == [str(lexical[0]["id"])]
    assert threshold == 0.35
    assert vector.startswith("[1.0")
    assert "ST_DWithin" in sql and "p.tenant_id IN ($5, 'global')" in sql
    assert "ks.tenant_id = p.tenant_id" in sql
    assert "kc.tenant_id = ks.tenant_id" in sql
    assert "min(kc.embedding <=>" in sql


def test_absent_vectors_skip_embedding_and_allow_discovery(monkeypatch):
    conn = connection_stub(monkeypatch, [], has_vectors=False)
    model = Mock()
    results = asyncio.run(rag_db_manager.ChatDBManager(model).find_nearby_places(
        None, ["pho"], 4, user_id="visitor", latitude=10.79, longitude=106.67,
        similar_places=[],
    ))
    assert results == []
    model.encode.assert_not_called()
    assert conn.fetch.await_count == 1


@pytest.mark.parametrize(
    "vector",
    [
        np.array([1.0] + [0.0] * 766),
        np.zeros(768),
        np.array([float("nan")] + [0.0] * 767),
    ],
)
def test_invalid_search_vectors_are_logged_and_do_not_query_semantic_matches(
    monkeypatch, caplog, vector,
):
    lexical = [place("Pho A", 50)]
    conn = connection_stub(monkeypatch, lexical)
    model = Mock()
    model.encode.return_value = vector
    rows = asyncio.run(rag_db_manager.ChatDBManager(model).find_nearby_places(
        None, ["pho"], 4, user_id="visitor", latitude=10.79, longitude=106.67,
        similar_places=[],
    ))
    assert len(rows) == 1
    assert conn.fetch.await_count == 1
    assert "Invalid 768-dimensional place search vector" in caplog.text


def test_vector_timeout_retains_lexical_matches_without_waiting_for_provider(
    monkeypatch, caplog,
):
    lexical = [place("Pho A", 50)]
    conn = connection_stub(monkeypatch, lexical)
    monkeypatch.setattr(rag_db_manager, "PLACE_VECTOR_TIMEOUT_SECONDS", 0.01)
    provider_finished = []

    def encode(*args, **kwargs):
        time.sleep(0.08)
        provider_finished.append(True)
        return np.array([1.0] + [0.0] * 767)

    async def scenario():
        results = await rag_db_manager.ChatDBManager(
            SimpleNamespace(encode=encode)
        ).find_nearby_places(
            None, ["pho"], 4, user_id="visitor", latitude=10.79, longitude=106.67,
            similar_places=[],
        )
        assert provider_finished == []
        assert len(results) == 1

    asyncio.run(scenario())
    assert conn.fetch.await_count == 1
    assert "Semantic nearby search failed" in caplog.text


@pytest.mark.skipif(
    os.getenv("RUN_NEARBY_DB_TESTS") != "1",
    reason="Enable explicitly for rollback-only PostGIS/pgvector integration tests.",
)
def test_real_hybrid_search_filters_radius_tenants_duplicates_and_irrelevant_vectors(
    monkeypatch,
):
    async def scenario():
        conn = await asyncpg.connect(DATABASE_URL)
        transaction = conn.transaction()
        await transaction.start()
        try:
            schema = f"hybrid_places_{uuid4().hex}"
            await conn.execute(f'CREATE SCHEMA "{schema}"')
            await conn.execute(f'SET LOCAL search_path TO "{schema}", public')
            await conn.execute("""
                CREATE TABLE geo_places (
                    id uuid PRIMARY KEY, tenant_id text, name text,
                    address text, description text, category text, tags text[],
                    geom geometry(Point,4326)
                );
                CREATE TABLE knowledge_sources (
                    id uuid PRIMARY KEY, tenant_id text, status text, metadata jsonb
                );
                CREATE TABLE knowledge_chunks (
                    source_id uuid, tenant_id text, embedding vector(768)
                );
            """)
            indexes = (
                Path(__file__).resolve().parents[1]
                / "sql_scripts" / "geo_places_search_indexes.sql"
            ).read_text()
            # Validate the same index expressions inside the rollback-only schema.
            await conn.execute(indexes.replace("CONCURRENTLY ", ""))
            for name, tenant, offset, axis in [
                ("Pho shop", "global", 0, 0),
                ("Noodle House", "global", 0.001, 0),
                ("Near Threshold", "global", 0.0015, 2),
                ("Beyond Threshold", "global", 0.0018, 3),
                ("Market", "global", 0.002, 1),
                ("Private Noodles", "other", 0.003, 0),
                ("Far Noodles", "global", 0.1, 0),
            ]:
                place_id, source_id = uuid4(), uuid4()
                await conn.execute(
                    "INSERT INTO geo_places VALUES "
                    "($1,$2,$3,NULL,NULL,'eatery',ARRAY[]::text[],"
                    "ST_SetSRID(ST_MakePoint($4,10.79),4326))",
                    place_id, tenant, name, 106.67 + offset,
                )
                await conn.execute(
                    "INSERT INTO knowledge_sources VALUES ($1,$2,'active',"
                    "jsonb_build_object('geo_place_id',$3::text,'source','geo_places'))",
                    source_id, tenant, str(place_id),
                )
                vector = [0.0] * 768
                if axis in (0, 1):
                    vector[axis] = 1.0
                else:
                    vector[0] = 0.66 if axis == 2 else 0.64
                    vector[1] = math.sqrt(1 - vector[0] ** 2)
                for _ in range(2):
                    await conn.execute(
                        "INSERT INTO knowledge_chunks VALUES ($1,$2,$3::vector)",
                        source_id, tenant, str(vector),
                    )

            @asynccontextmanager
            async def connect():
                yield conn

            monkeypatch.setattr(rag_db_manager, "get_async_pg_conn", connect)
            model = Mock()
            model.encode.return_value = np.array([1.0] + [0.0] * 767)
            similar = []
            rows = await rag_db_manager.ChatDBManager(model).find_nearby_places(
                None, ["pho"], 4, user_id="visitor", latitude=10.79,
                longitude=106.67, radius_meters=1_000, tenant_id="tenant-a",
                similar_places=similar,
            )
            assert [row["name"] for row in rows] == ["Pho shop"]
            assert [row["name"] for row in similar] == ["Noodle House", "Near Threshold"]
            assert all(row["distance_meters"] <= 1_000 for row in rows)
            mien_names = ["miến ngon", "Miến trộn Đậu Đậu", "Miến xào Phúc Cua"]
            for name in mien_names:
                await conn.execute(
                    "INSERT INTO geo_places VALUES "
                    "($1,'global',$2,NULL,NULL,'restaurant',ARRAY[]::text[],"
                    "ST_SetSRID(ST_MakePoint(106.67,10.79),4326))",
                    uuid4(), name,
                )
            await conn.execute(
                "UPDATE geo_places SET description='miến', category='miến', "
                "tags=ARRAY['miến'] WHERE name='Market'"
            )
            similar = []
            matches = await rag_db_manager.ChatDBManager(model).find_nearby_places(
                None, ["miến"], 5, user_id="visitor", latitude=10.79,
                longitude=106.67, radius_meters=1_000, tenant_id="tenant-a",
                similar_places=similar,
            )
            assert {row["name"] for row in matches} == set(mien_names)
            assert "Market" not in {row["name"] for row in matches}
            assert "Pho shop" in {row["name"] for row in similar}
            assert not set(mien_names).intersection(row["name"] for row in similar)
        finally:
            await transaction.rollback()
            await conn.close()

    asyncio.run(scenario())
