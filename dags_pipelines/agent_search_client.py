"""Client for Brave Search's Place Search API."""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any

import httpx
import requests
from dotenv import load_dotenv

PLACE_SEARCH_API_URL = "https://api.search.brave.com/res/v1/local/place_search"
LLM_SEARCH_API_URL = "https://api.search.brave.com/res/v1/llm/context"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SEARCH_COUNTRY = "ALL"
DEFAULT_SEARCH_LANG = "vi"
DEFAULT_UNITS = "metric"
DEFAULT_SAFESEARCH = "strict"
DEFAULT_PLACE_COUNTRY = "ALL"
DEFAULT_PLACE_UI_LANG = "en-US"
DEFAULT_LOCATION_CITY = "Ho Chi Minh City"
DEFAULT_LOCATION_STATE = "Ho Chi Minh City"
DEFAULT_LOCATION_COUNTRY = "VN"
DEFAULT_CONTEXT_URLS = 20
DEFAULT_CONTEXT_TOKENS = 8192
DEFAULT_CONTEXT_SNIPPETS = 50
DEFAULT_CONTEXT_TOKENS_PER_URL = 4096
DEFAULT_CONTEXT_SNIPPETS_PER_URL = 50


def _validate_int_range(
    name: str, value: int, minimum: int, maximum: int
) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not minimum <= value <= maximum
    ):
        raise ValueError(f"{name} must be an integer between {minimum} and {maximum}")


