#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
APP_USER="${LEOBOT_SERVICE_USER:-leocdp}"
STOP_SCRIPT="$SCRIPT_DIR/stop_app.sh"
START_SCRIPT="$SCRIPT_DIR/start_app.sh"
CRON_LOG_DIR="$SCRIPT_DIR/cron-jobs"
CRON_LOG_FILE="$CRON_LOG_DIR/restart.log"

mkdir -p "$CRON_LOG_DIR"

if [[ ! -f "$STOP_SCRIPT" || ! -f "$START_SCRIPT" ]]; then
  echo "Service lifecycle scripts are missing from $SCRIPT_DIR." >&2
  exit 1
fi

if ! id "$APP_USER" >/dev/null 2>&1; then
  echo "Service account '$APP_USER' does not exist." >&2
  exit 1
fi
if ! command -v sudo >/dev/null 2>&1; then
  echo "sudo is required to restart services as '$APP_USER'." >&2
  exit 1
fi

{
  echo "------------------------------------------------------------"
  echo "Restart triggered at: $(date '+%Y-%m-%d %H:%M:%S')"
  echo "Stopping chatbot and Dagster cluster as $APP_USER."
  sudo -u "$APP_USER" bash "$STOP_SCRIPT"
  echo "Starting chatbot and Dagster cluster as $APP_USER."
  sudo -u "$APP_USER" bash "$START_SCRIPT" "$@"
  echo "Restart completed at: $(date '+%Y-%m-%d %H:%M:%S')"
} >>"$CRON_LOG_FILE" 2>&1
