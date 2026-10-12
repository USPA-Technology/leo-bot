"""Shared normalization and relevance helpers for geo-place assets."""

from __future__ import annotations

import logging
import math
import re
import unicodedata
from typing import Any, Iterable

from bs4 import BeautifulSoup

from leoai.rag_knowledge_manager import KnowledgeInputError, PublicWebPageFetcher

LOGGER = logging.getLogger(__name__)

_SEARCH_STOP_WORDS = {
    "a",
    "an",
    "and",
    "basilica",
    "cathedral",
    "catholic",
    "chapel",
    "church",
    "cong",
    "giao",
    "nha",
    "of",
    "parish",
    "the",
    "tho",
    "xu",
}
_PLACE_CONTEXT_TERMS = (
    "archdiocese",
    "basilica",
    "catholic",
    "cathedral",
    "chapel",
    "church",
    "giao xu",
    "mass",
    "nha tho",
    "parish",
    "thanh duong",
)


def fold(value: str) -> str:
    """Lowercase text, remove Vietnamese diacritics, and keep words."""
    value = (value or "").replace("đ", "d").replace("Đ", "D")
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char)).lower()
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def meaningful_search_tokens(value: str | None) -> set[str]:
    return {
        token
        for token in fold(value or "").split()
        if token not in _SEARCH_STOP_WORDS and len(token) > 1
    }


def has_place_context(text: str) -> bool:
    return any(term in text for term in _PLACE_CONTEXT_TERMS)


def place_matches_search(
    place_name: str,
    search_text: str | None,
    categories: Iterable[str],
    search_name: str,
) -> bool:
    searchable_text = fold(
        " ".join((place_name, search_text or "", " ".join(categories)))
    )
    if fold(search_name) == "coffee":
        return (
            bool({"coffee", "cafe"}.intersection(searchable_text.split()))
            or "ca phe" in searchable_text
        )
    query_tokens = meaningful_search_tokens(search_name)
    if "ramen" in query_tokens:
        query_tokens.difference_update({"mi", "my", "noodle", "noodles"})
    if query_tokens:
        return query_tokens.issubset(set(searchable_text.split()))
    return has_place_context(searchable_text)


def grounding_result_matches_place(
    place: dict[str, Any], title: str, snippets: list[str]
) -> bool:
    searchable_text = fold(" ".join([title, *snippets]))
    place_tokens = meaningful_search_tokens(place.get("name"))
    if not place_tokens:
        place_tokens = meaningful_search_tokens(place.get("address"))
    if not place_tokens or not place_tokens.issubset(set(searchable_text.split())):
        return False
    category = fold(str(place.get("category") or ""))
    is_church = any(
        term in category
        for term in ("church", "cathedral", "chapel", "parish", "nha tho")
    )
    return not is_church or has_place_context(searchable_text)


def text_value(value: Any) -> str | None:
    if isinstance(value, str):
        if re.search(r"</?[A-Za-z][^>]*>", value):
            soup = BeautifulSoup(value, "html.parser")
            for tag in soup(["script", "style", "iframe", "object", "svg", "noscript"]):
                tag.decompose()
            value = soup.get_text(" ", strip=True)
        return value.strip() or None
    if isinstance(value, dict):
        parts = [text_value(item) for item in value.values()]
        return ", ".join(part for part in parts if part) or None
    if isinstance(value, (list, tuple)):
        parts = [text_value(item) for item in value]
        return ", ".join(part for part in parts if part) or None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return None


def safe_website_url(value: Any) -> str | None:
    website = text_value(value)
    if not website:
        return None
    try:
        return str(PublicWebPageFetcher.normalize_url(website))
    except KnowledgeInputError:
        LOGGER.warning("Ignoring unsupported external website URL")
        return None


def image_url(place: dict[str, Any]) -> str | None:
    candidates = [place.get("thumbnail")]
    pictures = place.get("pictures")
    if isinstance(pictures, list):
        candidates.extend(pictures)
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            safe_url = safe_website_url(candidate)
            if safe_url:
                return safe_url
        if isinstance(candidate, dict):
            for key in ("original", "src", "url", "image_url"):
                url = candidate.get(key)
                if isinstance(url, str) and url.strip():
                    safe_url = safe_website_url(url)
                    if safe_url:
                        return safe_url
    return None


def parse_coordinates(value: Any) -> tuple[float | None, float | None]:
    """Read Brave's [latitude, longitude] list or a {latitude, longitude} object."""
    if not value:
        return None, None
    if isinstance(value, dict):
        latitude, longitude = value.get("latitude"), value.get("longitude")
    elif isinstance(value, (list, tuple)) and len(value) == 2:
        latitude, longitude = value
    else:
        raise ValueError("coordinates must be [latitude, longitude]")
    if latitude is None or longitude is None:
        return None, None
    for number in (latitude, longitude):
        if isinstance(number, bool) or not isinstance(number, (int, float)):
            raise ValueError("coordinates must be numeric")
    lat, lon = float(latitude), float(longitude)
    if not math.isfinite(lat) or not math.isfinite(lon):
        raise ValueError("coordinates must be finite")
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError("coordinates are out of range")
    return lat, lon


def postal_address_text(value: Any) -> str | None:
    """Use Brave's displayAddress; ignore structural keys such as 'type'."""
    if isinstance(value, dict):
        display = value.get("displayAddress")
        if isinstance(display, str) and display.strip():
            return display.strip()
        return text_value({key: item for key, item in value.items() if key != "type"})
    return text_value(value)
