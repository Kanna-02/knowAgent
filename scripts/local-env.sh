#!/usr/bin/env bash

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="${ROOT_DIR}/.runtime"
POSTGRES_DIR="${RUNTIME_DIR}/postgres"
POSTGRES_DATA_DIR="${POSTGRES_DIR}/data"
POSTGRES_SOCKET_DIR="${POSTGRES_DIR}/socket"
POSTGRES_HOST="127.0.0.1"
POSTGRES_PORT="${KNOWAGENT_LOCAL_POSTGRES_PORT:-5440}"
REDIS_DIR="${RUNTIME_DIR}/redis"
REDIS_HOST="127.0.0.1"
REDIS_PORT="${KNOWAGENT_LOCAL_REDIS_PORT:-6380}"
MINIO_DIR="${RUNTIME_DIR}/minio"
MINIO_DATA_DIR="${MINIO_DIR}/data"
MINIO_PORT="${KNOWAGENT_LOCAL_MINIO_PORT:-9200}"
MINIO_CONSOLE_PORT="${KNOWAGENT_LOCAL_MINIO_CONSOLE_PORT:-9201}"
API_PORT="${KNOWAGENT_LOCAL_API_PORT:-8200}"
FRONTEND_PORT="${KNOWAGENT_LOCAL_FRONTEND_PORT:-5273}"

mkdir -p \
  "${RUNTIME_DIR}" \
  "${POSTGRES_DIR}" \
  "${POSTGRES_SOCKET_DIR}" \
  "${REDIS_DIR}" \
  "${MINIO_DATA_DIR}"

log() {
  printf '[knowagent] %s\n' "$*"
}

fail() {
  printf '[knowagent] error: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "required command not found: $1"
}

load_environment() {
  [[ -f "${ROOT_DIR}/backend/.env" ]] || fail "backend/.env is missing"
  [[ -f "${ROOT_DIR}/model-service/.env" ]] || fail "model-service/.env is missing"

  set -a
  # shellcheck disable=SC1091
  source "${ROOT_DIR}/backend/.env"
  # shellcheck disable=SC1091
  source "${ROOT_DIR}/model-service/.env"
  set +a

  export PYTHONPATH="${ROOT_DIR}/backend/src"
  export VITE_API_PROXY_TARGET="http://127.0.0.1:${API_PORT}"
}

