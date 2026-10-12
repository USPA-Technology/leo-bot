#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

MODE="dev"
SCRIPT_ARGS=()
PGSQL_ARGS=()
for arg in "$@"; do
  if [[ "$arg" == "--cluster" ]]; then
    MODE="cluster"
  elif [[ "$arg" == "--reset-db" ]]; then
    PGSQL_ARGS+=("$arg")
  else
    SCRIPT_ARGS+=("$arg")
  fi
done

PGSQL_SCRIPT="$SCRIPT_DIR/dockers/pgsql/start_pgsql_pgvector.sh"
if [[ ! -f "$PGSQL_SCRIPT" ]]; then
  echo "PostgreSQL startup script not found: $PGSQL_SCRIPT" >&2
  exit 1
fi

echo "Starting PostgreSQL and ensuring TARGET_DB is available."
bash "$PGSQL_SCRIPT" "${PGSQL_ARGS[@]}"

DAGSTER_BIN="$SCRIPT_DIR/env/bin/dagster"
if [[ ! -x "$DAGSTER_BIN" ]]; then
  DAGSTER_BIN="$(command -v dagster || true)"
fi

if [[ -z "$DAGSTER_BIN" || ! -x "$DAGSTER_BIN" ]]; then
  echo "Dagster is not installed in env/bin or on PATH." >&2
  echo "Install project requirements, then run this script again." >&2
  exit 1
fi

if [[ "$MODE" == "dev" ]]; then
  exec "$DAGSTER_BIN" dev -m dags_pipelines "${SCRIPT_ARGS[@]}"
fi

DAGSTER_WEBSERVER_BIN="$SCRIPT_DIR/env/bin/dagster-webserver"
if [[ ! -x "$DAGSTER_WEBSERVER_BIN" ]]; then
  DAGSTER_WEBSERVER_BIN="$(command -v dagster-webserver || true)"
fi

DAGSTER_DAEMON_BIN="$SCRIPT_DIR/env/bin/dagster-daemon"
if [[ ! -x "$DAGSTER_DAEMON_BIN" ]]; then
  DAGSTER_DAEMON_BIN="$(command -v dagster-daemon || true)"
fi

if [[ -z "$DAGSTER_WEBSERVER_BIN" || ! -x "$DAGSTER_WEBSERVER_BIN" ]]; then
  echo "dagster-webserver is not installed in env/bin or on PATH." >&2
  exit 1
fi
if [[ -z "$DAGSTER_DAEMON_BIN" || ! -x "$DAGSTER_DAEMON_BIN" ]]; then
  echo "dagster-daemon is not installed in env/bin or on PATH." >&2
  exit 1
fi

export DAGSTER_HOME="${DAGSTER_HOME:-$SCRIPT_DIR/.dagster}"
LOG_DIR="${DAGSTER_LOG_DIR:-$SCRIPT_DIR/logs}"
PID_DIR="${DAGSTER_PID_DIR:-$SCRIPT_DIR/.dagster-pids}"
WEB_HOST="${DAGSTER_WEB_HOST:-0.0.0.0}"
WEB_PORT="${DAGSTER_WEB_PORT:-3000}"
WEB_LOG="$LOG_DIR/dagster-webserver.log"
DAEMON_LOG="$LOG_DIR/dagster-daemon.log"
WEB_PID_FILE="$PID_DIR/webserver.pid"
DAEMON_PID_FILE="$PID_DIR/daemon.pid"

mkdir -p "$DAGSTER_HOME" "$LOG_DIR" "$PID_DIR"

stop_pid_file() {
  local pid_file="$1"
  local expected_command="$2"
  local pid
  local command

  [[ -f "$pid_file" ]] || return 0
  pid="$(cat "$pid_file")"
  if [[ ! "$pid" =~ ^[0-9]+$ ]] || ! kill -0 "$pid" 2>/dev/null; then
    rm -f "$pid_file"
    return 0
  fi

  command="$(ps -p "$pid" -o args= || true)"
  if [[ "$command" != *"$expected_command"* ]]; then
    echo "Refusing to stop unexpected process $pid from $pid_file." >&2
    rm -f "$pid_file"
    return 0
  fi

  echo "Stopping existing $expected_command process (PID $pid)."
  kill -TERM "$pid"
  for _ in {1..10}; do
    kill -0 "$pid" 2>/dev/null || break
    sleep 1
  done
  if kill -0 "$pid" 2>/dev/null; then
    kill -KILL "$pid"
  fi
  rm -f "$pid_file"
}

stop_pid_file "$WEB_PID_FILE" "dagster-webserver"
stop_pid_file "$DAEMON_PID_FILE" "dagster-daemon"

WEB_ARGS=(
  --host "$WEB_HOST"
  --port "$WEB_PORT"
  -m dags_pipelines
  "${SCRIPT_ARGS[@]}"
)

cleanup() {
  local status=$?
  trap - EXIT
  if [[ -n "${WEB_PID:-}" ]] && kill -0 "$WEB_PID" 2>/dev/null; then
    kill -TERM "$WEB_PID"
  fi
  if [[ -n "${DAEMON_PID:-}" ]] && kill -0 "$DAEMON_PID" 2>/dev/null; then
    kill -TERM "$DAEMON_PID"
  fi
  wait "${WEB_PID:-}" 2>/dev/null || true
  wait "${DAEMON_PID:-}" 2>/dev/null || true
  rm -f "$WEB_PID_FILE" "$DAEMON_PID_FILE"
  exit "$status"
}

trap cleanup EXIT
trap 'exit 143' INT TERM

echo "Starting Dagster webserver on ${WEB_HOST}:${WEB_PORT}."
"$DAGSTER_WEBSERVER_BIN" "${WEB_ARGS[@]}" >>"$WEB_LOG" 2>&1 &
WEB_PID=$!
printf '%s\n' "$WEB_PID" >"$WEB_PID_FILE"

echo "Starting Dagster daemon."
"$DAGSTER_DAEMON_BIN" run -m dags_pipelines >>"$DAEMON_LOG" 2>&1 &
DAEMON_PID=$!
printf '%s\n' "$DAEMON_PID" >"$DAEMON_PID_FILE"

echo "Dagster cluster started."
echo "Webserver log: $WEB_LOG"
echo "Daemon log: $DAEMON_LOG"

set +e
wait -n "$WEB_PID" "$DAEMON_PID"
status=$?
set -e
exit "$status"
