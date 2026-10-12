"""Run a sample Brave Place Search request for churches in Ho Chi Minh City."""

from __future__ import annotations

import json
import math
from typing import Any

if __package__:
    from . import _bootstrap
else:
    import _bootstrap

from dags_pipelines.agent_search_client import BravePlaceSearchClient


def _distance_from_origin(
    place: dict[str, Any], origin_latitude: float, origin_longitude: float
) -> float:
    coordinates = place.get("coordinates")
    if not isinstance(coordinates, dict):
        return math.inf

    latitude = coordinates.get("latitude")
    longitude = coordinates.get("longitude")
    if (
        isinstance(latitude, bool)
        or not isinstance(latitude, (int, float))
        or isinstance(longitude, bool)
        or not isinstance(longitude, (int, float))
        or not math.isfinite(latitude)
        or not math.isfinite(longitude)
        or not -90 <= latitude <= 90
        or not -180 <= longitude <= 180
    ):
        return math.inf

    lat1 = math.radians(origin_latitude)
    lat2 = math.radians(latitude)
    delta_lat = lat2 - lat1
    delta_lon = math.radians(longitude - origin_longitude)
    haversine = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * 6_371_000 * math.asin(math.sqrt(min(1.0, haversine)))


def main() -> None:
    client = BravePlaceSearchClient()
    latitude = 10.7536097
    longitude = 106.6284595
    result = client.search(
        "church",
        latitude=latitude,
        longitude=longitude,
        radius=5000,
        count=2,
    )
    fields = (
        "title",
        "url",
        "provider_url",
        "description",
        "coordinates",
        "thumbnail",
        "postal_address",
        "opening_hours",
        "categories"
    )
    places = [
        {field: place[field] for field in fields if field in place}
        for place in sorted(
            result["results"],
            key=lambda place: _distance_from_origin(place, latitude, longitude),
        )
    ]
    print(json.dumps(places, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
