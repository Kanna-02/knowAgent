# 本地开发

## 1. 前置条件

- Python 3.11.x；后端依赖以 `backend/pyproject.toml` 的 `[project]` 和 `[project.optional-dependencies.dev]` 为准。
- Node.js 24.x；只用于前端安装、测试和构建。
- PostgreSQL 16+ 测试实例，服务端必须能加载 `vector` 与 `pg_trgm` 扩展。
- Redis 7 测试实例，用于 Session、Celery broker 和恢复调度。
- 数据库迁移账号必须具有目标 Schema 建表/索引权限，以及 `CREATE EXTENSION vector`、`CREATE EXTENSION pg_trgm` 权限；若扩展由 DBA 预装，应用账号不需要扩展创建权限。
- 一个可访问的 Ollama 服务和已加载的 `bge-m3`；仓库内 `model-service` 将其适配为主应用使用的 `POST /v1/embeddings` 契约。本机可复用 `knowledge-rag` 的 `deploy_ollama-models` volume，生产环境不以 Docker 为前提。
- Qwen OpenAI 兼容 API 的完整 Key、Base URL 和模型名；没有 Key 时可运行关键词/向量之外的单测，但不能完成真实回答生成。

本地 HTTP 调试可设置 `KNOWAGENT_COOKIE_SECURE=false`；类生产和生产环境必须使用 HTTPS，并保持 `true`。

### macOS 本地环境基线

当前 macOS 开发基线使用 Homebrew PostgreSQL 17 二进制，并由统一入口在 `.runtime/postgres` 初始化项目独立数据目录，监听 `127.0.0.1:5440`。Homebrew `pgvector` 必须与 PostgreSQL 主版本匹配；本机已验证 PostgreSQL 17.10 可加载 `vector 0.8.6` 和 `pg_trgm 1.6`。不要把数据库建在其他项目的 PostgreSQL 容器中，也不要复用按阶段命名的临时验收库。

项目自己的 Redis 监听 `127.0.0.1:6380`，MinIO S3 API/控制台监听 `127.0.0.1:9200/9201`，数据、PID 和日志保存在仓库忽略的 `.runtime/`。这样即使其他项目占用标准端口，KnowAgent 的 Session、Celery broker 和文档对象仍保持独立。

首次安装本地二进制：

```bash
brew install postgresql@17 pgvector redis minio
```

复制并填写两个 `.env` 后，使用仓库统一入口管理本地进程：

```bash
./scripts/local-env.sh start
./scripts/local-env.sh serve
./scripts/local-env.sh status
./scripts/local-env.sh logs backend
./scripts/local-env.sh stop
```

`start` 会初始化并启动项目独立 PostgreSQL `5440`、Redis `6380` 和 MinIO `9200/9201`，自动创建 `knowagent-dev` Bucket，检查 Ollama、执行 `alembic upgrade head`，再启动 model-service、API `8200`、Celery Worker、Celery Beat 和 Vite 前端 `5273`。Vite 使用严格端口并通过 `VITE_API_PROXY_TARGET` 自动代理到项目 API。普通终端可使用 `start` 后台运行；需要由当前终端持续托管进程时使用 `serve`，按 `Ctrl+C` 会统一停止。`stop` 会同时校验 `.runtime/` 中的 PID 和进程启动时间，只停止本次脚本启动的 KnowAgent 进程；过期或已被复用的 PID 记录只会被清理，不会向无关进程发送信号。单独执行迁移使用 `./scripts/local-env.sh migrate`。

## 2. 后端

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

macOS/Linux 对应命令是 `cp .env.example .env`。`.env` 是隐藏文件，在 Finder 默认不可见；可在 `backend` 目录执行 `ls -la .env` 查看。本仓库已忽略该文件，禁止把真实 Key 提交到 Git。

依赖只需安装到项目持久目录 `backend/.venv` 一次；后续测试直接复用该环境。不要使用 `pip install --target /tmp/...` 作为常规测试方式，否则临时目录清理后会再次下载依赖。

