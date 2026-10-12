#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
ENV_FILE="$PROJECT_ROOT/.env"
SCHEMA_FILE="$PROJECT_ROOT/sql_scripts/leo360_schema.sql"
CLEAR_DATA_FILE="$PROJECT_ROOT/sql_scripts/clear_all_data.sql"
SEED_FILE="$PROJECT_ROOT/sql_scripts/sample_places.sql"
PG_CONTAINER_NAME="${PG_CONTAINER_NAME:-pgsql18_vector}"

usage() {
  cat <<'USAGE'
Usage:
  ./start-seeding-data.sh
  ./start-seeding-data.sh --clear-all yes
  ./start-seeding-data.sh --drop-db-and-start-new yes

The destructive options are mutually exclusive and require the literal "yes".
USAGE
}

CLEAR_ALL=false
DROP_DB_AND_START_NEW=false
while (($#)); do
  case "$1" in
    --clear-all)
      if [[ "${2:-}" != "yes" ]]; then
        echo "❌ --clear-all requires the explicit confirmation: yes" >&2
        usage >&2
        exit 2
      fi
      CLEAR_ALL=true
      shift 2
      ;;
    --drop-db-and-start-new)
      if [[ "${2:-}" != "yes" ]]; then
        echo "❌ --drop-db-and-start-new requires the explicit confirmation: yes" >&2
        usage >&2
        exit 2
      fi
      DROP_DB_AND_START_NEW=true
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "❌ Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ "$CLEAR_ALL" == true && "$DROP_DB_AND_START_NEW" == true ]]; then
  echo "❌ Choose either --clear-all or --drop-db-and-start-new, not both." >&2
  exit 2
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "❌ Environment file not found: $ENV_FILE" >&2
  exit 1
fi
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

DATABASE_NAME="${PGSQL_DB_NAME:-leo360}"
DATABASE_URL="${PGSQL_DB_URL:-}"
if [[ -z "$DATABASE_URL" ]]; then
  echo "❌ PGSQL_DB_URL must be configured in $ENV_FILE" >&2
  exit 1
fi
if [[ "$DROP_DB_AND_START_NEW" == true && "$DATABASE_NAME" != "leo360" ]]; then
  echo "❌ --drop-db-and-start-new only operates on the leo360 database." >&2
  exit 2
fi
for sql_file in "$SCHEMA_FILE" "$SEED_FILE"; do
  if [[ ! -f "$sql_file" ]]; then
    echo "❌ Required SQL file not found: $sql_file" >&2
    exit 1
  fi
done
if [[ "$CLEAR_ALL" == true && ! -f "$CLEAR_DATA_FILE" ]]; then
  echo "❌ Clear-data SQL file not found: $CLEAR_DATA_FILE" >&2
  exit 1
fi

admin_database_url() {
  python3 - "$DATABASE_URL" <<'PY'
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import sys

url = urlsplit(sys.argv[1])
if url.scheme not in {"postgres", "postgresql"}:
    raise SystemExit("PGSQL_DB_URL must be a PostgreSQL URI to drop the database.")

query = [(key, value) for key, value in parse_qsl(url.query) if key.lower() != "dbname"]
print(urlunsplit(url._replace(path="/postgres", query=urlencode(query))))
PY
}

USE_HOST_PSQL=false
ADMIN_DATABASE_URL=""
DOCKER_AVAILABLE=false
if command -v docker >/dev/null 2>&1 \
  && docker ps --format '{{.Names}}' | grep -qx "$PG_CONTAINER_NAME"; then
  DOCKER_AVAILABLE=true
fi

