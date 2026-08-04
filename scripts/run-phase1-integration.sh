#!/usr/bin/env bash

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend"
PYTHON="${BACKEND_DIR}/.venv/bin/python"
POSTGRES_SOCKET_DIR="${ROOT_DIR}/.runtime/postgres/socket"
POSTGRES_PORT="${KNOWAGENT_LOCAL_POSTGRES_PORT:-5440}"
REDIS_PORT="${KNOWAGENT_LOCAL_REDIS_PORT:-6380}"
MINIO_PORT="${KNOWAGENT_LOCAL_MINIO_PORT:-9200}"
MINIO_CONSOLE_PORT="${KNOWAGENT_LOCAL_MINIO_CONSOLE_PORT:-9201}"
MINIO_DATA_DIR="${ROOT_DIR}/.runtime/minio/data"
MINIO_LOG="${ROOT_DIR}/.runtime/phase1-minio.log"
RUN_ID="$(date -u +%Y%m%d%H%M%S)-$$"
DATABASE_NAME="knowagent_integration"
BUCKET_NAME="knowagent-phase1-it"
STARTED_MINIO_PID=""

cleanup() {
  if [[ -n "${STARTED_MINIO_PID}" ]] && kill -0 "${STARTED_MINIO_PID}" 2>/dev/null; then
    kill "${STARTED_MINIO_PID}"
    wait "${STARTED_MINIO_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT

[[ -x "${PYTHON}" ]] || { echo "backend/.venv is missing" >&2; exit 1; }
[[ -f "${BACKEND_DIR}/.env" ]] || { echo "backend/.env is missing" >&2; exit 1; }
[[ "${DATABASE_NAME}" == "knowagent_integration" ]] \
  || { echo "unsafe integration database name" >&2; exit 1; }
[[ "${BUCKET_NAME}" == "knowagent-phase1-it" ]] \
  || { echo "unsafe integration bucket name" >&2; exit 1; }

set -a
# shellcheck disable=SC1091
source "${BACKEND_DIR}/.env"
set +a

[[ "${KNOWAGENT_S3_ENDPOINT_URL}" == "http://127.0.0.1:${MINIO_PORT}" ]] \
  || { echo "acceptance runner only supports the project-local MinIO endpoint" >&2; exit 1; }
psql \
  -h "${POSTGRES_SOCKET_DIR}" \
  -p "${POSTGRES_PORT}" \
  -d postgres \
  -tAc "SELECT 1" | grep -qx 1 \
  || { echo "project-local PostgreSQL is unavailable" >&2; exit 1; }
redis-cli -h 127.0.0.1 -p "${REDIS_PORT}" ping | grep -qx PONG \
  || { echo "project-local Redis is unavailable" >&2; exit 1; }

if ! curl --fail --silent --show-error --max-time 2 \
  "http://127.0.0.1:${MINIO_PORT}/minio/health/live" >/dev/null 2>&1; then
  mkdir -p "${MINIO_DATA_DIR}"
  MINIO_ROOT_USER="${KNOWAGENT_S3_ACCESS_KEY}" \
  MINIO_ROOT_PASSWORD="${KNOWAGENT_S3_SECRET_KEY}" \
    minio server \
      --address "127.0.0.1:${MINIO_PORT}" \
      --console-address "127.0.0.1:${MINIO_CONSOLE_PORT}" \
      "${MINIO_DATA_DIR}" >"${MINIO_LOG}" 2>&1 &
  STARTED_MINIO_PID="$!"
  for _ in {1..30}; do
    curl --fail --silent --show-error --max-time 2 \
      "http://127.0.0.1:${MINIO_PORT}/minio/health/live" >/dev/null 2>&1 && break
    sleep 1
  done
  curl --fail --silent --show-error --max-time 2 \
    "http://127.0.0.1:${MINIO_PORT}/minio/health/live" >/dev/null \
    || { echo "project-local MinIO failed to start; see ${MINIO_LOG}" >&2; exit 1; }
fi

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
  || { echo "acceptance runner only supports the project-local PostgreSQL" >&2; exit 1; }
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
export KNOWAGENT_REDIS_URL=redis://127.0.0.1:6380/15
export KNOWAGENT_REDIS_PREFIX="knowagent:phase1-it:${RUN_ID}"
export KNOWAGENT_SESSION_COOKIE=knowagent_phase1_it_session
export KNOWAGENT_COOKIE_SECURE=false
export KNOWAGENT_S3_BUCKET="${BUCKET_NAME}"
export KNOWAGENT_RUN_PHASE1_ACCEPTANCE=1

(
  cd "${BACKEND_DIR}"
  "${PYTHON}" -m alembic upgrade head
  "${PYTHON}" -m alembic check
  PYTHONPATH=src "${PYTHON}" -m pytest \
    tests/integration/test_phase1_live_acceptance.py \
    -m integration \
    --no-cov \
    -v \
    -s
)