将 `.env` 中的数据库、Redis、S3、Embedding 和 LLM 配置改为本地测试值，再把变量加载到当前终端。应用不会自动读取 `.env`；可使用公司统一的环境加载方式，或在 macOS/Linux 的 `zsh` 中执行 `set -a; source .env; set +a`。兼容用户现有的 `LLM_API_BASE`、`LLM_API_KEY`、`LLM_MODEL`，项目前缀变量 `KNOWAGENT_LLM_*` 优先。

Phase 2 关键变量：

| 变量 | 是否必需 | 说明 |
| --- | --- | --- |
| `KNOWAGENT_DATABASE_URL` | 是 | 必须指向安装 `vector`/`pg_trgm` 的 PostgreSQL；SQLite 仅用于单测和迁移语法检查 |
| `KNOWAGENT_EMBEDDING_API_BASE` | 向量链路必需 | 默认 `http://127.0.0.1:8100/v1` |
| `KNOWAGENT_EMBEDDING_MODEL` | 向量链路必需 | 默认 `bge-m3`；响应模型名必须一致 |
| `KNOWAGENT_EMBEDDING_TIMEOUT_SECONDS` | 否 | 默认 15 秒 |
| `KNOWAGENT_EMBEDDING_BATCH_SIZE` | 否 | 索引批大小，默认 32 |
| `KNOWAGENT_RETRIEVAL_*` | 否 | 关键词/向量/result top-k 与 RRF 参数 |
| `KNOWAGENT_EVIDENCE_MAX_*` | 否 | 证据条数和字符预算 |
| `KNOWAGENT_EVIDENCE_POLICY_VERSION` | 否 | 证据判定策略版本，默认 `evidence-v1` |
| `KNOWAGENT_EVIDENCE_MIN_FUSED_SCORE` / `KNOWAGENT_EVIDENCE_MIN_SCORE_GAP` | 否 | 最低融合分数和头部候选最小差值；必须为非负数 |
| `KNOWAGENT_EVIDENCE_DEGRADED_SCORE_MULTIPLIER` | 否 | 向量等检索通道降级时的阈值倍率，必须不小于 1 |
| `KNOWAGENT_TICKET_DEDUPLICATION_WINDOW_HOURS` | 否 | 同系统规范化问题的自动工单合并时间窗，默认 24 小时 |
| `KNOWAGENT_LLM_API_BASE` / `LLM_API_BASE` | 生成链路必需 | Qwen OpenAI 兼容 `/v1` Base URL |
| `KNOWAGENT_LLM_API_KEY` / `LLM_API_KEY` | 生成链路必需 | 只放本地 `.env` 或密钥设施；不能使用 `sk-` 占位值 |
| `KNOWAGENT_LLM_MODEL` / `LLM_MODEL` | 生成链路必需 | 当前测试目标为 `qwen3.6-plus` |
| `KNOWAGENT_LLM_PROMPT_VERSION` | 生成链路必需 | 默认 `grounded-answer-v1`；必须对应随包发布且启用的 Prompt 资源 |

对象存储使用 `KNOWAGENT_S3_*` 环境变量。至少配置 endpoint、bucket、region、access key 和 secret key；内部 CA 使用 `KNOWAGENT_S3_CA_BUNDLE`，不得通过关闭 TLS 校验绕过证书问题。`KNOWAGENT_S3_VERIFY_TLS` 和 `KNOWAGENT_COOKIE_SECURE` 只接受明确的 `true/false`、`yes/no`、`on/off` 或 `1/0`，拼写错误会让应用启动失败。连接/读取超时、SDK 重试次数和 multipart 阈值/分片大小均可配置，凭据只能由环境或公司密钥设施提供。

文档解析和切分参数统一使用 `KNOWAGENT_DOCUMENT_*` 环境变量。默认值已列在 `backend/.env.example`，包括上传字节数、Office 展开大小/压缩比/归档条目数、PDF 页数与块数、Word/Markdown 块数、Excel 工作表/行/列/单元格上限，以及 chunk token 预算和块重叠数。所有上限必须为正整数，只有 `KNOWAGENT_DOCUMENT_CHUNK_OVERLAP_BLOCKS` 可以为 `0`；无效值会在配置加载时失败，不应在生产环境静默回退。

