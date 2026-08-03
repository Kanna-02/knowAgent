# 本地开发

## 1. 前置条件

- Python 3.11.x；后端依赖以 `backend/pyproject.toml` 的 `[project]` 和 `[project.optional-dependencies.dev]` 为准。
- Node.js 24.x；只用于前端安装、测试和构建。
- PostgreSQL 16+ 测试实例，服务端必须能加载 `vector` 与 `pg_trgm` 扩展。
- Redis 7 测试实例，用于 Session、Celery broker 和恢复调度。
- 数据库迁移账号必须具有目标 Schema 建表/索引权限，以及 `CREATE EXTENSION vector`、`CREATE EXTENSION pg_trgm` 权限；若扩展由 DBA 预装，应用账号不需要扩展创建权限。
- 一个 OpenAI 兼容的 Embedding HTTP 服务，提供 `POST /v1/embeddings`，返回 `model`、`model_version`、`dimension`、`normalized` 和 `vectors`。它可以是项目后续自托管的内网 `model-service`，不要求购买外部 API，但当前仓库尚未实现实际模型运行时。
- Qwen OpenAI 兼容 API 的完整 Key、Base URL 和模型名；没有 Key 时可运行关键词/向量之外的单测，但不能完成真实回答生成。

本地 HTTP 调试可设置 `KNOWAGENT_COOKIE_SECURE=false`；类生产和生产环境必须使用 HTTPS，并保持 `true`。

## 2. 后端

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

macOS/Linux 对应命令是 `cp .env.example .env`。`.env` 是隐藏文件，在 Finder 默认不可见；可在 `backend` 目录执行 `ls -la .env` 查看。本仓库已忽略该文件，禁止把真实 Key 提交到 Git。

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
| `KNOWAGENT_EVIDENCE_*` | 否 | 证据条数和字符预算 |
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

## 3. 首个管理员

首个管理员只能通过一次性命令初始化；已有管理员后，命令会拒绝再次创建。

```powershell
knowagent-bootstrap-admin --username root.admin --display-name "平台管理员"
```

密码通过隐藏输入读取，不进入命令历史。新管理员首次从 `/admin/login` 登录后必须改密。

## 4. 批量导入用户

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

## 5. 前端

```powershell
cd frontend
npm ci
npm run dev -- --host 127.0.0.1 --port 5173
```

页面地址：

- 用户登录：`http://127.0.0.1:5173/login`
- 用户问答首页与系统选择：`http://127.0.0.1:5173/app`
- 管理员登录：`http://127.0.0.1:5173/admin/login`
- 业务系统管理：`http://127.0.0.1:5173/admin/systems`

Vite 将 `/api` 代理到 `http://127.0.0.1:8000`。

## 6. 验证

```powershell
cd backend
$env:PYTHONPATH = "src"
pytest tests -v

cd ..\frontend
npm test
npm run typecheck
npm run lint
npm run build
```

SSO 端点已保留适配边界，但在公司协议确认前返回 `FEATURE_DISABLED`，不应作为可用登录方式展示。
