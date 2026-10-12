#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

ENV_FILE="${LEO_ENV_FILE:-$SCRIPT_DIR/.env}"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

DAGSTER_PID_DIR="${DAGSTER_PID_DIR:-$SCRIPT_DIR/.dagster-pids}"
PID_DIR="${LEOBOT_PID_DIR:-$DAGSTER_PID_DIR}"
APP_MODULE="main_app:leobot"
STOP_FAILED=false

process_matches() {
  local pid="$1"
  local first_fragment="$2"
  local second_fragment="$3"
  local command

  command="$(ps -p "$pid" -o args= 2>/dev/null || true)"
  [[ "$command" == *"$first_fragment"* && "$command" == *"$second_fragment"* ]]
}

stop_pid() {
  local pid="$1"
  local label="$2"
  local first_fragment="$3"
  local second_fragment="$4"

  if [[ ! "$pid" =~ ^[0-9]+$ ]] || ! kill -0 "$pid" 2>/dev/null; then
    return 0
  fi
  if ! process_matches "$pid" "$first_fragment" "$second_fragment"; then
    echo "Refusing to stop unexpected process $pid from $label." >&2
    return 0
  fi

  echo "Stopping $label (PID $pid)."
  kill -TERM "$pid" 2>/dev/null || true
  for _ in {1..15}; do
    if ! kill -0 "$pid" 2>/dev/null || ! process_matches "$pid" "$first_fragment" "$second_fragment"; then
      return 0
    fi
    sleep 1
  done

  if process_matches "$pid" "$first_fragment" "$second_fragment"; then
    echo "$label did not stop gracefully; sending SIGKILL to PID $pid." >&2
    kill -KILL "$pid" 2>/dev/null || true
    for _ in {1..3}; do
      if ! kill -0 "$pid" 2>/dev/null || ! process_matches "$pid" "$first_fragment" "$second_fragment"; then
        return 0
      fi
      sleep 1
    done
    echo "Unable to stop $label (PID $pid)." >&2
    return 1
  fi
}

stop_pid_file() {
  local pid_file="$1"
  local label="$2"
  local first_fragment="$3"
  local second_fragment="$4"
  local pid

  [[ -f "$pid_file" ]] || return 0
  pid="$(cat "$pid_file")"
  if [[ ! "$pid" =~ ^[0-9]+$ ]]; then
    echo "Removing invalid PID file: $pid_file" >&2
    rm -f "$pid_file"
    return 0
  fi

  stop_pid "$pid" "$label" "$first_fragment" "$second_fragment" || STOP_FAILED=true
  rm -f "$pid_file"
}

echo "Stopping chatbot and Dagster cluster."
stop_pid_file "$PID_DIR/chatbot.pid" "LEO chatbot" "uvicorn" "$APP_MODULE"
stop_pid_file \
  "$PID_DIR/dagster-cluster.pid" \
  "Dagster cluster supervisor" \
  "$SCRIPT_DIR/start_dagster.sh" \
  "--cluster"

# The Dagster supervisor normally stops and removes these child PID files itself.
# Stop any remaining children if the supervisor had to be force-terminated.
stop_pid_file \
  "$DAGSTER_PID_DIR/webserver.pid" \
  "Dagster webserver" \
  "dagster-webserver" \
  "dags_pipelines"
stop_pid_file \
  "$DAGSTER_PID_DIR/daemon.pid" \
  "Dagster daemon" \
  "dagster-daemon" \
  "dags_pipelines"

# Clean up matching legacy processes from before PID-file tracking was added.
legacy_chatbot_pids="$(pgrep -f '[u]vicorn.*main_app:leobot' || true)"
if [[ -n "$legacy_chatbot_pids" ]]; then
  while IFS= read -r pid; do
    stop_pid "$pid" "legacy LEO chatbot" "uvicorn" "$APP_MODULE" || STOP_FAILED=true
  done <<< "$legacy_chatbot_pids"
fi

legacy_dagster_pids="$(
  pgrep -f '[d]agster-(webserver|daemon).*dags_pipelines' || true
)"
if [[ -n "$legacy_dagster_pids" ]]; then
  while IFS= read -r pid; do
    process_cwd="$(readlink -f "/proc/$pid/cwd" 2>/dev/null || true)"
    if [[ "$process_cwd" == "$SCRIPT_DIR" ]]; then
      command="$(ps -p "$pid" -o args= 2>/dev/null || true)"
      if [[ "$command" == *"dagster-webserver"* ]]; then
        stop_pid "$pid" "legacy Dagster webserver" "dagster-webserver" "dags_pipelines" || STOP_FAILED=true
      elif [[ "$command" == *"dagster-daemon"* ]]; then
        stop_pid "$pid" "legacy Dagster daemon" "dagster-daemon" "dags_pipelines" || STOP_FAILED=true
      fi
    fi
  done <<< "$legacy_dagster_pids"
fi

if [[ "$STOP_FAILED" == true ]]; then
  echo "One or more managed services could not be stopped." >&2
  exit 1
fi

rm -f "$PID_DIR/chatbot.pid" "$PID_DIR/dagster-cluster.pid"
echo "Chatbot and Dagster cluster stopped. PostgreSQL was left running."