parser 是同步的 CPU/内存密集端口，只能由独立文档 worker 调用，不得直接放入 FastAPI `async` 请求链。`KNOWAGENT_INGESTION_*` 配置任务最大尝试次数、租约、退避、派发超时、恢复批大小和 Celery 软/硬超时；硬超时必须大于软超时，租约必须大于硬超时。Worker 每次写状态都校验 owner、attempt 和租约有效期，过期执行只记录告警，不覆盖已被重新领取的任务。

应用数据库迁移并启动 API：

```powershell
alembic upgrade head
uvicorn knowagent.api.app:app --reload --host 127.0.0.1 --port 8000
```

迁移 `3ba86a4c3d35` 会从 `documents.system_id` 回填已有 `document_versions.system_id`，为入库任务增加原始父文档请求指纹，再收紧版本隔离与当前发布指针复合外键，并创建 `knowledge_sources`、`knowledge_chunks`。应用迁移前需备份目标 Schema；不得跳过回填直接手工加 `NOT NULL`。

迁移 `c8784d439b23` 在 PostgreSQL 上创建 `vector`、`pg_trgm` 扩展，增加 `knowledge_chunks.embedding` 和 `retrieval_text` GIN trigram 索引。可先确认扩展可用：

```sql
SELECT extname, extversion FROM pg_extension WHERE extname IN ('vector', 'pg_trgm');
```

当前向量列不固定维度，因此可以保存 Provider 返回的模型维度，但暂不创建 HNSW。模型和维度最终确认后再通过独立迁移增加固定维度/HNSW，并用类生产数据验证查询计划。

迁移 `cc99b700f739` 创建 `evidence_decisions` 和 `tickets`，保存策略版本、拒答原因、候选证据摘要及自动工单关联，并建立系统/判定结果和系统/工单状态索引。应用该迁移前必须先完成备份，并在隔离数据库验证 `upgrade`/`downgrade` 往返和 `alembic check`。

健康检查：`GET http://127.0.0.1:8000/health/live`。

另开终端启动入库 Worker 和恢复调度器；两者与 API 使用同一组数据库、Redis 和对象存储环境变量：

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
celery -A knowagent.worker.celery_app:celery_app worker --loglevel=INFO --queues=ingestion
```

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
celery -A knowagent.worker.celery_app:celery_app beat --loglevel=INFO
```

Celery 消息只携带 `job_id`；业务状态以 PostgreSQL 为准。Beat 定期恢复未派发任务、到期重试和租约过期任务，不能用 Celery result backend 判断入库是否完成。

## 3. Embedding 模型服务

本机已有 Docker volume `deploy_ollama-models`，其中 `bge-m3` 模型层约 1.158 GB。仅用于本地联调时，可从 `knowledge-rag/deploy` 恢复 Ollama 容器；Compose 会复用同名 volume，不重新下载模型权重：

```bash
docker compose -f ../knowledge-rag/deploy/docker-compose.yml up -d ollama
```

安装并启动适配层：

```bash
cd model-service
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
cp .env.example .env
set -a
source .env
set +a
knowagent-model-service
```

Windows 使用 `py -3.11 -m venv .venv`、`.\.venv\Scripts\Activate.ps1` 和 `$env:` 形式加载变量。适配层默认监听 `127.0.0.1:8100`，Ollama 地址为 `127.0.0.1:11434`。验证：

`.env` 中的 `KNOWAGENT_MODEL_OLLAMA_MODEL_DIGEST` 必须是 Ollama `/api/tags` 返回 digest 的 8-64 位十六进制前缀，`KNOWAGENT_MODEL_EMBEDDING_VERSION` 必须以同一前缀结尾。服务会在 readiness 和每次推理前核对实际模型；tag 或 digest 不匹配时返回未就绪，不生成或误标向量。`KNOWAGENT_MODEL_OLLAMA_HEALTH_TIMEOUT_SECONDS` 仅控制 `/api/tags` 检查，默认 5 秒，不受 300 秒推理超时影响。