class BravePlaceSearchClient:
    """Search Brave's place index and return its decoded JSON response."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        timeout: float = 15.0,
        session: requests.Session | None = None,
    ) -> None:
        load_dotenv(PROJECT_ROOT / ".env")
        configured_api_key = api_key or os.getenv("BRAVE_API_KEY")
        if not configured_api_key or not configured_api_key.strip():
            raise ValueError(
                "Set BRAVE_API_KEY in the environment or repository .env file."
            )
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be greater than zero")

        self.api_key: str = configured_api_key.strip()
        self.timeout = timeout
        self.session = session or requests.Session()

    def search(
        self,
        query: str | None = None,
        *,
        latitude: float | None = None,
        longitude: float | None = None,
        location: str | None = None,
        radius: float | None = None,
        count: int = 10,
        country: str | None = DEFAULT_PLACE_COUNTRY,
        search_lang: str | None = DEFAULT_SEARCH_LANG,
        ui_lang: str | None = DEFAULT_PLACE_UI_LANG,
        units: str | None = DEFAULT_UNITS,
        safesearch: str | None = DEFAULT_SAFESEARCH,
        spellcheck: bool | None = True,
    ) -> dict[str, Any]:
        """Search by query and optional coordinates or named location.

        ``radius`` biases results within the supplied coordinates; it is not a
        hard distance cutoff. Omitting ``query`` requests a general local search.
        The API does not offer ``VN`` or ``vi-VN`` in its Place Search enums,
        so coordinate-based Vietnamese searches use ``ALL``, ``vi``, and
        ``en-US`` while retaining metric units. Pass ``None`` to omit an
        optional request parameter.
        """
        if (latitude is None) != (longitude is None):
            raise ValueError("latitude and longitude must be supplied together")
        if latitude is not None and (
            not math.isfinite(latitude) or not -90 <= latitude <= 90
        ):
            raise ValueError("latitude must be between -90 and 90")
        if longitude is not None and (
            not math.isfinite(longitude) or not -180 <= longitude <= 180
        ):
            raise ValueError("longitude must be between -180 and 180")
        if location and latitude is not None:
            raise ValueError("use either location or latitude/longitude, not both")
        if radius is not None and latitude is None:
            raise ValueError("radius requires latitude and longitude")
        if radius is not None and (not math.isfinite(radius) or radius <= 0):
            raise ValueError("radius must be greater than zero")
        if (
            isinstance(count, bool)
            or not isinstance(count, int)
            or not 1 <= count <= 100
        ):
            raise ValueError("count must be an integer between 1 and 100")
        if query is not None and not query.strip():
            raise ValueError("query must not be empty")
        if location is not None and not location.strip():
            raise ValueError("location must not be empty")
        if country is not None:
            country = country.strip().upper()
            if (
                country != "ALL"
                and (
                    len(country) != 2
                    or not country.isascii()
                    or not country.isalpha()
                )
            ):
                raise ValueError("country must be a two-letter ISO 3166-1 code")
        if search_lang is not None:
            search_lang = search_lang.strip().lower()
            if len(search_lang) < 2:
                raise ValueError("search_lang must contain at least two characters")
        if ui_lang is not None:
            ui_lang = ui_lang.strip()
            if not ui_lang:
                raise ValueError("ui_lang must not be empty")
        if units is not None:
            units = units.strip().lower()
            if units not in {"metric", "imperial"}:
                raise ValueError("units must be metric or imperial")
        if safesearch is not None:
            safesearch = safesearch.strip().lower()
            if safesearch not in {"off", "moderate", "strict"}:
                raise ValueError("safesearch must be off, moderate, or strict")
        if spellcheck is not None and not isinstance(spellcheck, bool):
            raise ValueError("spellcheck must be a boolean")

        params: dict[str, str | float | int | bool] = {"count": count}
        if query is not None:
            params["q"] = query.strip()
        if latitude is not None and longitude is not None:
            params["latitude"] = latitude
            params["longitude"] = longitude
        if location is not None:
            params["location"] = location.strip()
        if radius is not None:
            params["radius"] = radius

        optional_params = {
            "country": country,
            "search_lang": search_lang,
            "ui_lang": ui_lang,
            "units": units,
            "safesearch": safesearch,
            "spellcheck": spellcheck,
        }
        params.update(
            {key: value for key, value in optional_params.items() if value is not None}
        )

        response = self.session.get(
            PLACE_SEARCH_API_URL,
            params=params,
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": self.api_key,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Brave Place Search returned a non-object JSON response")
        if not isinstance(payload.get("results"), list):
            raise ValueError("Brave Place Search response has no results list")
        return payload


class BraveAgentSearch:
    """Asynchronously fetch grounded web results for Vietnamese users.

    Requests include Ho Chi Minh City location headers by default; callers can
    override or omit each location header through the search parameters. The
    API does not support ``VN`` as a country query value, so searches use
    ``ALL`` with Vietnamese language and location preferences.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        timeout: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        load_dotenv(PROJECT_ROOT / ".env")
        configured_api_key = api_key or os.getenv("BRAVE_API_KEY")
        if not configured_api_key or not configured_api_key.strip():
            raise ValueError(
                "Set BRAVE_API_KEY in the environment or repository .env file."
            )
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be greater than zero")

        self.api_key = configured_api_key.strip()
        self.timeout = timeout
        self.transport = transport
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "BraveAgentSearch":
        if self._client is not None:
            raise RuntimeError("BraveAgentSearch is already open")
        self._client = httpx.AsyncClient(
            timeout=self.timeout,
            transport=self.transport,
            trust_env=False,
        )
        return self

    async def __aexit__(self, *_args: Any) -> None:
        del _args
        client = self._client
        self._client = None
        if client is not None:
            await client.aclose()

    async def search(
        self,
        query: str,
        *,
        country: str | None = DEFAULT_SEARCH_COUNTRY,
        search_lang: str | None = DEFAULT_SEARCH_LANG,
        count: int = 20,
        freshness: str | None = None,
        location_city: str | None = DEFAULT_LOCATION_CITY,
        location_state: str | None = DEFAULT_LOCATION_STATE,
        location_country: str | None = DEFAULT_LOCATION_COUNTRY,
        maximum_number_of_urls: int = DEFAULT_CONTEXT_URLS,
        maximum_number_of_tokens: int = DEFAULT_CONTEXT_TOKENS,
        maximum_number_of_snippets: int = DEFAULT_CONTEXT_SNIPPETS,
        maximum_number_of_tokens_per_url: int = DEFAULT_CONTEXT_TOKENS_PER_URL,
        maximum_number_of_snippets_per_url: int = DEFAULT_CONTEXT_SNIPPETS_PER_URL,
    ) -> list[dict[str, Any]]:
        """Return only ``grounding.generic`` results for Vietnamese users."""
        query = query.strip()
        if not query:
            raise ValueError("query must not be empty")
        if len(query) > 600:
            raise ValueError("query must not exceed 600 characters")
        if len(query.split()) > 75:
            raise ValueError("query must not exceed 75 words")
        _validate_int_range("count", count, 1, 50)
        _validate_int_range(
            "maximum_number_of_urls", maximum_number_of_urls, 1, 50
        )
        _validate_int_range(
            "maximum_number_of_tokens", maximum_number_of_tokens, 1024, 32768
        )
        _validate_int_range(
            "maximum_number_of_snippets", maximum_number_of_snippets, 1, 256
        )
        _validate_int_range(
            "maximum_number_of_tokens_per_url",
            maximum_number_of_tokens_per_url,
            512,
            8192,
        )
        _validate_int_range(
            "maximum_number_of_snippets_per_url",
            maximum_number_of_snippets_per_url,
            1,
            100,
        )
        if country is not None:
            country = country.strip().lower()
            if (
                country != "all"
                and (
                    len(country) != 2
                    or not country.isascii()
                    or not country.isalpha()
                )
            ):
                raise ValueError("country must be a two-letter ISO 3166-1 code")
        if search_lang is not None:
            search_lang = search_lang.strip().lower()
            if len(search_lang) < 2:
                raise ValueError("search_lang must contain at least two characters")
        if freshness is not None:
            freshness = freshness.strip()
            if not freshness:
                freshness = None
        for name, value in (
            ("location_city", location_city),
            ("location_state", location_state),
        ):
            if value is not None and not value.strip():
                raise ValueError(f"{name} must not be empty")
        if location_country is not None:
            location_country = location_country.strip().upper()
            if (
                len(location_country) != 2
                or not location_country.isascii()
                or not location_country.isalpha()
            ):
                raise ValueError(
                    "location_country must be a two-letter ISO 3166-1 code"
                )

        params = {
            "q": query,
            "country": country,
            "count": count,
            "search_lang": search_lang,
            "maximum_number_of_urls": maximum_number_of_urls,
            "maximum_number_of_tokens": maximum_number_of_tokens,
            "maximum_number_of_snippets": maximum_number_of_snippets,
            "maximum_number_of_tokens_per_url": maximum_number_of_tokens_per_url,
            "maximum_number_of_snippets_per_url": maximum_number_of_snippets_per_url,
        }
        if freshness is not None:
            params["freshness"] = freshness
        params = {key: value for key, value in params.items() if value is not None}
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": self.api_key,
        }
        headers.update(
            {
                key: value.strip()
                for key, value in {
                    "X-Loc-City": location_city,
                    "X-Loc-State": location_state,
                    "X-Loc-Country": location_country,
                }.items()
                if value is not None
            }
        )
        if self._client is not None:
            response = await self._client.get(
                LLM_SEARCH_API_URL, params=params, headers=headers
            )
        else:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                transport=self.transport,
                trust_env=False,
            ) as client:
                response = await client.get(
                    LLM_SEARCH_API_URL, params=params, headers=headers
                )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Brave Search returned a non-object JSON response")
        grounding = payload.get("grounding")
        if not isinstance(grounding, dict) or not isinstance(
            grounding.get("generic"), list
        ):
            raise ValueError(
                "Brave Search response has no grounding.generic results list"
            )
        if any(not isinstance(item, dict) for item in grounding["generic"]):
            raise ValueError("Brave Search returned an invalid grounding.generic item")
        return grounding["generic"]