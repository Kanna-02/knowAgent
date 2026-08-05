#!/usr/bin/env bash

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend"
MODEL_DIR="${ROOT_DIR}/model-service"
PYTHON="${BACKEND_DIR}/.venv/bin/python"
POSTGRES_SOCKET_DIR="${ROOT_DIR}/.runtime/postgres/socket"
POSTGRES_PORT="${KNOWAGENT_LOCAL_POSTGRES_PORT:-5440}"
REDIS_PORT="${KNOWAGENT_LOCAL_REDIS_PORT:-6380}"
DATABASE_NAME="knowagent_integration"
RUN_ID="$(date -u +%Y%m%d%H%M%S)-$$"
MODEL_LOG="${ROOT_DIR}/.runtime/phase2-model-service.log"
STARTED_MODEL_PID=""

cleanup() {
  if [[ -n "${STARTED_MODEL_PID}" ]] && kill -0 "${STARTED_MODEL_PID}" 2>/dev/null; then
    kill "${STARTED_MODEL_PID}"
    wait "${STARTED_MODEL_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT

[[ -x "${PYTHON}" ]] || { echo "backend/.venv is missing" >&2; exit 1; }
[[ -x "${MODEL_DIR}/.venv/bin/knowagent-model-service" ]] \
  || { echo "model-service/.venv is missing" >&2; exit 1; }
[[ -f "${BACKEND_DIR}/.env" ]] || { echo "backend/.env is missing" >&2; exit 1; }
[[ -f "${MODEL_DIR}/.env" ]] || { echo "model-service/.env is missing" >&2; exit 1; }
[[ "${DATABASE_NAME}" == "knowagent_integration" ]] \
  || { echo "unsafe integration database name" >&2; exit 1; }

set -a
# shellcheck disable=SC1091
source "${BACKEND_DIR}/.env"
# shellcheck disable=SC1091
source "${MODEL_DIR}/.env"
set +a

psql \
  -h "${POSTGRES_SOCKET_DIR}" \
  -p "${POSTGRES_PORT}" \
  -d postgres \
  -tAc "SELECT 1" | grep -qx 1 \
  || { echo "project-local PostgreSQL is unavailable" >&2; exit 1; }
redis-cli -h 127.0.0.1 -p "${REDIS_PORT}" ping | grep -qx PONG \
  || { echo "project-local Redis is unavailable" >&2; exit 1; }
curl --fail --silent --show-error --max-time 5 \
  "${KNOWAGENT_MODEL_OLLAMA_BASE_URL}/api/tags" >/dev/null \
  || { echo "Ollama is unavailable" >&2; exit 1; }

DATABASE_PARTS="$(
  "${PYTHON}" -c '
import os
from sqlalchemy.engine import make_url

url = make_url(os.environ["KNOWAGENT_DATABASE_URL"])
print("|".join((url.username or "", url.host or "", str(url.port or 5432))))
'
)"
IFS='|' read -r DATABASE_USER DATABASE_HOST DATABASE_CONFIGURED_PORT <<<"${DATABASE_PARTS}"
[[ "${DATABASE_HOST}" == "127.0.0.1" && "${DATABASE_CONFIGURED_PORT}" == "${POSTGRES_PORT}" ]] \
  || { echo "integration runner only supports project-local PostgreSQL" >&2; exit 1; }
[[ "${DATABASE_USER}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] \
  || { echo "unsafe database owner" >&2; exit 1; }

if ! psql \
  -h "${POSTGRES_SOCKET_DIR}" \
  -p "${POSTGRES_PORT}" \
  -d postgres \
  -tAc "SELECT 1 FROM pg_database WHERE datname = '${DATABASE_NAME}'" | grep -qx 1; then
  createdb \
    -h "${POSTGRES_SOCKET_DIR}" \
    -p "${POSTGRES_PORT}" \
    -O "${DATABASE_USER}" \
    "${DATABASE_NAME}"
fi

psql \
  -h "${POSTGRES_SOCKET_DIR}" \
  -p "${POSTGRES_PORT}" \
  -d "${DATABASE_NAME}" \
  -v ON_ERROR_STOP=1 \
  -c "CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS pg_trgm;" \
  >/dev/null

export KNOWAGENT_DATABASE_URL="$(
  "${PYTHON}" -c '
import os
import sys
from sqlalchemy.engine import make_url

print(make_url(os.environ["KNOWAGENT_DATABASE_URL"]).set(database=sys.argv[1]).render_as_string(hide_password=False))
' "${DATABASE_NAME}"
)"
export KNOWAGENT_ENVIRONMENT=integration
export KNOWAGENT_REDIS_URL="redis://127.0.0.1:${REDIS_PORT}/15"
export KNOWAGENT_REDIS_PREFIX="knowagent:phase2-it:${RUN_ID}"
export KNOWAGENT_EMBEDDING_API_BASE="http://127.0.0.1:8100/v1"
export KNOWAGENT_EMBEDDING_TIMEOUT_SECONDS=300
export KNOWAGENT_RUN_PHASE2_INTEGRATION=1
export KNOWAGENT_RUN_API_INTEGRATION=1
export KNOWAGENT_API_INTEGRATION_DATABASE_URL="${KNOWAGENT_DATABASE_URL}"
if [[ "${1:-}" == "--with-llm" ]]; then
  export KNOWAGENT_RUN_PHASE2_LLM_INTEGRATION=1
elif [[ -n "${1:-}" ]]; then
  echo "usage: $0 [--with-llm]" >&2
  exit 2
fi

if ! curl --fail --silent --show-error --max-time 5 \
  "http://127.0.0.1:8100/health/ready" >/dev/null 2>&1; then
  mkdir -p "${ROOT_DIR}/.runtime"
  (
    cd "${MODEL_DIR}"
    "${MODEL_DIR}/.venv/bin/knowagent-model-service" >"${MODEL_LOG}" 2>&1 &
    echo "$!"
  ) >"${ROOT_DIR}/.runtime/phase2-model-service.pid"
  STARTED_MODEL_PID="$(<"${ROOT_DIR}/.runtime/phase2-model-service.pid")"
  for _ in {1..60}; do
    curl --fail --silent --show-error --max-time 5 \
      "http://127.0.0.1:8100/health/ready" >/dev/null 2>&1 && break
    sleep 1
  done
  curl --fail --silent --show-error --max-time 5 \
    "http://127.0.0.1:8100/health/ready" >/dev/null \
    || { echo "model-service failed to start; see ${MODEL_LOG}" >&2; exit 1; }
fi

(
  cd "${BACKEND_DIR}"
  "${PYTHON}" -m alembic upgrade head
  "${PYTHON}" -m alembic check
  PYTHONPATH=src "${PYTHON}" -m pytest \
    tests/integration/test_phase2_live_integration.py \
    tests/integration/test_agent_api.py \
    tests/integration/test_tickets_api.py \
    -m integration \
    --no-cov \
    -v \
    -s
)
