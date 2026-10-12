import asyncio
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID, uuid5, NAMESPACE_URL

import pytest
from dagster import DagsterInvalidConfigError, validate_run_config

from dags_pipelines import defs
from dags_pipelines.geo_places_pipeline import (
    BravePlace,
    GeoPlaceRepository,
    GeoPlaceSearchService,
    KnowledgeRepository,
    MassScheduleConfig,
    MassScheduleEnricher,
    BraveSearchRepository,
    PlaceEnricher,
    PlaceEnrichment,
    MASS_SCHEMA,
    MassScheduleOutputError,
    build_place_search_query,
)


def test_brave_place_normalizes_location_fields_and_stable_identity():
    raw_place = {
        "title": "St. Mary's Church",
        "description": "A local church.",
        "coordinates": {"latitude": 10.75, "longitude": 106.62},
        "postal_address": {"street": "1 Main St", "city": "HCMC"},
        "thumbnail": {"src": "https://images.example/church.jpg"},
        "categories": ["church", "place of worship"],
    }

    first = BravePlace.from_search_result(raw_place)
    second = BravePlace.from_search_result(raw_place)

    assert first.geo_place_id == second.geo_place_id
    assert first.geo_place_id.startswith("brave_api:")
    assert first.name == "St. Mary's Church"
    assert first.address == "1 Main St, HCMC"
    assert first.search_text == "A local church."
    assert first.image_url == "https://images.example/church.jpg"
    assert first.categories == ("church", "place of worship")


def test_grounding_search_query_uses_name_address_and_category():
    assert build_place_search_query(
        {
            "name": "Nghia Hoa Church",
            "address": "25/18 Nghia Hoa Street",
            "category": "Church",
        }
    ) == "Nghia Hoa Church at 25/18 Nghia Hoa Street in Church"


def test_brave_place_allows_missing_coordinates_for_deferred_recovery():
    place = BravePlace.from_search_result(
        {"title": "Church", "address": "1 Main Street"}
    )

    assert place.latitude is None
    assert place.longitude is None
    assert place.geo_place_id.startswith("brave_api:sha256:")


def test_brave_place_removes_active_markup_and_rejects_script_urls():
    place = BravePlace.from_search_result(
        {
            "title": "<script>alert(1)</script>Church",
            "description": "<img src=x onerror=alert(1)>A parish</img>",
            "coordinates": {"latitude": 10.75, "longitude": 106.62},
            "url": "javascript:alert(1)",
            "thumbnail": {"src": "data:text/html,<script>alert(1)</script>"},
        }
    )

    assert place.name == "Church"
    assert place.search_text == "A parish"
    assert place.website is None
    assert place.image_url is None


def test_search_service_passes_caller_filters_and_deduplicates_results():
    result = {
        "id": "brave-place-1",
        "title": "Church",
        "coordinates": {"latitude": 10.75, "longitude": 106.62},
    }
    unrelated = {
        "id": "district-8",
        "title": "Visit District 8: Best of District 8 Tourism",
        "coordinates": {"latitude": 10.75, "longitude": 106.62},
    }
    client = Mock()
    client.search.return_value = {
        "results": [result, result, unrelated, {"title": "Missing coordinates"}]
    }
    service = GeoPlaceSearchService(client)

    places, skipped = service.search(
        name="church",
        latitude=10.75,
        longitude=106.62,
        radius=6000,
        count=20,
    )

    client.search.assert_called_once_with(
        "church",
        latitude=10.75,
        longitude=106.62,
        radius=6000,
        count=20,
    )
    assert [place.geo_place_id for place in places] == ["brave_api:brave-place-1"]
    assert skipped == 2


def test_search_service_keeps_ramen_places_for_vietnamese_noodle_query():
    client = Mock()
    client.search.return_value = {
        "results": [
            {
                "id": "kohaku-ramen",
                "title": "KOHAKU RAMEN & UDON - PHAN XÍCH LONG",
                "coordinates": [10.79, 106.68],
            },
            {
                "id": "kohaku-udon-ramen",
                "title": "Kohaku Udon & Ramen",
                "coordinates": [10.79, 106.68],
                "rating": "4.5",
            },
        ]
    }
    service = GeoPlaceSearchService(client)

    places, skipped = service.search(
        name="mỳ ramen",
        latitude=10.79,
        longitude=106.68,
        radius=6000,
        count=20,
    )

    assert [place.name for place in places] == [
        "KOHAKU RAMEN & UDON - PHAN XÍCH LONG",
        "Kohaku Udon & Ramen",
    ]
    assert places[1].rating is None
    assert skipped == 0