load_database_settings() {
  local database_parts
  database_parts="$(
    "${ROOT_DIR}/backend/.venv/bin/python" -c '
import os
from sqlalchemy.engine import make_url

url = make_url(os.environ["KNOWAGENT_DATABASE_URL"])
print("|".join((url.username or "", url.password or "", url.database or "", url.host or "", str(url.port or 5432))))
'
  )"
  IFS='|' read -r DATABASE_USER DATABASE_PASSWORD DATABASE_NAME DATABASE_HOST DATABASE_PORT \
    <<<"${database_parts}"

  [[ "${DATABASE_USER}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] \
    || fail "database user must be a simple PostgreSQL identifier"
  [[ "${DATABASE_NAME}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] \
    || fail "database name must be a simple PostgreSQL identifier"
  [[ "${DATABASE_HOST}" == "${POSTGRES_HOST}" ]] \
    || fail "KNOWAGENT_DATABASE_URL must use ${POSTGRES_HOST} for local runtime"
  [[ "${DATABASE_PORT}" == "${POSTGRES_PORT}" ]] \
    || fail "KNOWAGENT_DATABASE_URL must use project PostgreSQL port ${POSTGRES_PORT}"
  [[ -n "${DATABASE_PASSWORD}" ]] || fail "database password must not be empty"
}

pid_running() {
  local pid_file="$1"
  local start_file="${pid_file}.start"
  [[ -f "${pid_file}" && -f "${start_file}" ]] || return 1
  local pid
  pid="$(<"${pid_file}")"
  [[ "${pid}" =~ ^[0-9]+$ ]] || return 1
  kill -0 "${pid}" 2>/dev/null || return 1

  local expected_start actual_start
  expected_start="$(<"${start_file}")"
  actual_start="$(ps -p "${pid}" -o lstart= 2>/dev/null)"
  [[ -n "${actual_start}" && "${actual_start}" == "${expected_start}" ]]
}

remember_process_identity() {
  local pid_file="$1"
  [[ -f "${pid_file}" ]] || return 1
  local pid process_start
  pid="$(<"${pid_file}")"
  [[ "${pid}" =~ ^[0-9]+$ ]] || return 1
  kill -0 "${pid}" 2>/dev/null || return 1
  process_start="$(ps -p "${pid}" -o lstart= 2>/dev/null)"
  [[ -n "${process_start}" ]] || return 1
  printf '%s\n' "${process_start}" >"${pid_file}.start"
}

start_process() {
  local name="$1"
  local work_dir="$2"
  shift 2

  local pid_file="${RUNTIME_DIR}/${name}.pid"
  local log_file="${RUNTIME_DIR}/${name}.log"
  if pid_running "${pid_file}"; then
    log "${name} already running (pid $(<"${pid_file}"))"
    return
  fi
  rm -f "${pid_file}" "${pid_file}.start"

  (
    cd "${work_dir}"
    nohup "$@" >"${log_file}" 2>&1 &
    echo "$!" >"${pid_file}"
  )
  sleep 1
  remember_process_identity "${pid_file}" \
    || fail "${name} process identity could not be recorded; see ${log_file}"
  pid_running "${pid_file}" || fail "${name} failed to start; see ${log_file}"
  log "started ${name} (pid $(<"${pid_file}"))"
}

stop_process() {
  local name="$1"
  local pid_file="${RUNTIME_DIR}/${name}.pid"
  if ! pid_running "${pid_file}"; then
    rm -f "${pid_file}" "${pid_file}.start"
    log "${name} is not running"
    return
  fi

  local pid
  pid="$(<"${pid_file}")"
  kill "${pid}"
  for _ in {1..20}; do
    kill -0 "${pid}" 2>/dev/null || break
    sleep 0.25
  done
  if kill -0 "${pid}" 2>/dev/null; then
    kill -KILL "${pid}"
  fi
  rm -f "${pid_file}" "${pid_file}.start"
  log "stopped ${name}"
}

wait_for_url() {
  local name="$1"
  local url="$2"
  for _ in {1..30}; do
    if curl --fail --silent --show-error --max-time 5 "${url}" >/dev/null 2>&1; then
      log "${name} is ready: ${url}"
      return
    fi
    sleep 1
  done
  fail "${name} did not become ready: ${url}"
}

start_postgres() {
  if [[ ! -f "${POSTGRES_DATA_DIR}/PG_VERSION" ]]; then
    log "initializing project PostgreSQL data directory"
    initdb \
      -D "${POSTGRES_DATA_DIR}" \
      --encoding=UTF8 \
      --locale=en_US.UTF-8 \
      --auth-local=trust \
      --auth-host=scram-sha-256 >/dev/null
  fi

  if pg_ctl -D "${POSTGRES_DATA_DIR}" status >/dev/null 2>&1; then
    log "project PostgreSQL already running on ${POSTGRES_HOST}:${POSTGRES_PORT}"
  else
    pg_ctl \
      -D "${POSTGRES_DATA_DIR}" \
      -l "${POSTGRES_DIR}/postgres.log" \
      -o "-h ${POSTGRES_HOST} -p ${POSTGRES_PORT} -k ${POSTGRES_SOCKET_DIR}" \
      -w start >/dev/null
    log "started project PostgreSQL on ${POSTGRES_HOST}:${POSTGRES_PORT}"
  fi

  local escaped_password
  escaped_password="${DATABASE_PASSWORD//\'/\'\'}"
  if ! psql -h "${POSTGRES_SOCKET_DIR}" -p "${POSTGRES_PORT}" -d postgres \
    -tAc "SELECT 1 FROM pg_roles WHERE rolname = '${DATABASE_USER}'" | grep -qx 1; then
    psql -h "${POSTGRES_SOCKET_DIR}" -p "${POSTGRES_PORT}" -d postgres \
      -v ON_ERROR_STOP=1 <<SQL >/dev/null
CREATE ROLE "${DATABASE_USER}" WITH LOGIN PASSWORD '${escaped_password}';
SQL
  else
    psql -h "${POSTGRES_SOCKET_DIR}" -p "${POSTGRES_PORT}" -d postgres \
      -v ON_ERROR_STOP=1 <<SQL >/dev/null
ALTER ROLE "${DATABASE_USER}" WITH LOGIN PASSWORD '${escaped_password}';
SQL
  fi

  if ! psql -h "${POSTGRES_SOCKET_DIR}" -p "${POSTGRES_PORT}" -d postgres \
    -tAc "SELECT 1 FROM pg_database WHERE datname = '${DATABASE_NAME}'" | grep -qx 1; then
    createdb -h "${POSTGRES_SOCKET_DIR}" -p "${POSTGRES_PORT}" \
      -O "${DATABASE_USER}" "${DATABASE_NAME}"
  fi

  psql -h "${POSTGRES_SOCKET_DIR}" -p "${POSTGRES_PORT}" -d "${DATABASE_NAME}" \
    -v ON_ERROR_STOP=1 \
    -c "CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS pg_trgm;" \
    >/dev/null
}

stop_postgres() {
  if pg_ctl -D "${POSTGRES_DATA_DIR}" status >/dev/null 2>&1; then
    pg_ctl -D "${POSTGRES_DATA_DIR}" -m fast -w stop >/dev/null
    log "stopped project PostgreSQL"
  else
    log "project PostgreSQL is not running"
  fi
}

start_redis() {
  if redis-cli -h "${REDIS_HOST}" -p "${REDIS_PORT}" ping 2>/dev/null | grep -qx PONG; then
    if pid_running "${RUNTIME_DIR}/redis.pid"; then
      log "project Redis already running on ${REDIS_HOST}:${REDIS_PORT}"
      return
    fi
    fail "Redis port ${REDIS_PORT} is occupied by an unmanaged process"
  fi

  redis-server \
    --bind "${REDIS_HOST}" \
    --port "${REDIS_PORT}" \
    --protected-mode yes \
    --daemonize yes \
    --pidfile "${RUNTIME_DIR}/redis.pid" \
    --dir "${REDIS_DIR}" \
    --dbfilename dump.rdb \
    --appendonly yes \
    --appenddirname appendonlydir \
    --logfile "${RUNTIME_DIR}/redis.log"

  for _ in {1..20}; do
    if redis-cli -h "${REDIS_HOST}" -p "${REDIS_PORT}" ping 2>/dev/null | grep -qx PONG; then
      remember_process_identity "${RUNTIME_DIR}/redis.pid" \
        || fail "Redis process identity could not be recorded"
      log "started project Redis on ${REDIS_HOST}:${REDIS_PORT}"
      return
    fi
    sleep 0.25
  done
  fail "project Redis failed to start; see ${RUNTIME_DIR}/redis.log"
}

stop_redis() {
  if pid_running "${RUNTIME_DIR}/redis.pid"; then
    redis-cli -h "${REDIS_HOST}" -p "${REDIS_PORT}" shutdown save >/dev/null
    log "stopped project Redis"
  else
    log "project Redis is not running"
  fi
  rm -f "${RUNTIME_DIR}/redis.pid" "${RUNTIME_DIR}/redis.pid.start"
}

ensure_minio_bucket() {
  "${ROOT_DIR}/backend/.venv/bin/python" -c '
import os

import boto3

client = boto3.client(
    "s3",
    endpoint_url=os.environ["KNOWAGENT_S3_ENDPOINT_URL"],
    region_name=os.environ["KNOWAGENT_S3_REGION"],
    aws_access_key_id=os.environ["KNOWAGENT_S3_ACCESS_KEY"],
    aws_secret_access_key=os.environ["KNOWAGENT_S3_SECRET_KEY"],
)
bucket = os.environ["KNOWAGENT_S3_BUCKET"]
if bucket not in {item["Name"] for item in client.list_buckets()["Buckets"]}:
    client.create_bucket(Bucket=bucket)
'
}

start_minio() {
  local health_url="http://127.0.0.1:${MINIO_PORT}/minio/health/live"
  if curl --fail --silent --show-error --max-time 5 "${health_url}" >/dev/null 2>&1; then
    if pid_running "${RUNTIME_DIR}/minio.pid"; then
      log "project MinIO already running on 127.0.0.1:${MINIO_PORT}"
      ensure_minio_bucket
      return
    fi
    fail "MinIO port ${MINIO_PORT} is occupied by an unmanaged process"
  fi

  start_process minio "${ROOT_DIR}" \
    env \
    MINIO_ROOT_USER="${KNOWAGENT_S3_ACCESS_KEY}" \
    MINIO_ROOT_PASSWORD="${KNOWAGENT_S3_SECRET_KEY}" \
    minio server \
    --address "127.0.0.1:${MINIO_PORT}" \
    --console-address "127.0.0.1:${MINIO_CONSOLE_PORT}" \
    "${MINIO_DATA_DIR}"
  wait_for_url MinIO "${health_url}"
  ensure_minio_bucket
  log "MinIO bucket ready: ${KNOWAGENT_S3_BUCKET}"
}

check_database() {
  PGPASSWORD="${DATABASE_PASSWORD}" \
    psql -h "${DATABASE_HOST}" -p "${DATABASE_PORT}" \
    -U "${DATABASE_USER}" -d "${DATABASE_NAME}" -tAc "SELECT 1" \
    | grep -qx 1 \
    || fail "project PostgreSQL is not ready on ${DATABASE_HOST}:${DATABASE_PORT}"
}

migrate_database() {
  log "applying database migrations"
  (
    cd "${ROOT_DIR}/backend"
    "${ROOT_DIR}/backend/.venv/bin/python" -m alembic upgrade head
  )
}

start_all() {
  require_command curl
  require_command createdb
  require_command initdb
  require_command pg_ctl
  require_command psql
  require_command redis-cli
  require_command redis-server
  require_command npm
  require_command minio
  require_command ollama
  require_command ps
  [[ -x "${ROOT_DIR}/backend/.venv/bin/python" ]] || fail "backend/.venv is missing"
  [[ -x "${ROOT_DIR}/model-service/.venv/bin/knowagent-model-service" ]] || fail "model-service/.venv is missing"
  [[ -d "${ROOT_DIR}/frontend/node_modules" ]] || fail "frontend dependencies are missing; run npm ci"

  load_environment
  load_database_settings
  start_postgres
  check_database
  start_redis
  start_minio
  migrate_database

  [[ "$(uname -s)" == "Darwin" ]] || fail "local Ollama runtime must run on macOS"
  [[ "${KNOWAGENT_MODEL_OLLAMA_BASE_URL}" == "http://127.0.0.1:11434" ]] \
    || fail "KNOWAGENT_MODEL_OLLAMA_BASE_URL must be http://127.0.0.1:11434 for macOS local runtime"
  curl --fail --silent --show-error --max-time 5 \
    "http://127.0.0.1:11434/api/tags" >/dev/null \
    || fail "Ollama is not reachable at http://127.0.0.1:11434; start it with 'ollama serve'"

  start_process model-service "${ROOT_DIR}/model-service" \
    "${ROOT_DIR}/model-service/.venv/bin/knowagent-model-service"
  wait_for_url model-service "http://127.0.0.1:8100/health/ready"

  start_process backend "${ROOT_DIR}/backend" \
    "${ROOT_DIR}/backend/.venv/bin/python" -m uvicorn \
    knowagent.api.app:app --host 127.0.0.1 --port "${API_PORT}"
  wait_for_url backend "http://127.0.0.1:${API_PORT}/health/live"

  start_process celery-worker "${ROOT_DIR}/backend" \
    "${ROOT_DIR}/backend/.venv/bin/celery" \
    -A knowagent.worker.celery_app:celery_app worker \
    --loglevel=INFO --queues=ingestion,notification --hostname=knowagent-worker@%h

  start_process celery-beat "${ROOT_DIR}/backend" \
    "${ROOT_DIR}/backend/.venv/bin/celery" \
    -A knowagent.worker.celery_app:celery_app beat \
    --loglevel=INFO \
    --pidfile="${RUNTIME_DIR}/celery-beat-state.pid" \
    --schedule="${RUNTIME_DIR}/celerybeat-schedule"

  start_process frontend "${ROOT_DIR}/frontend" \
    npm run dev -- --host 127.0.0.1 --port "${FRONTEND_PORT}" --strictPort
  wait_for_url frontend "http://127.0.0.1:${FRONTEND_PORT}/login"

  log "local environment is ready"
  log "frontend: http://127.0.0.1:${FRONTEND_PORT}"
  log "api: http://127.0.0.1:${API_PORT}"
  log "model-service: http://127.0.0.1:8100"
}

stop_all() {
  stop_process frontend
  stop_process celery-beat
  stop_process celery-worker
  stop_process backend
  stop_process model-service
  stop_process minio
  stop_redis
  stop_postgres
}

serve_all() {
  trap stop_all EXIT
  trap 'exit 0' INT TERM
  start_all
  log "foreground supervisor active; press Ctrl+C to stop"
  while true; do
    sleep 3600
  done
}

status_all() {
  load_environment
  load_database_settings
  local failed=0

  if pg_ctl -D "${POSTGRES_DATA_DIR}" status >/dev/null 2>&1 \
    && PGPASSWORD="${DATABASE_PASSWORD}" \
      psql -h "${DATABASE_HOST}" -p "${DATABASE_PORT}" \
      -U "${DATABASE_USER}" -d "${DATABASE_NAME}" -tAc "SELECT 1" \
      | grep -qx 1; then
    log "project PostgreSQL ready on ${POSTGRES_HOST}:${POSTGRES_PORT}"
  else
    log "PostgreSQL unavailable"
    failed=1
  fi

  if redis-cli -h "${REDIS_HOST}" -p "${REDIS_PORT}" ping 2>/dev/null | grep -qx PONG; then
    log "project Redis ready on ${REDIS_HOST}:${REDIS_PORT}"
  else
    log "project Redis unavailable"
    failed=1
  fi

  for item in minio model-service backend celery-worker celery-beat frontend; do
    if pid_running "${RUNTIME_DIR}/${item}.pid"; then
      log "${item} running (pid $(<"${RUNTIME_DIR}/${item}.pid"))"
    else
      log "${item} stopped"
      failed=1
    fi
  done

  curl --fail --silent --show-error --max-time 5 \
    "http://127.0.0.1:${API_PORT}/health/live" >/dev/null 2>&1 \
    || failed=1
  curl --fail --silent --show-error --max-time 5 \
    "http://127.0.0.1:8100/health/ready" >/dev/null 2>&1 \
    || failed=1
  curl --fail --silent --show-error --max-time 5 \
    "http://127.0.0.1:${FRONTEND_PORT}/login" >/dev/null 2>&1 \
    || failed=1
  curl --fail --silent --show-error --max-time 5 \
    "http://127.0.0.1:${MINIO_PORT}/minio/health/live" >/dev/null 2>&1 \
    || failed=1

  return "${failed}"
}

show_logs() {
  local service="${1:-}"
  if [[ -n "${service}" ]]; then
    local log_file="${RUNTIME_DIR}/${service}.log"
    [[ -f "${log_file}" ]] || fail "unknown or missing log: ${service}"
    tail -n 100 "${log_file}"
    return
  fi
  for log_file in "${RUNTIME_DIR}"/*.log; do
    [[ -e "${log_file}" ]] || continue
    printf '\n[%s]\n' "$(basename "${log_file}")"
    tail -n 30 "${log_file}"
  done
}

usage() {
  printf 'Usage: %s {start|serve|stop|restart|status|migrate|logs [service]}\n' "$0"
}

main() {
  case "${1:-}" in
    start)
      start_all
      ;;
    serve)
      serve_all
      ;;
    stop)
      stop_all
      ;;
    restart)
      stop_all
      start_all
      ;;
    status)
      status_all
      ;;
    migrate)
      load_environment
      load_database_settings
      start_postgres
      check_database
      migrate_database
      ;;
    logs)
      show_logs "${2:-}"
      ;;
    *)
      usage
      return 2
      ;;
  esac
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
