#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

APP_NAME="leobot"
APP_MODULE="main_app:leobot"
VENV_PATH="$SCRIPT_DIR/env"
HOST="${LEOBOT_HOST:-0.0.0.0}"
PORT="${LEOBOT_PORT:-8888}"
WORKERS="${UVICORN_WORKERS:-1}"
SEED_DATA=false
RESET_DB=false

for arg in "$@"; do
  case "$arg" in
    --seed-data) SEED_DATA=true ;;
    --reset-db) RESET_DB=true ;;
    *)
      echo "Unknown option: $arg" >&2
      exit 1
      ;;
  esac
done

ENV_FILE="${LEO_ENV_FILE:-$SCRIPT_DIR/.env}"
if [[ -f "$ENV_FILE" ]]; then
  echo "Loading configuration from $ENV_FILE."
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
else
  echo "Environment file not found at $ENV_FILE; using exported environment variables."
fi

HOST="${LEOBOT_HOST:-$HOST}"
PORT="${LEOBOT_PORT:-$PORT}"
WORKERS="${UVICORN_WORKERS:-$WORKERS}"
LOG_DIR="${LEOBOT_LOG_DIR:-$SCRIPT_DIR/logs}"
DAGSTER_PID_DIR="${DAGSTER_PID_DIR:-$SCRIPT_DIR/.dagster-pids}"
PID_DIR="${LEOBOT_PID_DIR:-$DAGSTER_PID_DIR}"
DAGSTER_WEB_PORT="${DAGSTER_WEB_PORT:-3000}"
DAGSTER_STARTUP_TIMEOUT="${DAGSTER_STARTUP_TIMEOUT:-60}"
APP_STARTUP_TIMEOUT="${LEOBOT_STARTUP_TIMEOUT:-30}"
APP_PID_FILE="$PID_DIR/chatbot.pid"
DAGSTER_MANAGER_PID_FILE="$PID_DIR/dagster-cluster.pid"
DAGSTER_MANAGER_LOG="$LOG_DIR/dagster-cluster-manager.log"
APP_LOG_FILE="$LOG_DIR/${APP_NAME}-$(date '+%Y-%m-%d_%H-%M-%S').log"

mkdir -p "$LOG_DIR" "$PID_DIR" "$DAGSTER_PID_DIR"

if [[ ! "$DAGSTER_STARTUP_TIMEOUT" =~ ^[1-9][0-9]*$ ]]; then
  echo "DAGSTER_STARTUP_TIMEOUT must be a positive integer." >&2
  exit 1
fi
if [[ ! "$APP_STARTUP_TIMEOUT" =~ ^[1-9][0-9]*$ ]]; then
  echo "LEOBOT_STARTUP_TIMEOUT must be a positive integer." >&2
  exit 1
fi

if [[ ! -x "$VENV_PATH/bin/python" ]]; then
  echo "Python virtual environment not found. Creating Python 3.12 environment at $VENV_PATH."
  if ! command -v python3.12 >/dev/null 2>&1; then
    echo "Python 3.12 is required but python3.12 was not found." >&2
    exit 1
  fi
  python3.12 -m venv "$VENV_PATH"
  "$VENV_PATH/bin/python" -m pip install --upgrade pip
  "$VENV_PATH/bin/python" -m pip install -r "$SCRIPT_DIR/requirements.txt"
elif [[ ! -f "$VENV_PATH/bin/activate" ]]; then
  echo "Python virtual environment is incomplete at $VENV_PATH." >&2
  exit 1
fi

PYTHON_MINOR="$("$VENV_PATH/bin/python" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if [[ "$PYTHON_MINOR" != "3.12" ]]; then
  echo "Python 3.12 is required; $VENV_PATH uses Python $PYTHON_MINOR." >&2
  exit 1
fi
UVICORN="$VENV_PATH/bin/uvicorn"
if [[ ! -x "$UVICORN" ]]; then
  echo "Uvicorn is not installed in $VENV_PATH." >&2
  exit 1
fi
echo "Using Python $PYTHON_MINOR."

echo "Stopping any existing managed chatbot and Dagster cluster."
bash "$SCRIPT_DIR/stop_app.sh"
find "$LOG_DIR" -type f -name "*.log" -mtime +2 -delete

PGSQL_ARGS=()
if [[ "$RESET_DB" == true ]]; then
  echo "WARNING: --reset-db will delete the existing PostgreSQL data."
  PGSQL_ARGS+=(--reset-db)
fi
bash "$SCRIPT_DIR/dockers/pgsql/start_pgsql_pgvector.sh" "${PGSQL_ARGS[@]}"

if [[ "$SEED_DATA" == true ]]; then
  echo "Loading sample place data."
  bash "$SCRIPT_DIR/start-seeding-data.sh"