def test_place_repository_upserts_on_brave_identity(monkeypatch):
    place = BravePlace.from_search_result(
        {
            "id": "brave-place-1",
            "title": "Church",
            "coordinates": {"latitude": 10.75, "longitude": 106.62},
            "thumbnail": {"src": "https://images.example/church.jpg"},
        }
    )
    execute_values = Mock()
    monkeypatch.setattr(
        "dags_pipelines.geo_places_pipeline.execute_values", execute_values
    )
    cursor = Mock()

    GeoPlaceRepository().upsert(cursor, [place])

    sql, rows = execute_values.call_args.args[1:3]
    assert "ON CONFLICT (tenant_id, geo_place_id)" in sql
    assert rows[0][0] == "brave_api:brave-place-1"
    assert rows[0][3] == "Place"
    assert rows[0][5] == "7P28QJ2C+22"
    assert rows[0][6:8] == (10.75, 106.62)
    assert rows[0][-1] == "brave"
    assert execute_values.call_args.kwargs["template"].count("%s") == len(rows[0])


def test_place_enricher_uses_ai_client_for_summary_and_embeddings():
    ai_client = Mock()
    ai_client.generate_json.return_value = {
        "description": "A church in Ho Chi Minh City.",
        "tags": ["church", "Vietnam"],
    }
    ai_client.get_embedding.return_value = [1.0] + [0.0] * 767
    place = {
        "name": "Church",
        "address": "Ho Chi Minh City",
        "search_text": "Place search summary",
        "schedule_operation": None,
        "website": "https://church.example",
        "phone": None,
    }

    enriched = PlaceEnricher(ai_client).enrich(place)

    assert enriched.description == "A church in Ho Chi Minh City."
    assert enriched.tags == ("church", "Vietnam")
    assert enriched.chunks
    assert len(enriched.chunks) == len(enriched.embeddings)
    assert all(len(embedding) == 768 for embedding in enriched.embeddings)
    assert ai_client.generate_json.call_count == 1
    assert ai_client.get_embedding.call_count == len(enriched.chunks)


def test_place_enricher_surfaces_invalid_ai_response():
    ai_client = Mock()
    ai_client.generate_json.return_value = {}

    with pytest.raises(RuntimeError, match="invalid place enrichment"):
        PlaceEnricher(ai_client).enrich({"name": "Church"})


def test_knowledge_repository_upserts_source_and_chunks():
    place_id = UUID("00000000-0000-7000-8000-000000000001")
    place = {
        "id": place_id,
        "geo_place_id": "brave-place-1",
        "name": "Church",
        "website": None,
    }
    enrichment = PlaceEnrichment(
        description="A church.",
        tags=("church",),
        chunks=("Name: Church\nPlace description: A church.",),
        embeddings=((1.0,) + (0.0,) * 767,),
    )
    cursor = Mock()

    source_id = KnowledgeRepository().persist(cursor, place, enrichment)

    assert source_id == uuid5(NAMESPACE_URL, f"geo-place:{place_id}")
    assert cursor.execute.call_count == 3
    assert "UPDATE geo_places" in cursor.execute.call_args_list[0].args[0]
    assert "INSERT INTO knowledge_sources" in cursor.execute.call_args_list[1].args[0]
    assert "DELETE FROM knowledge_chunks" in cursor.execute.call_args_list[2].args[0]
    assert isinstance(cursor.execute.call_args_list[0].args[1][2], str)
    assert isinstance(cursor.execute.call_args_list[1].args[1][0], str)
    assert isinstance(cursor.execute.call_args_list[2].args[1][0], str)
    cursor.executemany.assert_called_once()
    chunk_rows = cursor.executemany.call_args.args[1]
    assert all(isinstance(row[0], str) and isinstance(row[1], str) for row in chunk_rows)
    assert chunk_rows[0][0] == str(uuid5(source_id, "0"))
    assert all(row[1] == "global" for row in chunk_rows)