if [[ "$DROP_DB_AND_START_NEW" == true ]]; then
  if command -v psql >/dev/null 2>&1; then
    if ! command -v dropdb >/dev/null 2>&1 || ! command -v createdb >/dev/null 2>&1; then
      echo "❌ dropdb and createdb are required for a host PostgreSQL reset." >&2
      exit 1
    fi
    if ! ADMIN_DATABASE_URL="$(admin_database_url)"; then
      echo "❌ Could not create an administrative PostgreSQL connection URL." >&2
      exit 1
    fi
    if ! psql "$ADMIN_DATABASE_URL" -v ON_ERROR_STOP=1 -Atc "SELECT 1" >/dev/null 2>&1; then
      echo "❌ Cannot connect to the PostgreSQL maintenance database; refusing to reset another server." >&2
      exit 1
    fi
    USE_HOST_PSQL=true
  elif [[ "$DOCKER_AVAILABLE" != true ]]; then
    echo "❌ No host PostgreSQL tools or running Docker container found for the reset." >&2
    exit 1
  fi
elif [[ "$CLEAR_ALL" == true ]]; then
  if command -v psql >/dev/null 2>&1; then
    if ! psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -Atc "SELECT 1" >/dev/null 2>&1; then
      echo "❌ Cannot connect through PGSQL_DB_URL; refusing to clear a different Docker database." >&2
      exit 1
    fi
    USE_HOST_PSQL=true
  elif [[ "$DOCKER_AVAILABLE" != true ]]; then
    echo "❌ No host PostgreSQL client or running Docker container found for clearing data." >&2
    exit 1
  fi
elif [[ "$DROP_DB_AND_START_NEW" != true ]] && command -v psql >/dev/null 2>&1 \
  && psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -Atc "SELECT 1" >/dev/null 2>&1; then
  USE_HOST_PSQL=true
fi

if [[ "$USE_HOST_PSQL" != true && "$DOCKER_AVAILABLE" != true ]]; then
  echo "❌ Neither a usable psql connection nor a running PostgreSQL Docker container was found." >&2
  exit 1
fi

run_query() {
  if [[ "$USE_HOST_PSQL" == true ]]; then
    psql "$DATABASE_URL" -v ON_ERROR_STOP=1 "$@"
  else
    docker exec -i -u postgres "$PG_CONTAINER_NAME" \
      psql -v ON_ERROR_STOP=1 -d "$DATABASE_NAME" "$@"
  fi
}

apply_sql_file() {
  local sql_file=$1
  if [[ "$USE_HOST_PSQL" == true ]]; then
    psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$sql_file"
  else
    docker exec -i -u postgres "$PG_CONTAINER_NAME" \
      psql -v ON_ERROR_STOP=1 -d "$DATABASE_NAME" < "$sql_file"
  fi
}

if [[ "$DROP_DB_AND_START_NEW" == true ]]; then
  echo "⚠️ Dropping and recreating database '$DATABASE_NAME'..."
  if [[ "$USE_HOST_PSQL" == true ]]; then
    dropdb --if-exists --force --maintenance-db="$ADMIN_DATABASE_URL" "$DATABASE_NAME"
    createdb --maintenance-db="$ADMIN_DATABASE_URL" "$DATABASE_NAME"
  else
    docker exec -u postgres "$PG_CONTAINER_NAME" \
      dropdb --if-exists --force "$DATABASE_NAME"
    docker exec -u postgres "$PG_CONTAINER_NAME" createdb "$DATABASE_NAME"
  fi
fi

ACTUAL_DATABASE="$(run_query -Atc "SELECT current_database();")"
if [[ "$ACTUAL_DATABASE" != "$DATABASE_NAME" ]]; then
  echo "❌ Connected to database '$ACTUAL_DATABASE'; expected '$DATABASE_NAME'." >&2
  exit 1
fi
echo "✅ Connected to database '$DATABASE_NAME'."

echo "🔧 Applying canonical schema from $SCHEMA_FILE..."
apply_sql_file "$SCHEMA_FILE"

if [[ "$(run_query -Atc "SELECT to_regclass('public.geo_places');")" != "geo_places" ]]; then
  echo "❌ Canonical schema did not create public.geo_places." >&2
  exit 1
fi

if [[ "$CLEAR_ALL" == true ]]; then
  echo "⚠️ Clearing all table data and restarting owned sequences..."
  apply_sql_file "$CLEAR_DATA_FILE"
fi

echo "🌱 Seeding places from $SEED_FILE..."
apply_sql_file "$SEED_FILE"
echo "✅ Seed data applied successfully."