fi

process_matches() {
  local pid="$1"
  local first_fragment="$2"
  local second_fragment="$3"
  local command

  command="$(ps -p "$pid" -o args= 2>/dev/null || true)"
  [[ "$command" == *"$first_fragment"* && "$command" == *"$second_fragment"* ]]
}

echo "Starting Dagster cluster on port $DAGSTER_WEB_PORT."
nohup bash "$SCRIPT_DIR/start_dagster.sh" --cluster \
  </dev/null >>"$DAGSTER_MANAGER_LOG" 2>&1 &
DAGSTER_MANAGER_PID=$!
printf '%s\n' "$DAGSTER_MANAGER_PID" >"$DAGSTER_MANAGER_PID_FILE"

DAGSTER_READY=false
for ((attempt = 1; attempt <= DAGSTER_STARTUP_TIMEOUT; attempt++)); do
  if ! kill -0 "$DAGSTER_MANAGER_PID" 2>/dev/null; then
    break
  fi
  if ! process_matches "$DAGSTER_MANAGER_PID" "$SCRIPT_DIR/start_dagster.sh" "--cluster"; then
    sleep 1
    continue
  fi

  WEB_PID=""
  DAEMON_PID=""
  [[ ! -f "$DAGSTER_PID_DIR/webserver.pid" ]] \
    || WEB_PID="$(cat "$DAGSTER_PID_DIR/webserver.pid")"
  [[ ! -f "$DAGSTER_PID_DIR/daemon.pid" ]] \
    || DAEMON_PID="$(cat "$DAGSTER_PID_DIR/daemon.pid")"
  HTTP_STATUS="$(
    curl --silent --output /dev/null --write-out '%{http_code}' \
      --connect-timeout 1 --max-time 2 \
      "http://127.0.0.1:${DAGSTER_WEB_PORT}/" || true
  )"

  if [[ "$HTTP_STATUS" =~ ^[1-5][0-9][0-9]$ ]] \
      && [[ "$WEB_PID" =~ ^[0-9]+$ ]] \
      && process_matches "$WEB_PID" "dagster-webserver" "dags_pipelines" \
      && [[ "$DAEMON_PID" =~ ^[0-9]+$ ]] \
      && process_matches "$DAEMON_PID" "dagster-daemon" "dags_pipelines"; then
    DAGSTER_READY=true
    break
  fi
  sleep 1
done

if [[ "$DAGSTER_READY" != true ]]; then
  echo "Dagster cluster did not become ready within ${DAGSTER_STARTUP_TIMEOUT}s." >&2
  tail -n 40 "$DAGSTER_MANAGER_LOG" >&2 || true
  bash "$SCRIPT_DIR/stop_app.sh" || true
  exit 1
fi
echo "Dagster cluster is ready at http://127.0.0.1:${DAGSTER_WEB_PORT}/."

echo "Starting $APP_NAME on ${HOST}:${PORT}."
UVICORN_ARGS=(
  "$APP_MODULE"
  --host "$HOST"
  --port "$PORT"
  --workers "$WORKERS"
)
if [[ -f "$ENV_FILE" ]]; then
  UVICORN_ARGS+=(--env-file "$ENV_FILE")
fi

nohup "$UVICORN" "${UVICORN_ARGS[@]}" \
  </dev/null >>"$APP_LOG_FILE" 2>&1 &
APP_PID=$!
printf '%s\n' "$APP_PID" >"$APP_PID_FILE"

APP_READY=false
for ((attempt = 1; attempt <= APP_STARTUP_TIMEOUT; attempt++)); do
  if ! kill -0 "$APP_PID" 2>/dev/null; then
    break
  fi
  if ! process_matches "$APP_PID" "uvicorn" "$APP_MODULE"; then
    sleep 1
    continue
  fi

  HTTP_STATUS="$(
    curl --silent --output /dev/null --write-out '%{http_code}' \
      --connect-timeout 1 --max-time 2 \
      "http://127.0.0.1:${PORT}/_leoai/ping" || true
  )"
  if [[ "$HTTP_STATUS" == "200" ]]; then
    APP_READY=true
    break
  fi
  sleep 1
done

if [[ "$APP_READY" != true ]]; then
  echo "$APP_NAME did not become ready within ${APP_STARTUP_TIMEOUT}s." >&2
  tail -n 40 "$APP_LOG_FILE" >&2 || true
  bash "$SCRIPT_DIR/stop_app.sh" || true
  exit 1
fi

echo "$APP_NAME is ready at http://127.0.0.1:${PORT}/."
echo "Chatbot PID: $APP_PID (log: $APP_LOG_FILE)"
echo "Dagster cluster PID: $DAGSTER_MANAGER_PID (log: $DAGSTER_MANAGER_LOG)"