def test_brave_search_repository_persists_each_source_and_snippet():
    place_id = UUID("00000000-0000-7000-8000-000000000001")
    place = {
        "id": place_id,
        "name": "Nghia Hoa Church",
        "address": "25/18 Nghia Hoa Street",
    }
    ai_client = Mock()
    ai_client.get_embedding.return_value = [0.25] + [0.0] * 767
    cursor = Mock()

    sources, chunks = BraveSearchRepository().persist(
        cursor,
        place,
        [
            {
                "url": "https://saigonarchdiocese.net/parish/nghia-hoa-646",
                "title": "ARCHDIOCESE OF SAIGON",
                "snippets": [
                    "Nghĩa Hoà - Deanery of Chí Hoà",
                    "Mass Schedule: Sunday at 04:30",
                ],
            },
            {
                "url": "https://ca.trip.com/travel-guide/attraction/nghia-hoa",
                "title": "Nghia Hoa Church",
                "snippets": ["Address: 25/18 Nghĩa Hòa Street"],
            },
            {
                "url": "https://travel.example/district-8",
                "title": "Visit District 8: Best of District 8 Tourism",
                "snippets": ["Best tourism attractions and travel tips."],
            },
        ],
        ai_client,
    )

    assert (sources, chunks) == (2, 3)
    assert cursor.execute.call_count == 3
    source_insert = cursor.execute.call_args_list[1].args[1]
    assert isinstance(source_insert[0], str)
    assert source_insert[4] == "ARCHDIOCESE OF SAIGON"
    assert source_insert[5] == "https://saigonarchdiocese.net/parish/nghia-hoa-646"
    assert cursor.execute.call_args_list[2].args[1][4] == "Nghia Hoa Church"
    chunk_rows = [
        row
        for call in cursor.executemany.call_args_list
        for row in call.args[1]
    ]
    assert all(isinstance(row[0], str) and isinstance(row[1], str) for row in chunk_rows)
    assert all(row[1] == "global" for row in chunk_rows)
    assert [row[3] for row in chunk_rows] == [
        "Nghĩa Hoà - Deanery of Chí Hoà",
        "Mass Schedule: Sunday at 04:30",
        "Address: 25/18 Nghĩa Hòa Street",
    ]
    assert [row[5] for row in chunk_rows] == [0, 1, 0]
    assert ai_client.get_embedding.call_count == 3


def test_mass_schedule_enricher_uses_ai_client_for_website_content():
    ai_client = Mock()
    ai_client.generate_json.return_value = {
        "found": True,
        "schedule": [
            {
                "days": ["sun"],
                "times": ["08:00"],
                "note": "",
                "evidence": "Sunday Mass at 08:00",
            }
        ],
        "source_url": "",
        "confidence": 0.9,
        "notes": "",
    }

    class FakeFetcher:
        async def fetch(self, url):
            return SimpleNamespace(
                text="Sunday Mass at 08:00",
                fetched_url=url,
                links=(),
            )

    place = {
        "name": "Church",
        "address": "Ho Chi Minh City",
        "website": "https://church.example",
    }

    schedule = asyncio.run(
        MassScheduleEnricher(
            ai_client, MassScheduleConfig(), FakeFetcher()
        ).find_schedule(place)
    )

    assert schedule == {
        "found": True,
        "schedule": [
            {
                "days": ["sun"],
                "times": ["08:00"],
                "note": None,
                "evidence": "Sunday Mass at 08:00",
            }
        ],
        "source_url": "https://church.example",
        "confidence": 0.9,
        "notes": None,
        "via": "website",
    }
    ai_client.generate_json.assert_called_once()
    assert ai_client.generate_json.call_args.kwargs["system_instruction"]


class _StaticFetcher:
    def __init__(self, text):
        self.text = text

    async def fetch(self, url):
        return SimpleNamespace(text=self.text, fetched_url=url, links=())


