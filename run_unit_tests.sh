#!/usr/bin/env bash
# Run all tests in ./tests: Python (pytest) and JavaScript (node --test *.test.cjs).
# Extra arguments are forwarded to pytest, e.g.:
#   ./run_unit_tests.sh -k nearby -x
#   ./run_unit_tests.sh tests/test_nearby_places.py   (runs only that path)
set -uo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

GREEN="\033[1;32m"
YELLOW="\033[1;33m"
RED="\033[1;31m"
NC="\033[0m"

if [[ -x "env/bin/python" ]]; then
  PYTHON="env/bin/python"
else
  PYTHON="$(command -v python3 || true)"
  if [[ -z "$PYTHON" ]]; then
    echo -e "${RED}❌ No Python found (expected env/bin/python or python3).${NC}"
    exit 1
  fi
  echo -e "${YELLOW}⚠️  env/bin/python not found, using ${PYTHON}.${NC}"
fi

# Run the whole tests/ folder unless a test path was passed explicitly.
PYTEST_TARGET=(tests)
for arg in "$@"; do
  if [[ "$arg" != -* && -e "${arg%%::*}" ]]; then
    PYTEST_TARGET=()
    break
  fi
done

echo -e "${GREEN}🧪 Running Python tests...${NC}"
"$PYTHON" -m pytest "${PYTEST_TARGET[@]}" --continue-on-collection-errors "$@"
PY_STATUS=$?

JS_STATUS=0
shopt -s nullglob
JS_TESTS=(tests/*.test.cjs tests/*.test.js tests/*.test.mjs)
shopt -u nullglob
if [[ ${#JS_TESTS[@]} -gt 0 ]]; then
  if command -v node >/dev/null 2>&1; then
    echo -e "${GREEN}🧪 Running JavaScript tests...${NC}"
    node --test "${JS_TESTS[@]}"
    JS_STATUS=$?
  else
    echo -e "${YELLOW}⚠️  node not found, skipping JavaScript tests.${NC}"
  fi
fi

if [[ $PY_STATUS -eq 0 && $JS_STATUS -eq 0 ]]; then
  echo -e "${GREEN}✅ All tests passed.${NC}"
  exit 0
fi

echo -e "${RED}❌ Tests failed (pytest exit=${PY_STATUS}, node exit=${JS_STATUS}).${NC}"
exit 1
