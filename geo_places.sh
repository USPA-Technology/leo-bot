#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${LEO_ENV_FILE:-$SCRIPT_DIR/.env}"
DATABASE_URL=""
MODE=""
DATA_DIR=""

usage() {
  cat <<'USAGE'
Usage:
  ./geo_places.sh --import <folder>
  ./geo_places.sh --export <folder>

Import:
  Applies every .sql file in <folder> in lexical order. PostgreSQL custom,
  tar, and directory dumps are restored with pg_restore.

Export:
  Writes a portable data-only SQL dump of public.geo_places to
  <folder>/geo_places.sql.

The PostgreSQL connection is read from PGSQL_DB_URL in .env, or from the
environment variable LEO_ENV_FILE pointing to another environment file.
USAGE
}

fail() {
  echo "❌ $*" >&2
  exit 1
}

while (($#)); do
  case "$1" in
    --import)
      [[ -z "$MODE" ]] || fail "Choose only one mode."
      [[ -n "${2:-}" ]] || fail "--import requires a folder."
      MODE="import"
      DATA_DIR="$2"
      shift 2
      ;;
    --export)
      [[ -z "$MODE" ]] || fail "Choose only one mode."
      [[ -n "${2:-}" ]] || fail "--export requires a folder."
      MODE="export"
      DATA_DIR="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "Unknown option: $1"
      ;;
  esac
done

[[ -n "$MODE" ]] || {
  usage >&2
  exit 2
}

if [[ ! -f "$ENV_FILE" ]]; then
  fail "Environment file not found: $ENV_FILE"
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

DATABASE_URL="${PGSQL_DB_URL:-}"
[[ -n "$DATABASE_URL" ]] || fail "PGSQL_DB_URL is not configured in $ENV_FILE"

case "$DATABASE_URL" in
  postgres://*|postgresql://*) ;;
  *) fail "PGSQL_DB_URL must be a PostgreSQL connection URL." ;;
esac

command -v psql >/dev/null 2>&1 || fail "psql is required but was not found."
if [[ "$MODE" == "export" ]]; then
  command -v pg_dump >/dev/null 2>&1 || fail "pg_dump is required but was not found."
fi

if [[ "$MODE" == "import" ]]; then
  [[ -d "$DATA_DIR" ]] || fail "Import folder not found: $DATA_DIR"

  mapfile -t SQL_FILES < <(find "$DATA_DIR" -maxdepth 1 -type f -name '*.sql' -print | sort)
  mapfile -t DUMP_FILES < <(
    find "$DATA_DIR" -maxdepth 1 -type f \
      \( -name '*.dump' -o -name '*.backup' -o -name '*.tar' \) -print | sort
  )
  mapfile -t DIRECTORY_DUMPS < <(
    find "$DATA_DIR" -mindepth 1 -maxdepth 1 -type d -name '*.dir' -print | sort
  )

  total_files=$(( ${#SQL_FILES[@]} + ${#DUMP_FILES[@]} + ${#DIRECTORY_DUMPS[@]} ))
  (( total_files > 0 )) || fail "No .sql, .dump, .backup, .tar, or .dir files found in $DATA_DIR"
  if (( ${#DUMP_FILES[@]} + ${#DIRECTORY_DUMPS[@]} > 0 )); then
    command -v pg_restore >/dev/null 2>&1 || fail "pg_restore is required for dump imports."
  fi

  echo "🔧 Importing $total_files PostgreSQL file(s) into the configured database..."
  for sql_file in "${SQL_FILES[@]}"; do
    echo "  → $sql_file"
    psql "$DATABASE_URL" -X -v ON_ERROR_STOP=1 -f "$sql_file"
  done
  for dump_file in "${DUMP_FILES[@]}"; do
    echo "  → $dump_file"
    pg_restore --exit-on-error --no-owner --no-privileges --dbname="$DATABASE_URL" "$dump_file"
  done
  for directory_dump in "${DIRECTORY_DUMPS[@]}"; do
    echo "  → $directory_dump"
    pg_restore --exit-on-error --no-owner --no-privileges --dbname="$DATABASE_URL" "$directory_dump"
  done
  echo "✅ Geo-place data import completed."
else
  mkdir -p "$DATA_DIR"
  [[ -d "$DATA_DIR" ]] || fail "Cannot create export folder: $DATA_DIR"
  OUTPUT_FILE="$DATA_DIR/geo_places.sql"
  TEMP_FILE="$OUTPUT_FILE.tmp.$$"
  trap 'rm -f "$TEMP_FILE"' EXIT

  echo "🔧 Exporting public.geo_places to $OUTPUT_FILE..."
  pg_dump "$DATABASE_URL" \
    --format=plain \
    --data-only \
    --no-owner \
    --no-privileges \
    --table=public.geo_places \
    --file="$TEMP_FILE"
  mv -- "$TEMP_FILE" "$OUTPUT_FILE"
  trap - EXIT
  echo "✅ Geo-place data export completed: $OUTPUT_FILE"
fi