def _find_mass_schedule(response, page_text):
    ai_client = Mock()
    ai_client.generate_json.return_value = response
    enricher = MassScheduleEnricher(
        ai_client, MassScheduleConfig(), _StaticFetcher(page_text)
    )
    return asyncio.run(
        enricher.find_schedule(
            {"name": "Church", "address": None, "website": "https://church.example"}
        )
    )


def test_mass_schedule_schemas_are_accepted_by_google_genai():
    from google.genai import types

    from leoai.ai_core import _google_response_schema

    types.Schema.model_validate(_google_response_schema(MASS_SCHEMA))
    types.Schema.model_validate(_google_response_schema(PlaceEnricher.SCHEMA))


def test_mass_schedule_keeps_only_items_backed_by_the_page():
    result = _find_mass_schedule(
        {
            "found": True,
            "confidence": 0.9,
            "source_url": "",
            "notes": "",
            "schedule": [
                {
                    "days": ["sun"],
                    "times": ["08:00"],
                    "note": "",
                    "evidence": "Sunday Mass at 08:00",
                },
                {
                    "days": ["mon"],
                    "times": ["06:00"],
                    "note": "",
                    "evidence": "Monday morning Mass at 06:00 with the parish",
                },
            ],
        },
        "Sunday Mass at 08:00. Weekday Mass at 17:30.",
    )

    assert result["schedule"] == [
        {
            "days": ["sun"],
            "times": ["08:00"],
            "note": None,
            "evidence": "Sunday Mass at 08:00",
        }
    ]


def test_mass_schedule_matches_vietnamese_evidence_ignoring_diacritics():
    result = _find_mass_schedule(
        {
            "found": True,
            "confidence": 0.9,
            "source_url": "",
            "notes": "",
            "schedule": [
                {
                    "days": ["sun"],
                    "times": ["08:00"],
                    "note": "",
                    "evidence": "Chua Nhat 08:00",
                }
            ],
        },
        "Chúa Nhật: 08:00 — Thánh lễ",
    )

    assert result["schedule"][0]["days"] == ["sun"]


def test_mass_schedule_thu_hai_is_not_read_as_thursday():
    result = _find_mass_schedule(
        {
            "found": True,
            "confidence": 0.9,
            "source_url": "",
            "notes": "",
            "schedule": [
                {
                    "days": ["thu"],
                    "times": ["06:00"],
                    "note": "",
                    "evidence": "Thứ Hai 06:00 lễ sáng",
                }
            ],
        },
        "Thứ Hai 06:00 lễ sáng",
    )

    assert result is None


def test_mass_schedule_fabricated_evidence_yields_no_schedule_not_a_crash():
    result = _find_mass_schedule(
        {
            "found": True,
            "confidence": 0.9,
            "source_url": "",
            "notes": "",
            "schedule": [
                {
                    "days": ["sun"],
                    "times": ["08:00"],
                    "note": "",
                    "evidence": "Sunday Mass at 08:00",
                }
            ],
        },
        "Mass times are not listed.",
    )

    assert result is None


def test_mass_schedule_unusable_json_is_classified_as_output_error():
    with pytest.raises(MassScheduleOutputError):
        _find_mass_schedule({"found": "yes", "schedule": []}, "Sunday Mass at 08:00")


def test_mass_schedule_empty_model_response_stays_retryable():
    with pytest.raises(RuntimeError) as info:
        _find_mass_schedule({}, "Sunday Mass at 08:00")

    assert not isinstance(info.value, MassScheduleOutputError)


def test_mass_schedule_crawler_only_follows_same_origin_links():
    class FakeFetcher:
        def __init__(self):
            self.visited = []

        async def fetch(self, url):
            self.visited.append(url)
            if url == "https://church.example":
                return SimpleNamespace(
                    text="Parish website",
                    fetched_url=url,
                    links=(
                        "/mass-schedule",
                        "https://attacker.example/mass-schedule",
                        "javascript:alert(1)",
                    ),
                )
            return SimpleNamespace(
                text="Sunday Mass at 08:00",
                fetched_url=url,
                links=(),
            )

    fetcher = FakeFetcher()
    enricher = MassScheduleEnricher(Mock(), MassScheduleConfig(), fetcher)

    text, urls = asyncio.run(enricher.scrape_site("https://church.example"))

    assert fetcher.visited == [
        "https://church.example",
        "https://church.example/mass-schedule",
    ]
    assert urls == fetcher.visited
    assert "Sunday Mass at 08:00" in text


