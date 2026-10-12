"""Trigger bounded church-place discovery and knowledge enrichment on Dagster.

Start the cluster first (``./start_dagster.sh --cluster``), then run:

    env/bin/python -m test_poc.test_trigger_geo_places_tasks

Use ``--dry-run`` to validate the run config locally without contacting the
webserver. A real run calls Brave Place Search, so it may consume API quota.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Any

if __package__:
    from . import _bootstrap
else:
    import _bootstrap

from dagster import DagsterRunStatus, validate_run_config
from dagster_graphql import DagsterGraphQLClient

from dags_pipelines import defs
from leoai.rag_agent_utils import (
    GEO_PLACES_PIPELINE_JOB,
    build_geo_places_pipeline_run_config,
    trigger_geo_places_enrichment,
)

JOB_NAME = GEO_PLACES_PIPELINE_JOB
PLACE_DISCOVERY_CONFIG: dict[str, Any] = {
    "name": "church",
    "latitude": 10.7536097,
    "longitude": 106.6284595,
    "radius": 6000,
    "count": 5,
}
RUN_CONFIG = build_geo_places_pipeline_run_config(**PLACE_DISCOVERY_CONFIG)
TERMINAL_STATUSES = {
    DagsterRunStatus.SUCCESS,
    DagsterRunStatus.FAILURE,
    DagsterRunStatus.CANCELED,
}


def validate_geo_places_pipeline_config() -> None:
    """Check the run config against the job definition without any network call."""
    validate_run_config(defs.resolve_job_def(JOB_NAME), RUN_CONFIG)


def trigger_geo_places_pipeline(
    host: str,
    port: int,
    repository_location: str,
    repository: str,
    timeout_seconds: int,
    poll_seconds: int = 5,
) -> DagsterRunStatus:
    """Use the shared full-pipeline trigger and wait for completion in this CLI."""
    run_id = trigger_geo_places_enrichment(
        **PLACE_DISCOVERY_CONFIG,
        host=host,
        port=port,
        repository_location=repository_location,
        repository=repository,
    )
    client = DagsterGraphQLClient(host, port_number=port, timeout=15)
    print(f"Submitted {JOB_NAME} run {run_id}.")

    deadline = time.monotonic() + timeout_seconds
    while True:
        status = client.get_run_status(run_id)
        if status in TERMINAL_STATUSES:
            print(f"Run {run_id} finished with status {status.value}.")
            return status
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"Run {run_id} still {status.value} after {timeout_seconds}s; "
                "check the Dagster UI for its progress."
            )
        time.sleep(poll_seconds)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Trigger the geo places pipeline on Dagster.")
    parser.add_argument("--dry-run", action="store_true", help="validate config only")
    parser.add_argument(
        "--host", default=os.getenv("DAGSTER_HOST", "localhost"),
        help="Dagster webserver host (default: DAGSTER_HOST or localhost)",
    )
    parser.add_argument(
        "--port", type=int, default=int(os.getenv("DAGSTER_WEB_PORT", "3000")),
        help="Dagster webserver port (default: DAGSTER_WEB_PORT or 3000)",
    )
    parser.add_argument(
        "--repository-location", default="dags_pipelines",
        help="code location name, the module passed to dagster -m",
    )
    parser.add_argument(
        "--repository", default="__repository__",
        help="repository name inside the code location",
    )
    parser.add_argument(
        "--timeout", type=int, default=900, help="seconds to wait for the run",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    validate_geo_places_pipeline_config()
    print(f"Run config is valid for {JOB_NAME}; discovering up to five places.")
    if args.dry_run:
        return 0

    status = trigger_geo_places_pipeline(
        host=args.host,
        port=args.port,
        repository_location=args.repository_location,
        repository=args.repository,
        timeout_seconds=args.timeout,
    )
    return 0 if status == DagsterRunStatus.SUCCESS else 1


if __name__ == "__main__":
    sys.exit(main())
