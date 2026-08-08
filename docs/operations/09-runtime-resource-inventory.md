# Runtime Resource Baseline And Local Inventory

本文档记录 KnowAgent 的运行资源基线，以及 2026-08-08 对当前 macOS 宿主机和 Docker Desktop 的盘点与本地 Rerank 验证结果。过程不读取密钥值、不下载模型权重；仅在项目 model-service 虚拟环境安装项目锁定的可选推理依赖。

## 1. 系统所需资源清单

| 类别 | 资源 | 基线或用途 | 当前配置来源 |
| --- | --- | --- | --- |
| 宿主运行时 | Python | 3.11.x；backend 和 model-service 使用独立虚拟环境 | `backend/pyproject.toml`、`model-service/pyproject.toml` |
| 前端运行时 | Node.js / npm | Node.js 24.x；安装、测试和构建 React 前端 | `frontend/package.json`、`docs/operations/07-local-development.md` |
| 数据库 | PostgreSQL | 16+；必须加载 `vector` 和 `pg_trgm` | `backend/.env.example`、Alembic 迁移 |
| 会话与任务 | Redis | 7+；Session、登录限流、Celery broker 和恢复调度 | `backend/.env.example` |
| 对象存储 | S3 兼容服务 | 本地使用 MinIO；生产使用公司 S3 兼容端点和受控 TLS/CA | `backend/.env.example` |
| Embedding | Ollama + `bge-m3` | 1024 维归一化向量；model-service 转换为 `/v1/embeddings` | `model-service/.env.example` |
| Rerank | `BAAI/bge-reranker-v2-m3` | 对最多 20 个融合候选精排，默认返回 10 个 | `model-service/.env.example` |
| Rerank 运行时 | `FlagEmbedding==1.4.0` + PyTorch | 可选 extra；还需要其 Transformers 等传递依赖 | `model-service/pyproject.toml` |
| 生成模型 | Qwen OpenAI 兼容 API | 外部 API；Base URL、Key、模型名只从环境或密钥设施读取 | `backend/.env.example` |
| 应用进程 | API、Worker、Beat、model-service、Web | 本地默认端口为 8200、8100、5273；Worker/Beat 无监听端口 | `scripts/local-env.sh` |

Phase 3 本地默认 Rerank 限制为 `batch_size=4`、`max_length=512`、`max_concurrency=1`、`use_fp16=false`。生产 CPU、内存、GPU、量化和并发值仍需在目标 Linux 上通过真实 ESB 样本压测确定。

## 2. 宿主机已有资源

### 2.1 硬件与磁盘

| 项目 | 盘点值 | 结论 |
| --- | --- | --- |
| 设备 | MacBook Air，Apple M1，8 核，8 GB 内存 | 可做串行 CPU 冒烟；不应把本机吞吐或内存结果直接作为生产基线 |
| 架构 | `arm64` | PyTorch 必须使用 macOS ARM64 wheel |
| 系统 | macOS 26.5.1 | 本地开发环境，不代表目标 Linux |
| 根卷 | 228 GiB，约 43 GiB 可用 | 有安装空间，但应优先复用已有 4.2 GB Rerank 权重，避免重复下载 |

### 2.2 工具链与基础设施

| 资源 | 已有版本或状态 | 是否满足本地基线 |
| --- | --- | --- |
| Python shim | 3.11.11 | 是 |
| backend `.venv` | Python 3.11.15，约 365 MB | 是；应用依赖已安装 |
| model-service `.venv` | Python 3.11.15 | 基础服务与 `FlagEmbedding==1.4.0` Rerank 运行时已安装并完成真实推理 |
| Node.js / npm | 24.16.0 / 11.13.0 | 是 |
| PostgreSQL | 17.10，运行于 `127.0.0.1:5440` | 是 |
| PostgreSQL 扩展 | `vector 0.8.6`、`pg_trgm 1.6` | 是 |
| Redis | 8.10.0，运行于 `127.0.0.1:6380`，当前约 1.48 MB | 是 |
| MinIO | `RELEASE.2025-10-15T17-29-55Z`，二进制已安装，当前停止 | 已安装，需要完整入库链路时启动 |
| Ollama CLI | 宿主机未安装 | 不需要；当前由 Docker 容器提供 |
| model-service | 当前未监听 8100 | 需要 Rerank/Embedding 适配时启动 |

项目 `.runtime` 当前约 83 MB，其中 PostgreSQL 数据目录约 83 MB、Redis 约 208 KB、MinIO 数据约 64 KB。前端 `node_modules` 约 361 MB。

### 2.3 Python 推理依赖

初始盘点检查了以下四个现有虚拟环境：

- `knowAgent/backend/.venv`
- `knowAgent/model-service/.venv`
- `Function_Calling/backend/.venv`
- `ReActAgent/backend/.venv`

初始盘点时四者均未安装 `FlagEmbedding`、`torch`、`transformers`、`sentence-transformers`、`onnxruntime` 或 `optimum`。2026-08-08 已仅在 `knowAgent/model-service/.venv` 安装 `model-service[rerank]`，并将 `transformers` 固定为 4.57.6；实际验证确认 Transformers 5.14.1 与 FlagEmbedding 1.4.0 不兼容。其他三个环境仍不作为 KnowAgent Rerank 运行时。