def test_search_asset_config_requires_name_center_and_radius(monkeypatch):
    monkeypatch.setenv("PGSQL_DB_URL", "validation-placeholder")
    job = defs.resolve_job_def("geo_places_pipeline")
    validate_run_config(
        job,
        {
            "ops": {
                "process_places": {
                    "config": {
                        "name": "church",
                        "latitude": 10.75,
                        "longitude": 106.62,
                        "radius": 6000,
                    }
                }
            }
        },
    )
    with pytest.raises(DagsterInvalidConfigError):
        validate_run_config(
            job,
            {"ops": {"process_places": {"config": {"name": "church"}}}},
        )


BRAVE_EXAMPLE_RESULTS = [
    {
        "title": "St. Paul's Church",
        "url": "https://facebook.com/giaoxuthanhphaolo",
        "provider_url": "",
        "description": "Catholic Church",
        "coordinates": [10.7523098, 106.616141],
        "postal_address": {
            "type": "PostalAddress",
            "displayAddress": "280 Đ. Vành Đai Trong, An Lạc, Hồ Chí Minh 71908, Vietnam",
        },
        "categories": [],
    },
    {
        "title": "Church of the Epiphany",
        "url": "https://giothanhle.net/gio-le/nha-tho-chua-hien-linh-quan-6-tphcm",
        "provider_url": "",
        "description": "Catholic Church",
        "coordinates": [10.7518219, 106.6310276],
        "thumbnail": {
            "src": "https://imgs.search.brave.com/example",
            "original": "https://maikatours.com/wp-content/uploads/2019/12/catholic-church-in-ho-chi-minh-city-cho-quan-church.jpg",
        },
        "postal_address": {
            "type": "PostalAddress",
            "displayAddress": "38 Đ. Kinh Dương Vương, Phú Lâm, Hồ Chí Minh 700000, Vietnam",
        },
        "opening_hours": {"days": []},
        "categories": [],
    },
]


def test_brave_example_list_coordinates_and_display_address_are_mapped():
    client = Mock()
    client.search.return_value = {"results": BRAVE_EXAMPLE_RESULTS}
    places, skipped = GeoPlaceSearchService(client).search(
        name="church", latitude=10.75, longitude=106.63, radius=6000, count=20
    )

    by_name = {place.name: place for place in places}
    assert skipped == 0
    paul = by_name["St. Paul's Church"]
    assert (paul.latitude, paul.longitude) == (10.7523098, 106.616141)
    assert paul.pluscode == "7P28QJ28+WF"
    assert paul.address == "280 Đ. Vành Đai Trong, An Lạc, Hồ Chí Minh 71908, Vietnam"
    assert paul.search_text == "Catholic Church"
    assert paul.website == "https://facebook.com/giaoxuthanhphaolo"
    assert paul.image_url is None
    assert paul.geo_place_id.startswith("brave_api:sha256:")

    epiphany = by_name["Church of the Epiphany"]
    assert (epiphany.latitude, epiphany.longitude) == (10.7518219, 106.6310276)
    assert epiphany.pluscode == "7P28QJ2J+PC"
    assert epiphany.address == "38 Đ. Kinh Dương Vương, Phú Lâm, Hồ Chí Minh 700000, Vietnam"
    assert epiphany.image_url == (
        "https://maikatours.com/wp-content/uploads/2019/12/"
        "catholic-church-in-ho-chi-minh-city-cho-quan-church.jpg"
    )
    assert paul.geo_place_id != epiphany.geo_place_id


@pytest.mark.parametrize("coordinates", [[200, 106.6], [106.6], ["10.7", 106.6]])
def test_brave_invalid_coordinate_lists_are_rejected(coordinates):
    with pytest.raises(ValueError, match="invalid coordinates|must be"):
        BravePlace.from_search_result({"title": "Church", "coordinates": coordinates})


def test_brave_empty_coordinates_defer_recovery_instead_of_failing():
    place = BravePlace.from_search_result({"title": "Church", "coordinates": []})

    assert place.latitude is None
    assert place.longitude is None
