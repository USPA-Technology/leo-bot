import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def mock_docker(tmp_path):
    executable = tmp_path / "docker"
    executable.write_text("""#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]
if args[0] == "ps":
    print("pgsql18_vector")
elif args[:2] == ["volume", "inspect"]:
    sys.exit(1)
elif args[0] == "exec":
    if "-i" in args:
        sql = sys.stdin.read()
        kind = "indexes" if "CREATE INDEX CONCURRENTLY" in sql else "schema"
        with Path(os.environ["MOCK_DOCKER_LOG"]).open("a") as log:
            log.write(json.dumps({"kind": kind, "args": args, "sql": sql}) + "\\n")
        if os.environ.get("MOCK_SQL_FAILURE") == kind:
            sys.exit(1)
    elif "psql" in args:
        print("18.0" if "SHOW server_version;" in args else "1")
""")
    executable.chmod(0o755)
    log = tmp_path / "docker.jsonl"
    environment = {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "MOCK_DOCKER_LOG": str(log),
        "TARGET_DB": "test_leo360",
    }
    return log, environment


@pytest.mark.parametrize("failure", [None, "schema", "indexes"])
def test_shared_initializer_applies_sql_in_order_and_stops_on_failure(
    mock_docker, tmp_path, failure,
):
    log, environment = mock_docker
    if failure:
        environment["MOCK_SQL_FAILURE"] = failure
    result = subprocess.run(
        ["bash", str(ROOT / "dockers/pgsql/start_pgsql_pgvector.sh")],
        cwd=tmp_path, env=environment, capture_output=True, text=True,
        timeout=20,
    )
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert [call["kind"] for call in calls] == (
        ["schema"] if failure == "schema" else ["schema", "indexes"]
    )
    for call in calls:
        assert "-X" in call["args"]
        assert "ON_ERROR_STOP=1" in call["args"]
        assert call["args"][-2:] == ["-d", "test_leo360"]
        assert "--single-transaction" not in call["args"]
        assert "-1" not in call["args"]
    assert calls[0]["sql"] == (ROOT / "sql_scripts/leo360_schema.sql").read_text()
    if failure:
        assert result.returncode != 0
        assert "Failed to apply SQL" in result.stderr
        assert "+ PostGIS + pgvector is ready." not in result.stdout
    else:
        assert result.returncode == 0, result.stderr
        assert calls[1]["sql"] == (
            ROOT / "sql_scripts/geo_places_search_indexes.sql"
        ).read_text()


@pytest.mark.parametrize("missing", ["leo360_schema.sql", "geo_places_search_indexes.sql"])
def test_initializer_checks_both_sql_files_before_touching_docker(tmp_path, missing):
    script_dir = tmp_path / "dockers" / "pgsql"
    script_dir.mkdir(parents=True)
    script = script_dir / "start_pgsql_pgvector.sh"
    script.write_text((ROOT / "dockers/pgsql/start_pgsql_pgvector.sh").read_text())
    sql_dir = tmp_path / "sql_scripts"
    sql_dir.mkdir()
    for name in ("leo360_schema.sql", "geo_places_search_indexes.sql"):
        if name != missing:
            (sql_dir / name).write_text("")
    result = subprocess.run(
        ["bash", str(script)], capture_output=True, text=True, timeout=5,
    )
    assert result.returncode != 0
    assert f"Required SQL file not found: {sql_dir / missing}" in result.stderr


def test_both_startup_paths_initialize_sql_before_application_launch():
    production = (ROOT / "start_app.sh").read_text()
    development = (ROOT / "start_dev.sh").read_text()
    assert production.index(
        'bash "$SCRIPT_DIR/dockers/pgsql/start_pgsql_pgvector.sh"'
    ) < production.index('echo "Starting Dagster cluster')
    assert "set -euo pipefail" in production
    assert "set -euo pipefail" in development
    execution = development.split("# EXECUTION FLOW", 1)[1]
    assert execution.index("git pull --quiet") < execution.index("wait_for_postgres")
    assert execution.index("wait_for_postgres") < execution.index('uvicorn "${UVICORN_ARGS[@]}"')
    assert development.count("bash ./dockers/pgsql/start_pgsql_pgvector.sh") == 2
