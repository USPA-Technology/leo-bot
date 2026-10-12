"""Tests for no-results chat enrichment without network or provider calls."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import uuid4

import pytest
from dagster import validate_run_config
from dags_pipelines import defs
from dags_pipelines import geo_places_pipeline as pipeline
from dags_pipelines import geo_places_sql_code
from leoai import rag_agent, rag_agent_utils, rag_db_manager
from leoai.rag_db_manager import ChatDBManager, NearbyLocationUnavailable


@pytest.fixture(autouse=True)
def stub_chat_nearby_intent(monkeypatch):
    def classify(message):
        normalized = message.casefold()
        if "ramen" in normalized:
            return {
                "is_nearby_place_question": True,
                "terms": ["ramen"],
                "search_name": "ramen",
            }
        if "mỳ" in normalized or "mì" in normalized or "my" in normalized:
            return {
                "is_nearby_place_question": True,
                "terms": ["noodles", "mỳ", "mì"],
                "search_name": "noodle",
            }
        if "coffee" in normalized or "café" in normalized or "cafe" in normalized:
            return {
                "is_nearby_place_question": True,
                "terms": ["coffee"],
                "search_name": "coffee",
            }
        if "church" in normalized:
            return {
                "is_nearby_place_question": True,
                "terms": ["church", "cathedral", "nhà thờ"],
                "search_name": "church",
            }
        if "place" in normalized or "places" in normalized:
            return {
                "is_nearby_place_question": True,
                "terms": [],
                "search_name": "places",
            }
        return {
            "is_nearby_place_question": False,
            "terms": [],
            "search_name": "",
        }

    monkeypatch.setattr(rag_agent, "classify_nearby_place_intent", classify)


def intent_client(*, is_nearby, terms, search_name):
    return SimpleNamespace(generate_json=Mock(return_value={
        "is_nearby_place_question": is_nearby,
        "terms": terms,
        "search_name": search_name,
    }))


@pytest.mark.parametrize("question,radius", [
    ("top 3 coffee shop near me in 1 km", 1000),
    ("cafes nearby within 500 meters", 500),
    ("quán cà phê gần tôi trong 1,5 km", 1500),
    ("churches near me in 0.5 kilometres", 500),
    ("places nearby", rag_db_manager.NEARBY_PLACES_RADIUS_METERS),
])
def test_requested_radius(question, radius):
    assert rag_agent_utils.nearby_radius_meters(question) == radius


def test_unaccented_nearby_noodle_question_is_recognized_and_counted():
    question = "3 quán mỳ gần toi"
    intent = intent_client(
        is_nearby=True,
        terms=["noodles", "mỳ", "mì"],
        search_name="noodle",
    )
    assert rag_agent_utils.has_nearby_location_phrase(question)
    assert rag_agent_utils.is_nearby_place_question(question, intent)
    assert rag_agent_utils.nearby_result_limit(question) == 3
    assert rag_agent_utils.nearby_place_terms(question, intent) == [
        "noodles", "mỳ", "mì",
    ]
    assert rag_agent_utils.geo_places_search_name(question, intent) == "noodle"


@pytest.mark.parametrize("question", [
    "coffee near me in 0 km", "places nearby in -1 km",
])
def test_invalid_radius(question):
    with pytest.raises(ValueError, match="radius"):
        rag_agent_utils.nearby_radius_meters(question)


def test_coffee_intent_does_not_match_unrelated_restaurants():
    question = "top 3 coffee shop near me in 1 km"
    coffee_client = intent_client(
        is_nearby=True, terms=["coffee", "cafe"], search_name="coffee",
    )
    assert rag_agent_utils.is_nearby_place_question(question, coffee_client)
    assert rag_agent_utils.geo_places_search_name(question, coffee_client) == "coffee"
    assert "restaurant" not in rag_agent_utils.nearby_place_terms(
        question, coffee_client,
    )
    assert pipeline.place_matches_search("Corner Café", None, [], "coffee")
    assert not pipeline.place_matches_search("Steak Restaurant", None, [], "coffee")
    assert rag_agent_utils.nearby_result_limit("3 coffee shops near me in 1 km") == 3
    ramen_question = "top 3 quán mỳ ramen gần đây"
    ramen_client = intent_client(
        is_nearby=True, terms=["ramen"], search_name="ramen",
    )
    assert rag_agent_utils.is_nearby_place_question(ramen_question, ramen_client)
    assert rag_agent_utils.nearby_place_terms(ramen_question, ramen_client) == ["ramen"]
    assert rag_agent_utils.geo_places_search_name(ramen_question, ramen_client) == "ramen"


def test_nearby_intent_uses_ai_schema_and_rejects_invalid_output():
    client = intent_client(
        is_nearby=True,
        terms=[" ramen ", "ramen", "Japanese ramen", "restaurant"],
        search_name="  ramen  ",
    )

    result = rag_agent_utils.classify_nearby_place_intent(
        "top 3 quán mỳ ramen gần đây", client,
    )

    assert result == {
        "is_nearby_place_question": True,
        "terms": ["ramen", "Japanese ramen"],
        "search_name": "ramen",
    }
    prompt, schema = client.generate_json.call_args.args
    assert "quán mỳ ramen" in prompt
    assert (
        "ramen is not generic restaurant/food"
        in client.generate_json.call_args.kwargs["system_instruction"]
    )
    assert schema == rag_agent_utils.NEARBY_INTENT_SCHEMA
    client.generate_json.return_value = {}
    with pytest.raises(RuntimeError, match="incomplete nearby-place classification"):
        rag_agent_utils.classify_nearby_place_intent(
            "top 3 quán mỳ ramen gần đây", client,
        )


def test_ai_supports_categories_without_a_hard_coded_keyword():
    question = "top 5 omakase restaurants in my area"
    client = intent_client(
        is_nearby=True, terms=["omakase", "Japanese omakase"], search_name="omakase",
    )
    assert rag_agent_utils.has_nearby_location_phrase(question)
    assert rag_agent_utils.is_nearby_place_question(question, client)
    assert rag_agent_utils.nearby_place_terms(question, client) == [
        "omakase", "Japanese omakase",
    ]
    assert client.generate_json.call_count == 2


def test_non_nearby_messages_skip_ai_intent_classification():
    client = intent_client(is_nearby=False, terms=[], search_name="")
    assert not rag_agent_utils.is_nearby_place_question("Tell me about ramen", client)
    client.generate_json.assert_not_called()


def test_general_queues_include_all_categories_and_mass_schedule_stays_church_only():
    for query in (
        geo_places_sql_code.SELECT_SEARCH_PLACES,
        geo_places_sql_code.SELECT_KNOWLEDGE_PLACES,
        geo_places_sql_code.SELECT_TARGETED_SEARCH_PLACES,
        geo_places_sql_code.SELECT_TARGETED_KNOWLEDGE_PLACES,
    ):
        assert "(church|cathedral|chapel|parish|nhà thờ)" not in query
    for query in (
        geo_places_sql_code.SELECT_MASS_SCHEDULE_PLACES,
        geo_places_sql_code.SELECT_TARGETED_MASS_SCHEDULE_PLACES,
    ):
        assert "(church|cathedral|chapel|parish|nhà thờ)" in query
    for query in (
        geo_places_sql_code.SELECT_TARGETED_SEARCH_PLACES,
        geo_places_sql_code.SELECT_TARGETED_KNOWLEDGE_PLACES,
    ):
        assert "ST_DWithin" in query
        assert "LIMIT %s" in query


def test_general_discovery_preserves_provider_category(monkeypatch):
    place = pipeline.BravePlace.from_search_result({
        "id": "cafe", "title": "Corner Cafe", "categories": ["cafe"],
        "coordinates": [10.75, 106.62],
    })
    execute_values = Mock()
    monkeypatch.setattr(pipeline, "execute_values", execute_values)
    pipeline.GeoPlaceRepository().upsert(Mock(), [place], category=None)
    assert execute_values.call_args.args[2][0][3] == "cafe"


def test_generic_place_grounding_matches_place_name_without_church_words():
    assert pipeline.grounding_result_matches_place(
        {"name": "Tokyo Ramen House", "category": "Ramen"},
        "Tokyo Ramen House - Authentic Japanese noodles",
        ["Fresh ramen noodles in a local Japanese restaurant."],
    )
    assert not pipeline.grounding_result_matches_place(
        {"name": "Tokyo Ramen House", "category": "Ramen"},
        "McDonald's",
        ["Global fast food chain known for burgers."],
    )


def test_on_demand_pipeline_config_scopes_all_four_assets():
    config = rag_agent_utils.build_geo_places_pipeline_run_config(
        "ramen", 10.75, 106.62, 1000, count=3,
    )
    assert set(config["ops"]) == {
        "process_places",
        "process_brave_search",
        "process_mass_schedule",
        "process_knowledge",
    }
    assert config["ops"]["process_places"]["config"]["name"] == "ramen"
    for asset_name in (
        "process_brave_search",
        "process_mass_schedule",
        "process_knowledge",
    ):
        asset_config = config["ops"][asset_name]["config"]
        assert asset_config["search_name"] == "ramen"
        assert asset_config["max_places"] == 3
        assert asset_config["latitude"] == 10.75
        assert asset_config["longitude"] == 106.62
        assert asset_config["radius"] == 1000
    validate_run_config(defs.resolve_job_def("geo_places_pipeline"), config)


def test_scoped_postgres_queries_escape_like_wildcards():
    run_config = rag_agent_utils.build_geo_places_pipeline_run_config(
        "noodle", 10.75, 106.62, 1000, count=5,
    )
    scoped_queries = (
        (
            geo_places_sql_code.SELECT_TARGETED_SEARCH_PLACES,
            pipeline.BraveSearchConfig(
                **run_config["ops"]["process_brave_search"]["config"]
            ).search_scope_params(0),
        ),
        (
            geo_places_sql_code.SELECT_TARGETED_MASS_SCHEDULE_PLACES,
            pipeline.MassScheduleConfig(
                **run_config["ops"]["process_mass_schedule"]["config"]
            ).schedule_scope_params(0),
        ),
        (
            geo_places_sql_code.SELECT_TARGETED_KNOWLEDGE_PLACES,
            pipeline.KnowledgeEnrichmentConfig(
                **run_config["ops"]["process_knowledge"]["config"]
            ).knowledge_scope_params(),
        ),
    )

    for query, params in scoped_queries:
        assert query.count("%s") == len(params)
        rendered = query % params
        assert "LIKE '%' || lower(" in rendered
        assert "%s" not in rendered


def test_pipeline_run_config_caps_places_and_rejects_invalid_inputs():
    config = rag_agent_utils.build_geo_places_pipeline_run_config(
        "ramen", 10.75, 106.62, 1000, count=20,
    )
    assert config["ops"]["process_places"]["config"]["count"] == 5
    assert config["ops"]["process_brave_search"]["config"]["max_places"] == 5
    for invalid in (
        {"count": 0},
        {"count": True},
        {"latitude": 91},
        {"longitude": -181},
        {"radius": float("inf")},
        {"name": " "},
    ):
        kwargs = {
            "name": "ramen",
            "latitude": 10.75,
            "longitude": 106.62,
            "radius": 1000,
        }
        kwargs.update(invalid)
        with pytest.raises(ValueError):
            rag_agent_utils.build_geo_places_pipeline_run_config(**kwargs)


def test_full_pipeline_inserts_and_enriches_ramen_places(monkeypatch):
    place_id = uuid4()
    geo_place = {
        "id": place_id,
        "geo_place_id": "brave_api:ramen-1",
        "name": "Tokyo Ramen Shop",
        "address": "1 Noodle Street",
        "category": "Ramen",
        "tags": ["ramen"],
        "latitude": 10.75,
        "longitude": 106.62,
        "phone": None,
        "website": None,
        "description": "Ramen noodle restaurant",
        "schedule_operation": None,
    }
    discovery_client = Mock()
    discovery_client.search.return_value = {"results": [{
        "id": "ramen-1",
        "title": "Tokyo Ramen Shop",
        "description": "Ramen noodle restaurant",
        "coordinates": [10.75, 106.62],
        "categories": ["ramen"],
    }]}

    class EmptyBraveContext:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def search(self, *_args, **_kwargs):
            return []

    ai_client = Mock()
    ai_client.generate_json.return_value = {
        "description": "Ramen noodle restaurant.",
        "tags": ["ramen", "Japanese noodles"],
    }
    ai_client.get_embedding.return_value = [1.0] + [0.0] * 767
    monkeypatch.setattr(
        pipeline.BraveSearchResource,
        "build_client",
        lambda self: discovery_client,
    )
    monkeypatch.setattr(
        pipeline.BraveSearchResource,
        "build_context_client",
        lambda self: EmptyBraveContext(),
    )
    monkeypatch.setattr(
        pipeline.AIResource, "build_client", lambda self: ai_client,
    )
    executed_sql = []
    cursor = MagicMock()
    cursor.__enter__.return_value = cursor

    def execute(statement, params=()):
        executed_sql.append((statement, params))

    cursor.execute.side_effect = execute
    cursor.fetchall.side_effect = lambda: (
        [geo_place]
        if executed_sql[-1][0] in {
            geo_places_sql_code.SELECT_TARGETED_SEARCH_PLACES,
            geo_places_sql_code.SELECT_TARGETED_KNOWLEDGE_PLACES,
        }
        else []
    )
    cursor.executemany = Mock()
    connection = Mock()
    connection.cursor.return_value = cursor
    monkeypatch.setattr(pipeline.psycopg2, "connect", Mock(return_value=connection))
    upsert_rows = []

    def record_upsert(_cursor, _statement, rows, **_kwargs):
        upsert_rows.extend(rows)

    monkeypatch.setattr(pipeline, "execute_values", record_upsert)

    config = rag_agent_utils.build_geo_places_pipeline_run_config(
        "ramen", 10.75, 106.62, 1000, count=3,
    )
    result = defs.resolve_job_def("geo_places_pipeline").execute_in_process(
        run_config=config,
        resources={
            "pg": pipeline.PostgresResource(dsn="test"),
            "brave": pipeline.BraveSearchResource(),
            "ai": pipeline.AIResource(),
        },
    )

    assert result.success
    assert set(result.job_def.graph.node_names()) == {
        "process_places",
        "process_brave_search",
        "process_mass_schedule",
        "process_knowledge",
    }
    assert discovery_client.search.call_args.args[0] == "ramen"
    assert upsert_rows[0][3] == "Ramen"
    assert any("SELECT gp.id" in sql and "data_checked_at" in sql for sql, _ in executed_sql), executed_sql
    assert any("SELECT gp.id" in sql and "knowledge_sources" in sql for sql, _ in executed_sql), executed_sql
    assert any(
        "INSERT INTO knowledge_sources" in sql and params[4] == "Tokyo Ramen Shop"
        for sql, params in executed_sql
    )
    assert any(
        "UPDATE geo_places" in sql and params[0] == "Ramen noodle restaurant."
        for sql, params in executed_sql
    )
    assert cursor.executemany.called
    assert ai_client.generate_json.called


def test_trigger_submits_bounded_job_without_polling(monkeypatch):
    client = Mock()
    client.submit_job_execution.return_value = "run-id"
    factory = Mock(return_value=client)
    monkeypatch.setattr(rag_agent_utils, "DagsterGraphQLClient", factory)
    monkeypatch.setenv("DAGSTER_HOST", "dagster")
    monkeypatch.setenv("DAGSTER_WEB_PORT", "3001")
    monkeypatch.setenv("DAGSTER_REPOSITORY_LOCATION", "dags_pipelines")
    monkeypatch.setenv("DAGSTER_REPOSITORY", "__repository__")
    run_id = rag_agent_utils.trigger_geo_places_enrichment(
        "coffee", 10.75, 106.62, 1000, count=20,
    )

    assert run_id == "run-id"
    factory.assert_called_once_with("dagster", port_number=3001, timeout=15)
    submitted = client.submit_job_execution.call_args
    assert submitted.args == ("geo_places_pipeline",)
    config = submitted.kwargs["run_config"]
    assert set(config["ops"]) == {
        "process_places",
        "process_brave_search",
        "process_mass_schedule",
        "process_knowledge",
    }
    assert config["ops"]["process_places"]["config"] == {
        "name": "coffee",
        "latitude": 10.75,
        "longitude": 106.62,
        "radius": 1000,
        "count": 5,
    }
    assert config["ops"]["process_brave_search"]["config"]["search_name"] == "coffee"
    assert config["ops"]["process_mass_schedule"]["config"]["search_name"] == "coffee"
    assert config["ops"]["process_knowledge"]["config"]["search_name"] == "coffee"
    assert submitted.kwargs["asset_selection"] == [
        "process_places",
        "process_brave_search",
        "process_mass_schedule",
        "process_knowledge",
    ]
    validate_run_config(defs.resolve_job_def("geo_places_pipeline"), config)
    client.get_run_status.assert_not_called()


def test_enrichment_status_uses_configured_dagster_client(monkeypatch):
    client = Mock()
    client.get_run_status.return_value = SimpleNamespace(name="STARTED")
    factory = Mock(return_value=client)
    monkeypatch.setattr(rag_agent_utils, "DagsterGraphQLClient", factory)
    monkeypatch.setenv("DAGSTER_HOST", "dagster")
    monkeypatch.setenv("DAGSTER_WEB_PORT", "3001")

    status = rag_agent_utils.get_geo_places_enrichment_status("run-id")

    assert status == "STARTED"
    factory.assert_called_once_with("dagster", port_number=3001, timeout=15)
    client.get_run_status.assert_called_once_with("run-id")


@pytest.mark.parametrize("invalid", [
    {"count": 0}, {"count": True}, {"latitude": 91},
    {"longitude": -181}, {"radius": float("inf")}, {"name": " "},
])
def test_invalid_submission_never_contacts_dagster(monkeypatch, invalid):
    factory = Mock()
    monkeypatch.setattr(rag_agent_utils, "DagsterGraphQLClient", factory)
    kwargs = {"name": "coffee", "latitude": 10.75, "longitude": 106.62, "radius": 1000}
    kwargs.update(invalid)
    with pytest.raises(ValueError):
        rag_agent_utils.trigger_geo_places_enrichment(**kwargs)
    factory.assert_not_called()


def make_agent(places):
    agent = rag_agent.RAGAgent.__new__(rag_agent.RAGAgent)
    agent.db = SimpleNamespace(
        find_nearby_places=AsyncMock(return_value=places),
        resolve_nearby_location=AsyncMock(return_value=(10.75, 106.62)),
        save_chat_message=AsyncMock(),
    )
    agent._safe_generate = AsyncMock()
    return agent


@pytest.mark.parametrize(
    ("language", "has_places", "expected"),
    [
        ("Vietnamese", False, "tìm và bổ sung địa điểm"),
        ("vi-VN", True, "tìm thêm địa điểm"),
        ("English", False, "queued a search to find and add places"),
        ("en", True, "queued a search for more places"),
    ],
)
def test_build_geo_places_enrichment_notice(language, has_places, expected):
    notice = rag_agent._build_geo_places_enrichment_notice(language, has_places)
    assert expected in notice


@pytest.mark.parametrize("question,language,expected,search_term", [
    (
        "top 3 coffee shop near me in 1 km",
        "English",
        "I have queued a search",
        "coffee",
    ),
    (
        "top 3 quán mỳ ramen gần đây",
        "Vietnamese",
        "Mình đã gửi yêu cầu",
        "ramen",
    ),
])
def test_empty_search_queues_enrichment_and_returns_notice(
    monkeypatch, question, language, expected, search_term,
):
    trigger = Mock(return_value="run-id")
    monkeypatch.setattr(rag_agent, "trigger_geo_places_enrichment", trigger)
    agent = make_agent([])

    response = asyncio.run(agent.process_chat_message(
        "visitor", question, target_language=language,
        touchpoint_id="tp", latitude=10.75, longitude=106.62,
    ))

    assert expected in response
    trigger.assert_called_once_with(
        name=search_term,
        latitude=10.75,
        longitude=106.62,
        radius=(
            1000 if "1 km" in question
            else rag_db_manager.NEARBY_PLACES_RADIUS_METERS
        ),
        count=3,
    )
    agent.db.find_nearby_places.assert_awaited_once_with(
        "tp", ["coffee"] if search_term == "coffee" else ["ramen"], 3,
        user_id="visitor",
        latitude=10.75,
        longitude=106.62,
        radius_meters=(
            1000 if "1 km" in question
            else rag_db_manager.NEARBY_PLACES_RADIUS_METERS
        ),
        tenant_id="default",
    )
    agent._safe_generate.assert_not_awaited()
    assert agent.db.save_chat_message.await_args_list[1].args[2] == response
    assert all(call.kwargs["embed"] is False for call in agent.db.save_chat_message.await_args_list)


def test_existing_results_do_not_trigger_enrichment(monkeypatch):
    trigger = Mock()
    monkeypatch.setattr(rag_agent, "trigger_geo_places_enrichment", trigger)
    agent = make_agent([{"name": "Coffee Shop", "distance_meters": 500}])
    response = asyncio.run(agent.process_chat_message(
        "visitor", "top 1 coffee shop near me in 1 km", target_language="English",
    ))
    assert "Coffee Shop" in response
    trigger.assert_not_called()
    agent.db.resolve_nearby_location.assert_not_awaited()


@pytest.mark.parametrize(
    ("requested_count", "expected_enrichment_count"),
    [(5, 4), (20, 5)],
)
def test_partial_results_queue_only_the_missing_places_and_keep_existing_results(
    monkeypatch, requested_count, expected_enrichment_count,
):
    trigger = Mock(return_value="run-id")
    monkeypatch.setattr(rag_agent, "trigger_geo_places_enrichment", trigger)
    agent = make_agent([{"name": "Coffee Shop", "distance_meters": 500}])

    response = asyncio.run(agent.process_chat_message(
        "visitor", f"top {requested_count} coffee shop near me",
        target_language="English",
    ))

    assert "Coffee Shop" in response
    assert "queued a search for more places" in response
    trigger.assert_called_once_with(
        name="coffee",
        latitude=10.75,
        longitude=106.62,
        radius=rag_db_manager.NEARBY_PLACES_RADIUS_METERS,
        count=expected_enrichment_count,
    )
    assert agent.db.save_chat_message.await_args_list[1].args[2] == response


def test_missing_location_does_not_trigger_enrichment(monkeypatch):
    trigger = Mock()
    monkeypatch.setattr(rag_agent, "trigger_geo_places_enrichment", trigger)
    agent = make_agent([])
    agent.db.find_nearby_places.side_effect = NearbyLocationUnavailable()
    response = asyncio.run(agent.process_chat_message(
        "visitor", "coffee near me", target_language="English",
    ))
    assert "share your location" in response
    trigger.assert_not_called()
    agent.db.save_chat_message.assert_not_awaited()


def test_enrichment_resolves_cached_touchpoint_when_coordinates_are_not_in_request(monkeypatch):
    trigger = Mock(return_value="run-id")
    monkeypatch.setattr(rag_agent, "trigger_geo_places_enrichment", trigger)
    agent = make_agent([])
    response = asyncio.run(agent.process_chat_message(
        "visitor", "coffee near me in 1 km", touchpoint_id="cached-tp",
        target_language="English",
    ))
    assert "queued" in response
    agent.db.resolve_nearby_location.assert_awaited_once_with(
        "cached-tp", user_id="visitor", latitude=None, longitude=None,
        tenant_id="default",
    )
    trigger.assert_called_once_with(
        name="coffee", latitude=10.75, longitude=106.62, radius=1000,
        count=5,
    )


def test_rejected_submission_never_claims_search_was_queued(monkeypatch, caplog):
    trigger = Mock(side_effect=RuntimeError("Dagster unavailable"))
    monkeypatch.setattr(rag_agent, "trigger_geo_places_enrichment", trigger)
    agent = make_agent([])
    response = asyncio.run(agent.process_chat_message(
        "visitor", "coffee near me", target_language="English",
    ))
    assert "something went wrong" in response
    assert "queued" not in response
    assert "RAG pipeline error" in caplog.text
    agent.db.save_chat_message.assert_not_awaited()


def test_enrichment_run_id_survives_chat_persistence_error(monkeypatch):
    trigger = Mock(return_value="run-id")
    monkeypatch.setattr(rag_agent, "trigger_geo_places_enrichment", trigger)
    agent = make_agent([])
    agent.db.save_chat_message.side_effect = RuntimeError("chat persistence failed")

    result = asyncio.run(agent.process_chat_message_with_metadata(
        "visitor", "coffee near me", target_language="English",
    ))

    assert result["enrichment_run_id"] == "run-id"
    assert "something went wrong" in result["response"]


def test_enrichment_uses_owned_touchpoint_and_requested_sql_radius(monkeypatch):
    conn = SimpleNamespace(
        fetchrow=AsyncMock(return_value={"latitude": 10.75, "longitude": 106.62}),
        fetch=AsyncMock(return_value=[]),
    )

    @asynccontextmanager
    async def connect():
        yield conn

    monkeypatch.setattr(rag_db_manager, "get_async_pg_conn", connect)
    asyncio.run(ChatDBManager(None).find_nearby_places(
        "tp", ["coffee"], 3, user_id="visitor", radius_meters=1000,
    ))
    assert "tenant_id = $1 AND touchpoint_id = $2 AND user_id = $3" in (
        conn.fetchrow.call_args.args[0]
    )
    assert conn.fetchrow.call_args.args[1:] == ("default", "tp", "visitor")
    assert conn.fetch.call_args.args[-3:] == (1000, 3, "default")
    conn.fetchrow.return_value = None
    with pytest.raises(NearbyLocationUnavailable):
        asyncio.run(ChatDBManager(None).resolve_nearby_location(
            "other-tp", user_id="visitor",
        ))