全局 pip 缓存约 3.7 GB，但未确认其中存在可离线复用且版本匹配的完整 PyTorch wheel。恢复安装前应先列出锁定依赖和缓存命中情况。

## 3. 已有模型与缓存

| 位置 | 资源 | 大小/状态 | 复用结论 |
| --- | --- | --- | --- |
| Docker volume `deploy_ollama-models` | `bge-m3:latest` | 1.158 GB；digest `790764642607...`；F16 | 可直接复用；与项目默认 digest 前缀 `79076464` 一致 |
| `knowledge-rag/deploy/models/bge-reranker-v2-m3` | 原生 Safetensors 模型 | 约 2.1 GB；`model.safetensors` 2,271,071,852 bytes | 权重完整候选，可供 FlagEmbedding/PyTorch 使用 |
| `knowledge-rag/deploy/models/bge-reranker-v2-m3-onnx` | ONNX External Data 模型 | 约 2.1 GB；`model.onnx` + 2,271,088,656-byte `model.onnx_data` | 权重完整候选，可供 ONNX/TEI 备选方案使用 |
| `~/.cache/huggingface` | BAAI 与 ONNX 模型引用 | 总计约 504 KB，仅有 `refs/main`，无 blobs/snapshots | 不可视为已下载模型 |
| `~/.cache/modelscope` | Rerank lock 目录 | 0 B，无模型文件 | 不可复用 |
| `~/.ollama` | 宿主机 Ollama 缓存 | 不存在 | 使用 Docker volume，不需要重复下载 |

原生模型 `config.json` 声明 `XLMRobertaForSequenceClassification`、hidden size 1024、24 层、FP32 权重元数据，与 `bge-reranker-v2-m3` 交叉编码器结构相符。2026-08-08 已由当前 model-service 真实加载：示例相关候选得分约 `4.82495`，无关候选约 `-11.01469`；进程级 `/v1/rerank` HTTP 请求约 10.37 秒。

当前代码已用 `KNOWAGENT_MODEL_RERANK_MODEL_PATH` 承担本地加载路径，并保持 `KNOWAGENT_MODEL_RERANK_MODEL=BAAI/bge-reranker-v2-m3` 作为对外 API 标识；路径解耦门禁已关闭。

## 4. Docker 已有资源

### 4.1 与 KnowAgent 模型链路直接相关

| 资源 | 状态 | 占用/说明 |
| --- | --- | --- |
| 容器 `rag-ollama` | 运行且 healthy，映射 `11434:11434` | 镜像 `ollama/ollama:0.3.14`；提供 `bge-m3` |
| 镜像 `ollama/ollama:0.3.14` | 已存在 | 约 3.23 GB |
| 卷 `deploy_ollama-models` | 被 1 个容器使用 | 1.158 GB；必须复用，禁止重复拉取 `bge-m3` |
| 卷 `deploy_tei-cache` | 未使用 | 0 B；不含 Rerank 权重 |
| 卷 `deploy_pgdata` | 未使用 | 67.35 MB；属于 `knowledge-rag`，KnowAgent 不复用其数据库 |
| 卷 `deploy_rag-uploads` | 未使用 | 419.4 KB；属于 `knowledge-rag`，KnowAgent 不复用其业务对象 |
| TEI 容器/镜像 | 不存在 | 若改用 ONNX + TEI，需要另行确认镜像和 Apple Silicon 模拟成本 |

### 4.2 其他项目容器

Docker 中另有 Function Calling 和 ReActAgent 的 PostgreSQL/Redis/API/前端容器，以及 `postgres:15-alpine`、`postgres:16-alpine`、`redis:7-alpine` 镜像。它们证明镜像资源已存在，但其数据库、Redis namespace、账号和业务数据不属于 KnowAgent；按项目隔离规则不复用。

Docker 中没有 MinIO 镜像。KnowAgent 本地对象存储使用已安装的宿主机 MinIO 二进制和仓库内 `.runtime/minio` 数据目录。

## 5. 缺口与执行顺序

| 优先级 | 缺口 | 处理原则 |
| --- | --- | --- |
| 已关闭 | 本地 Rerank 运行时、路径解耦和真实加载 | 已复用现有权重完成离线与 HTTP 推理；禁止重新下载权重 |
| P1 | 8 GB M1 的组合内存余量未形成容量基线 | 保持 `max_concurrency=1`，避免同时加载模型和执行多套全量测试；本机结果仅作功能冒烟 |
| P1 | 目标 Linux CPU/内存/GPU 未知 | 不生成生产锁、不决定量化、不宣称本机结果代表生产 |
| P1 | 外部 Qwen 与公司 S3 只在 `.env` 配置 | 只验证连通性和契约，不把 Key 或真实端点写入本清单 |

本地执行链已完成：模型 ID/路径解耦 -> 锁定兼容依赖 -> 复用现有权重离线加载 -> model-service HTTP 集成。后续只剩真实 ESB 数据下的 RRF/Rerank 质量对比，以及目标 Linux 的资源、依赖锁、延迟和容量验证。任何步骤都不得隐式下载模型权重。

## 6. 更新规则

每次新增或替换模型、推理运行时、基础服务、目标服务器或资源限制时，更新以下字段：版本、架构、路径/卷、大小、digest/校验和、运行状态、是否可复用、验证日期和剩余缺口。密钥、密码、Token 和真实生产数据不得写入本文件。