```bash
curl http://127.0.0.1:8100/health/ready
curl -X POST http://127.0.0.1:8100/v1/embeddings \
  -H 'Content-Type: application/json' \
  -d '{"model":"bge-m3","texts":["ESB 接口如何申请？"]}'
```

响应应包含 `model=bge-m3`、配置的 `model_version`、`dimension=1024`、`normalized=true` 和一个向量。旧 Ollama 在 Apple Silicon 纯 CPU 上可能单条也需数十秒；本地测试应将 backend 的 `KNOWAGENT_EMBEDDING_TIMEOUT_SECONDS` 临时设为 `300`，不要把此值直接作为生产延迟目标。

对真实 Ollama 执行可重复的 Provider 集成测试：

```bash
cd model-service
export KNOWAGENT_TEST_OLLAMA_BASE_URL=http://127.0.0.1:11434
export KNOWAGENT_TEST_OLLAMA_MODEL_DIGEST=79076464
PYTHONPATH=src pytest tests/integration/test_live_ollama.py -m integration -v
```

模型或 volume 更新后，必须先从 `/api/tags` 取得新 digest，再同步更新运行配置和上述测试变量；不得只修改对外版本标签。

## 4. 首个管理员

首个管理员只能通过一次性命令初始化；已有管理员后，命令会拒绝再次创建。

```powershell
knowagent-bootstrap-admin --username root.admin --display-name "平台管理员"
```

密码通过隐藏输入读取，不进入命令历史。新管理员首次从 `/admin/login` 登录后必须改密。

## 5. 批量导入用户

先为临时密码生成 Argon2id 摘要：

```powershell
knowagent-hash-password
```

按 `backend/examples/users-import.csv` 准备 UTF-8 CSV。列为：

```text
username,display_name,password_hash,role,credential_batch
```

- `password_hash` 必须是 `$argon2id$` 摘要；包含逗号时必须按 CSV 标准加双引号。
- `role` 只允许 `USER` 或 `SYSTEM_OWNER`；批量导入不能创建管理员。
- 同批账号重复、数据库已有账号或任意一行无效时，整批事务回滚。
- 所有导入账号固定设置 `must_change_password=true`。

执行导入：

```powershell
knowagent-import-users .\examples\users-import.csv
```

## 6. 前端

```powershell
cd frontend
npm ci
npm run dev -- --host 127.0.0.1 --port 5173
```

页面地址：

- 统一入口启动后的用户登录：`http://127.0.0.1:5273/login`
- 用户问答首页与系统选择：`http://127.0.0.1:5273/app`
- 管理员登录：`http://127.0.0.1:5273/admin/login`
- 业务系统管理：`http://127.0.0.1:5273/admin/systems`

统一入口通过环境变量将 Vite `/api` 代理到 `http://127.0.0.1:8200`；手工启动未设置该变量时仍使用默认 `http://127.0.0.1:8000`。

## 7. 验证

Phase 1 真实基础设施验收固定复用 `knowagent_integration`、Redis DB 15 和 `knowagent-phase1-it`，数据库/Bucket 只在首次缺失时创建：

```bash
./scripts/run-phase1-integration.sh
```

成功运行后仅清理本次验收记录、S3 对象和 Redis 消息，不删除数据库或 Bucket，也不执行 `flushdb`。标准 pytest 套件默认跳过该 live 用例，避免误连本地基础设施。

```powershell
cd backend
$env:PYTHONPATH = "src"
pytest tests -v

cd ..\model-service
$env:PYTHONPATH = "src"
pytest tests -v

cd ..\frontend
npm test
npm run typecheck
npm run lint
npm run build
```

SSO 端点已保留适配边界，但在公司协议确认前返回 `FEATURE_DISABLED`，不应作为可用登录方式展示。
