# Feature Changelog

本文档记录开发过程中新增、变更、删除的功能。每次完成一个功能或重要改动后都必须更新。

## 记录格式

```text
日期：
功能：
类型：新增/变更/删除/修复
相关文件：
变更说明：
影响范围：
验证方式：
后续注意：
```

## 功能变更记录

### 2026-08-03 - 完成 Phase 2 工单分派、处理、追加、关闭/重开与审核入库

类型：新功能

相关需求：REQ-007；AC-006、AC-007（AC-007"5 分钟内可检索"依赖检索层纳入 TICKET 来源，见后续注意）。

变更说明：

1. 新增工单工作流服务与状态机：`OPEN→ASSIGNED→IN_PROGRESS→RESOLVED→CLOSED→OPEN`，分派、开始处理、回复追加、关闭、重开和解决均加行锁并写入不可变 `ticket_transitions` 审计轨迹；回复区分提问人/处理人/审核人角色并做非空与超长校验。
2. 新增知识审核服务：处理人提交答案生成 `PENDING` 知识候选并阻止重复待审核提交；审核人批准时创建 `TICKET` 类型知识来源和单条 `PUBLISHED` 知识片段并标记候选已批准，拒绝时不创建任何知识来源；候选记录的 `reviewer_id` 与 `status` 作为审核决策的审计记录。
3. 新增 `ticket_replies`、`ticket_transitions`、`knowledge_candidates` 持久模型及迁移，均沿用 `ticket_id+system_id` 复合外键链；repository 补充行锁、回复、转换、候选增查与来源/片段创建，知识来源与片段用延迟导入避免 pgvector 硬耦合。
4. 新增 24 项工单工作流与知识审核单元测试覆盖合法/非法状态转换、角色推断、追加回复、关闭/重开、重复提交、批准后已发布片段可查、拒绝无知识来源、退回后再提交、未知实体和系统隔离；测试基础设施导入全部 ORM 模块避免孤立 `create_all` 漏表。

验证方式：后端 238 项测试全部通过，总覆盖率 90.84%，`tickets/application/review.py` 82%、`workflow.py` 84%、`tickets/infrastructure/sqlalchemy_repository.py` 94%；本次 6 个相关 Python 文件 Black/isort 清洁；4 个相关源文件 `mypy --strict` 零错误；4 个相关源文件 Pylint 10.00/10；相关源文件 Bandit 中高危 0。

后续注意：按用户指定范围，本轮未运行新迁移的 SQLite 往返、`alembic check`、真实 PostgreSQL/pgvector 或端到端集成测试；检索层当前 `source_type == DOCUMENT` 硬过滤尚未纳入 `TICKET` 来源，AC-007"5 分钟内可重新检索"在检索过滤器扩展前不成立；问答 API/SSE、工单 API 路由和真实链路验收仍待后续范围。

### 2026-08-03 - 完成 Phase 2 证据充分性决策与拒答工单基础代码

类型：新功能

相关需求：REQ-006、REQ-014；AC-005/AC-008 的基础代码范围，迁移与真实链路验收待补。

变更说明：

1. 新增确定性证据策略，对无证据、来源定位缺失、融合分数不足、头部候选分差不足、必需词未覆盖和显式证据冲突统一判定并记录版本化原因；向量通道降级时自动应用更严格阈值。
2. 新增可靠问答服务，仅在证据充分时生成并记录回答；证据预算清空、引用或声明无法由原文支撑时可靠拒答，模型格式错误、模型不可用和检索设施故障不误建知识缺口工单。
3. 新增 `evidence_decisions` 与 `tickets` 持久模型及迁移；拒答判定和自动建单共用事务，按 `system_id + 规范化问题 + 时间窗` 合并重复工单，同一运行幂等重放且不同系统不合并。
4. 新增策略版本、最低融合分数、头部差值、降级倍率和工单去重时间窗环境配置；测试复用现有 AnyIO pytest 插件执行异步用例，未新增或临时下载测试依赖。

验证方式：本次 Phase 2 后端 46 项单测全部通过，核心模块分支覆盖率 92.83%；18 个相关源/测试文件 Black/isort 清洁；111 个后端源文件 `mypy --strict` 零错误；Phase 2 源文件 Pylint 10.00/10；全后端 Bandit 中高危 0。

后续注意：按用户指定范围，本轮未运行新迁移的 SQLite 往返、`alembic check`、真实 PostgreSQL/pgvector、Ollama/Qwen 或端到端集成测试，因此 REQ-006 暂保持 `implementing`；问答 API/SSE、会话上下文和完整工单处理仍待后续范围。

### 2026-08-03 - 增加 Ollama bge-m3 模型服务适配层

类型：新功能

相关需求：REQ-004、REQ-009；AC-003/AC-004 的本地 Embedding 服务准备范围。

变更说明：

1. 在独立 `model-service` 中实现 `POST /v1/embeddings`、`GET /health/live`、`GET /health/ready` 和兼容 `/health`，返回主应用要求的模型、版本、维度、归一化标识和批量向量契约。
2. 新增 Ollama Provider，优先调用批量 `/api/embed`，在旧版本返回 404 时自动回退到逐条 `/api/embeddings`；默认内部批大小为 1，以规避既有 Ollama 0.3.14 在 Apple Silicon 纯 CPU 批处理时的超时问题。
3. 对 Ollama 返回执行模型名、数量、1024 维、有限数值和非零向量校验，并统一做 L2 归一化；网络、HTTP 和非法响应使用脱敏错误，不向主应用泄露内部地址或响应正文。
4. 默认配置对应本机已保留的 `deploy_ollama-models` volume：`bge-m3` 模型层 digest 前缀 `daec91ff`、占用约 1.158 GB；生产模型版本、维度、批大小、超时、文本限制和 keep-alive 均可由环境覆盖。
5. 完成 review 缺陷修复：readiness 和每次推理前都精确校验允许的模型 tag 与实际 digest，且对外版本必须以 digest 前缀结尾；严格拒绝非 JSON 数组、布尔值和字符串数值向量；健康检查使用独立短超时，并输出不含文本、内部 URL 或响应正文的结构化结果、耗时和错误类别日志。
6. 增加可由 `KNOWAGENT_TEST_OLLAMA_*` 环境变量启用的真实 Ollama 集成测试门禁，覆盖模型身份、维度、归一化和单条向量契约。

验证方式：review 修复后 model-service 39 项测试通过、1 项真实 Ollama 测试因本轮服务未启动而显式跳过，总覆盖率 90.58%；源文件与测试 `mypy --strict` 零错误，Bandit 中高危 0，diff 与 100 字符行宽检查通过。修复前已恢复 Ollama 0.3.14 并复用既有 volume 完成真实冒烟：`/health/ready` 返回 200，`/api/embed` 冷启动约 18.21 秒、热请求约 3.73 秒，适配响应为 1 个 1024 维向量且 L2 范数为 1.0000000000000004；修复后的 digest 强校验真实复验需在服务恢复后运行新增集成测试。

后续注意：本地 Ollama 适配用于复用已有模型和快速联调，不替代目标 Linux 的推理后端资源门禁；Rerank 适配、pgvector 真实检索、Worker 索引接线和 Qwen 完整链路仍待完成。本轮 review 修复验证时 `127.0.0.1:11434` 和 `127.0.0.1:8100` 未运行，需按本地开发文档恢复后补跑真实集成测试。

### 2026-08-03 - 完成 Phase 2 基础检索、证据组织和带引用回答内核

类型：新功能

相关需求：REQ-002、REQ-004、REQ-005、REQ-009、REQ-014；AC-004/AC-008 的基础代码范围，真实模型与 PostgreSQL 集成验收待补。

变更说明：

1. 新增 `retrieval` 模块，使用 PostgreSQL `pg_trgm` 关键词相似度和 pgvector 余弦距离执行基础召回；两个通道均在数据库查询中先限定 `system_id`、`PUBLISHED` 和文档来源，再用 RRF 去重融合。
2. 新增 OpenAI 兼容 `/v1/embeddings` Provider 和知识来源批量索引服务，校验模型名、版本、维度、归一化契约和返回数量，并在单个事务中原子写回向量；批大小、超时和模型均配置化。
3. 新增证据组织器，按条数和字符预算生成稳定 `E1...En` 证据编号，并保留 chunk、来源名称、来源版本和完整 `SourceLocator` 快照。
4. 新增 Qwen OpenAI 兼容 SSE Provider、结构化回答解析和引用校验；服务端拒绝未知证据 ID、非原文引用、缺少引用和不完整流，并输出不可变引用快照。
5. 向量服务不可用时显式降级到关键词召回；无证据时停止 LLM 生成。系统故障不会被伪装成知识不足。
6. 新增迁移 `c8784d439b23`：PostgreSQL 创建 `vector`/`pg_trgm` 扩展、增加 nullable 无固定维度向量列和 GIN trigram 索引。Embedding 维度尚未最终确认，因此本轮不创建 HNSW 索引。

review 修复（4 阻塞 + 3 建议）：

1. pgvector/数据库异常统一映射为向量通道不可用，回滚失败事务后降级到关键词，并通过结构化日志和 `RetrievalMetrics` 端口记录原因。
2. 问答 Prompt 从 Provider 代码移入随包发布的不可变 JSON 资源，记录场景、版本、启用状态、创建时间和变更说明；版本由环境配置选择并写入领域回答结果。
3. OpenAI 兼容流只接受 `finish_reason=stop`，拒绝 `length`、未确认完成和提前 `[DONE]`，避免把截断响应视为完成。
4. 回答协议改为声明级引用；每条声明必须逐字出现在其引用原文中，服务端保存声明到引用快照的映射，任意回答配无关短引用不再能通过。
5. Embedding 写回改为单次批量执行并保留系统/来源过滤和并发数量校验；证据组织器跳过超预算候选后继续选择可容纳证据。
6. 清理本轮 Pylint 报告并补充数据库失败、降级指标、Prompt 元数据、SSE 终止、声明支撑、批量更新和证据预算回归测试。

验证方式：后端 167 项测试全部通过，总覆盖率 91.06%；相关 27 个源文件 `mypy --strict` 零错误；本次 36 个 Python 文件 Black/isort 清洁；Pylint 10.00/10；Bandit 中高危 0；SQLite 完成迁移升级、降级、重新升级及 `alembic check`。真实 pgvector、Embedding 和 Qwen 调用尚未完成，不记为通过。

后续注意：当前交付是问答内核，不含问答 API/SSE 持久事件、会话/答案引用落库、证据充分性策略、自动建单、工单处理审核回流、Rerank 和 HNSW。需要可加载 `vector` 的 PostgreSQL、真实 Embedding 服务及完整 Qwen Key 后再执行外部集成验收。

### 2026-08-03 - Phase 1 集成验收有条件通过

类型：集成验收 / 质量门禁

相关需求：REQ-001、REQ-002、REQ-003、REQ-004、REQ-011；AC-001、AC-002、AC-003、AC-009 的 Phase 1 范围。

变更说明：在隔离 PostgreSQL 16.14 数据库和 Redis 7 DB/namespace 上验证双系统授权、上传越权拒绝、真实 Session、幂等重放、Markdown 持久入库、v2 发布切换、跨系统知识零泄漏、租约过期恢复和 Celery broker 派发；未修改功能代码。

验证方式：目标 Python 3.11.11 下后端 129 项测试全部通过、总覆盖率 91.54%；PostgreSQL `upgrade head` 和 `alembic check` 通过；真实 PG/Redis 验收脚本返回两个系统、v1/v2、B 系统 0 个发布 chunk、1 个恢复任务已派发和 6 个隔离 Redis Session key。

后续注意：本机无 S3 兼容服务或测试 Bucket，真实 S3 `put/get/delete`、四格式 S3→PG→Worker 全链路和真实后端页面手测被跳过，因此 Phase 1 为有条件通过，暂不正式关闭。详见 `docs/development/20-phase1-integration-acceptance.md`。

### 2026-08-02 - 完成 Phase 1 文档版本、发布状态与知识强隔离基础模型

类型：新功能

相关需求：REQ-002、REQ-004、REQ-011；AC-002/AC-003 的真实基础设施验收仍待集成环境。

变更说明：

1. 现有文档上传支持可选 `document_id` 创建 v2+，版本号在逻辑文档内递增；跨系统复用文档 ID 按不存在处理，响应增加 `version_no` 与 `publish_status`。
2. 新增独立 `DRAFT/PUBLISHED/RETIRED` 发布状态、文档当前发布指针、知识来源和知识片段模型；处理状态与发布状态分离，退役不会丢失解析结果。
3. 文档版本、知识来源、知识片段均持久化 `system_id`，使用 `document_id + system_id`、`document_version_id + system_id`、`source_id + system_id` 复合外键形成数据库隔离链；所有知识读取仓储方法强制接收 `system_id`。
4. 新增事务发布服务：发布新版本时原子切换当前指针并退役旧版本/来源/片段；退役后片段立即退出只读发布查询，历史数据不物理删除。
5. 新增 Alembic 迁移，先从文档回填版本 `system_id` 再收紧约束，并为 `system_id + publish_status` 查询建立索引；知识 locator/结构路径在 PostgreSQL 使用 JSONB。

review 修复（6 阻塞 + 2 建议 + 1 提醒）：

1. 入库任务持久化原始 nullable `document_id`，幂等校验改用任务上传者和完整操作类型，避免跨上传者重放失败或创建/追加版本请求互相复用。
2. 对象写入完成后才短事务锁定文档并分配下一版本号；追加版本同步刷新逻辑文档 `updated_at`，避免 S3 延迟长期占用数据库行锁。
3. 当前发布版本增加 `(version_id, document_id, system_id)` 可延迟复合外键，阻止跨文档或跨系统指针；发布与退役统一先锁文档再锁版本，消除相反锁序死锁。
4. Pylint 相似代码阈值调整为 30 行，过滤 SQLAlchemy 声明式短映射噪音并保留实质重复检测；补充 6 个幂等、事务顺序、持久化和约束回归测试。
5. Alembic downgrade 显式删除发布状态检查约束，修复 SQLite 批量重建时约束引用已删除列的问题。
6. Alembic/Pylint 本地产物纳入 `.gitignore`，防止误纳入提交。

验证方式：后端 129 项测试通过，总覆盖率 91.54%；本次 39 个 Python 文件 Black/isort 清洁，相关 32 个源文件 `mypy --strict` 零错误，Pylint 10.00/10，Bandit 中高危 0；隔离 SQLite 空库完成 `upgrade head -> downgrade d1a97d2e451b -> upgrade head` 往返且 `alembic check` 无差异。

后续注意：尚未在公司真实 PostgreSQL/Redis/S3 和目标 Python 3.11/Linux 环境执行双系统、四格式、迁移锁时长和查询计划验收；向量列与 Embedding/重建索引编排需在 DBA 扩展门禁及 Phase 2 检索实现中补充。

### 2026-08-02 - 确认架构并调整为 Python 3.11

类型：架构确认 / 技术基线变更

相关文件：技术决策、项目结构、路线图、追溯矩阵、当前状态、后端/model-service `pyproject.toml` 和前端工具链配置。

变更说明：用户正式确认模块化单体 + Celery Worker + 独立 model-service 架构；运行时由 Python 3.12 调整为本机现有的 Python 3.11.11。创建后端和模型服务依赖/静态检查配置，以及 React/TypeScript 的 package、tsconfig、ESLint、Prettier、Vite/Vitest 配置和 npm 锁文件。模型推理运行时继续等待服务器资源门禁。

影响范围：REQ-001 至 REQ-018 的模块边界从候选转为已确认并推进到 `skeleton`。Python 代码的 `requires-python`、Black 和 mypy/Pylint 目标统一为 3.11，不改变 API、数据或部署架构。

验证方式：TOML/JSON/JavaScript 配置语法检查通过；npm 依赖树解析并生成锁文件；官方 npm peer 契约确认 TypeScript 7 不兼容当前 typescript-eslint，因此固定 TypeScript 5.9.3。Python 3.12 跨版本解析因本机旧 pip 和 23.8 MB PyMuPDF wheel 仅约 47 KB/s 被终止，改为直接使用 Python 3.11 验证。

后续注意：当前没有业务源码，无法运行测试、构建或覆盖率检查；目标 Linux 上仍需生成 Python 传递依赖锁并验证模型运行时。

### 2026-08-02 - 完成系统架构草案

类型：架构设计（待确认）

相关文件：项目结构、需求澄清、文档索引和当前状态。

变更说明：完成模块化单体 FastAPI、Celery Worker/Beat、独立 Embedding/Rerank model-service、React 双端应用、PostgreSQL 事实源与 Outbox 的总体架构草案；补充模块依赖、类型化 API/Provider、核心 Schema、数据模型、状态机、三条核心数据流、非 Docker 部署、安全、可观测性和降级矩阵。

影响范围：REQ-001 至 REQ-018 的候选实现边界。当前只形成待评审设计，不代表架构已正式确认，也未创建业务代码。

验证方式：逐项对照架构阶段自检清单；18 个需求均已映射到候选模块；修正审计依赖方向和首次改密 Session 契约；保留追溯矩阵 `pending` 状态等待用户确认。

后续注意：用户确认后才可记录正式架构决策、将追溯矩阵推进为 `skeleton`，并补齐依赖管理和静态检查配置。

### 2026-08-02 - 确认应用框架与核心版本基线

类型：技术决策

相关文件：技术决策、前端设计、文档索引、追溯矩阵和当前状态。

变更说明：确认 TD-010 采用 Python 3.12、FastAPI/Pydantic/SQLAlchemy/Alembic 后端和 React/Vite/Ant Design/TanStack Query/Lucide 前端，并锁定已核验的核心直接依赖版本。redis-py 固定 6.4.0，以满足 Celery/Kombu 的 `<6.5` 约束。

影响范围：API、ORM、迁移、任务、Agent 编排、前端路由、服务端状态、表格表单、图标、构建和版本升级。

验证方式：PyPI/npm 官方索引版本查询；核心 Python 依赖 `pip --dry-run --ignore-installed` 组合解析通过；前端 peer dependency 覆盖 React 19。当前没有 Python 3.12 和目标 Linux 环境，尚未执行真实安装与构建。

后续注意：骨架阶段生成并提交锁文件，补齐解析器和测试工具精确版本；模型运行时等待目标服务器资源后再锁定。

### 2026-08-02 - 确认 RAG 编排与可靠拒答方案

类型：技术决策

相关文件：技术决策、文档索引、追溯矩阵和当前状态。

变更说明：确认 TD-009 使用 LangGraph 类型化状态图负责编排，自定义领域服务负责系统隔离、混合检索、证据判断、引用校验、对话持久化和工单事务；PostgreSQL 保持唯一业务事实源。

影响范围：意图识别、多轮问题改写、混合检索、Rerank、回答生成、引用溯源、可靠拒答、故障分流、工单去重、流式事件和对话分析。

验证方式：技术决策清单、TD-009 决策正文、REQ-006/REQ-008/REQ-009 追溯关系和项目状态交叉检查；当前尚无业务代码，因此未运行工作流测试或离线评测。

后续注意：架构阶段需定义 `QuestionWorkflow`、类型化 graph state、节点契约、错误分类、证据决策记录和工单幂等事务；阈值必须通过真实 ESB 评测集校准。

### 2026-08-02 - 确认非 Docker Linux 部署方案

类型：技术决策

相关文件：技术决策、文档索引、追溯矩阵和当前状态。

变更说明：确认 TD-008 使用 systemd 管理 API、Celery、调度器和模型服务，使用 Nginx 托管前端并反向代理 API/流式连接，使用版本化发布目录和 `current` 软链接切换版本。

影响范围：构建产物、服务器目录、进程权限、配置密钥、健康检查、日志监控、数据库迁移、应用升级和回滚。

验证方式：技术决策清单、TD-008 决策正文、部署需求追溯关系和项目状态交叉检查；当前未连接目标 Linux 服务器，未执行真实部署验证。

后续注意：目标发行版和组件版本确认后再锁定版本；架构阶段定义部署视图，部署阶段生成并验证 unit、Nginx 模板和发布脚本。

### 2026-08-02 - 确认文档解析与来源定位方案

类型：技术决策

相关文件：技术决策、文档索引、追溯矩阵和当前状态。

变更说明：确认 TD-007 采用 PyMuPDF、`python-docx`、`markdown-it-py`、`openpyxl` 的格式专用 Python 解析器组合，并在解析阶段统一生成结构化 `SourceLocator`。首版扫描 PDF 显式标记 `OCR_REQUIRED`，不以空内容成功入库。

影响范围：文档上传、解析、结构化切分、引用溯源、历史证据快照、重新索引和解析 worker 资源限制。

验证方式：技术决策清单、TD-007 决策正文、REQ-004/REQ-005 追溯关系和项目状态交叉检查；当前尚无业务代码，因此未运行解析测试。

后续注意：架构阶段需定义 `DocumentParser`、语义块联合类型和 `SourceLocator` DTO；依赖版本在完整技术包锁定时通过官方包源核验。

### 2026-08-02 - 双登录入口与账号来源调整

类型：变更

相关文件：需求、开发原则、技术决策、路线图、前端设计、追溯矩阵和项目规则。

变更说明：

1. 保留用户端和管理端双方登录，采用不同表单和路由，但共用账号表与认证服务。
2. 用户账号改为受控 SQL/导入脚本批量创建，管理员账号由后台新增，首个管理员单独初始化。
3. 默认密码只保存 Argon2id 摘要并强制首次改密；确认 Redis 服务端 Session，不采用 JWT。

影响范围：登录、账号导入、管理员管理、路由守卫、权限、会话、审计和 SSO 适配边界。

验证方式：已完成两组 `rg` 交叉检查：认证关键词覆盖需求、开发原则、技术决策、路线图、前端设计、追溯矩阵和项目规则；旧的“用户免登录”“TD-006 待决定”和索引“待用户确认”状态均已清理。当前尚无业务代码或页面可运行。

后续注意：架构阶段需定义账号表、导入协议、首次改密状态机、Session/CSRF 中间件和首个管理员初始化流程。

### 2026-08-02 - 完成 Phase 1 账号认证纵向切片

类型：新功能

相关需求：REQ-001、AC-001；为 AC-012 保留 SSO 适配边界，实际公司 SSO 仍属于 REQ-015/P2。

变更说明：

1. 新增用户端和管理端独立登录表单与接口，共用账号、Argon2id、Redis Session、CSRF、限流和审计实现。
2. 新增 `USER`、`SYSTEM_OWNER`、`ADMIN` 三角色服务端 RBAC，错误入口、禁用账号和受限 Session 返回稳定错误。
3. 新增首次强制改密与 Session 轮换；改密、禁用和状态变化通过 `session_version` 与 Redis 账号索引撤销旧会话。
4. 新增管理员账号列表、新增、状态控制和最后一个有效管理员保护；用户批量导入只接受 Argon2id 摘要，拒绝管理员角色并整批事务提交。
5. 新增首管理员初始化、临时密码摘要生成、用户导入命令，以及 SSO `IdentityProvider` 端口和显式禁用适配器。
6. 新增 Alembic 账号/审计表迁移、类型化 API 客户端、路由守卫、首次改密页和管理员账号页；管理路由按需加载。

验证方式：后端 25 个测试通过，覆盖率 91.43%；Alembic `autogenerate`、`upgrade head` 和 `check` 通过；前端 9 个测试、Prettier、TypeScript、ESLint 和生产构建通过。浏览器自动化访问本机地址被安全策略拒绝，未完成自动截图；真实 PostgreSQL/Redis 和 Python 3.11 环境仍需集成验证。

后续注意：本轮后端测试使用内置 Python 3.12 临时环境运行，不替代目标 Python 3.11 证明；公司 SSO 协议未确认前端点固定返回 `FEATURE_DISABLED`。下一项进入 Phase 1 多业务系统管理与负责人映射。

### 2026-08-02 - 修复账号认证切片评审问题

类型：缺陷修复

相关需求：REQ-001、AC-001、AC-010。

变更说明：

1. 管理员禁用前通过 PostgreSQL `FOR UPDATE` 锁定有效管理员集合，首管理员初始化增加事务级 advisory lock，消除并发下无有效管理员或重复初始化的竞争窗口。
2. 登录限流改为只累计失败请求，成功登录清除账号失败计数；Redis 失败计数和 TTL 在同一事务管道写入，避免正常登录耗尽额度或留下无过期时间的计数。
3. 账号、显示名称和 Argon2id 摘要使用共享校验，CLI 和批量导入会在写库前拒绝无法登录的账号及损坏摘要。
4. 客户端 `X-Request-ID` 在进入审计前校验格式和 64 字符上限，非法值替换为服务端 UUID。
5. 前端在 Session 初始化完成前不开放登录表单；成功登录/改密会清理旧错误，401 或退出失败仍会清空本地身份和 CSRF，避免竞态覆盖和路由跳转循环。
6. Vitest 覆盖率改为包含全部运行时源码，新增 API、认证状态、路由、改密、账号管理和应用入口工作流测试。

验证方式：后端 32 项测试通过，覆盖率 91.29%，Python 编译导入通过；前端 27 项测试通过，全局语句/分支/函数/行覆盖率分别为 92.68%/80.41%/86.36%/95.03%，Prettier、TypeScript、ESLint 和生产构建通过。

后续注意：真实 PostgreSQL 并发锁和 Redis 故障恢复仍需在隔离集成环境验证；当前虚拟环境缺少 Black/isort/mypy/Pylint/Bandit，安装审批服务返回 503，本轮未取得这些 Python 静态工具的运行证据。

### 2026-08-02 - 完成 Phase 1 多业务系统管理与前台选择基础切片

类型：新功能

相关需求：REQ-002（系统管理与选择部分）；AC-002 完整验收待知识/检索模块落地。

变更说明：

1. 新增业务系统领域、应用服务、SQLAlchemy 仓储与 API，支持系统创建、名称/说明更新、启停和按状态查询；系统标识统一转大写并保持唯一。
2. 新增 `business_systems` 与 `account_system_roles` 迁移，负责人映射以 `account_id + system_id + role` 唯一约束持久化，并为系统状态和负责人查询建立索引。
3. 负责人配置支持替换或追加；服务端只接受有效 `SYSTEM_OWNER` 账号，并通过 CSRF、管理员 RBAC 和审计约束所有写操作。
4. 登录和 `/auth/me` 响应增加类型化 `system_roles`；普通用户/负责人只可查询启用系统，管理员可查看全部系统。
5. 管理后台新增业务系统表格、编辑/启停和负责人配置抽屉；用户问答首页新增启用系统加载、空/错状态和显式系统选择。

验证方式：后端 37 个测试通过，总覆盖率 91.55%；Alembic `autogenerate`、`upgrade head` 和 `check` 通过；前端 34 个测试通过，全局语句/分支/函数/行覆盖率 93.36%/80.00%/88.72%/95.98%，TypeScript、ESLint、Prettier 和 Vite 生产构建通过。

后续注意：真实 PostgreSQL/Redis 和浏览器响应式页面尚待集成验证；Black/isort/mypy/Pylint/Bandit 安装与 `npm audit` 网络审批均因服务 503 未完成。Phase 1 下一项为双端基础导航、状态和错误处理。

### 2026-08-02 - 修复多业务系统切片评审问题

类型：缺陷修复

相关需求：REQ-002；安全规则 16.3。

变更说明：

1. 负责人映射新增或移除后撤销受影响账号的 Redis Session，无变化的幂等更新不触发退出。
2. 管理员系统列表新增服务端分页；负责人候选支持按账号或显示名称搜索，并与系统列表独立加载、独立重试。
3. 普通用户系统列表保留兼容响应结构，但不再返回负责人姓名和账号；管理员分页接口保留负责人详情。
4. 编辑业务系统前重置表单并显式清空空说明，避免复用上一次编辑值。
5. 追溯矩阵将 REQ-002 修正为 gap：系统管理与选择基础已完成，知识/检索强隔离和 AC-002 零泄漏验收待实现。

验证方式：后端 39 项测试通过，总覆盖率 92.07%；前端 35 项测试通过，语句/分支/函数/行覆盖率分别为 92.56%/81.73%/87.50%/95.34%，TypeScript、ESLint、Prettier 和 Vite 生产构建通过。

后续注意：真实 PostgreSQL/Redis 和浏览器响应式页面仍待集成验证；当前 Python 3.12 虚拟环境未安装 Black/isort/mypy/Pylint/Bandit。

### 2026-08-02 - 完成 Phase 1 双端基础导航、状态和错误处理

类型：新功能

相关需求：REQ-003 的 Phase 1 基础切片；AC-001、AC-009 的页面基础能力。

变更说明：

1. 新增用户端与管理后台共用的响应式工作区壳层，桌面端固定侧栏、移动端抽屉导航、当前路由高亮、上下文标题、账号菜单和独立入口退出路径保持一致。
2. 用户端改为嵌套路由并继续按路由懒加载；当前只展示已实现的问答入口，不暴露尚未落地的工单、知识或审计空路由。
3. 新增统一 loading、empty、error 反馈组件和安全错误模型；账号列表、系统列表和前台系统选择在失败时保留已有内容，显示后端 `request_id` 并支持原位重试。
4. 新增应用级错误边界，渲染异常时只显示重新加载和返回入口，不暴露内部异常；403、404 状态补充明确上下文。
5. 新增共享壳层、错误转换、错误边界和三类页面恢复路径测试，并补齐移动导航和请求追踪断言。
6. 浏览器检查后修正 Ant Design 6 Drawer 弃用属性，并让 API 客户端将空/非 JSON 网关失败归一化为稳定、可追踪错误；退出接口失败不再产生未处理 Promise。
7. 修复评审发现的列表重试竞态：账号和业务系统列表采用最新请求胜出策略，重试期间锁定恢复按钮；工作区在所有 `<1024px` 视口切换为抽屉导航，并规避高 DPI 下的媒体查询亚像素空档。

验证方式：前端 42 项测试通过；全局语句/分支/函数/行覆盖率 92.49%/85.11%/85.62%/94.63%；TypeScript、ESLint、Prettier 和 Vite 生产构建通过。浏览器在 1440x900、390x844 以及 1023px/1024px 临界视口完成用户端、管理端、抽屉切换、长系统名、表格横向滚动和保留数据的错误状态检查，页面无横向溢出或控件重叠。`npm audit` 的首次沙箱请求无法访问公告接口，外部执行因会向公共 npm 服务发送依赖元数据而被安全策略拒绝。

后续注意：浏览器检查使用仅绑定本机的隔离测试 API 和虚构数据，不替代真实 PostgreSQL/Redis 集成验证；Phase 1 下一项为统一 `SourceLocator` 与四类文档结构化解析基础。

### 2026-08-02 - 完成 Phase 1 统一来源定位与四类结构化解析基础

类型：新功能

相关需求：REQ-004 的解析/切分/定位部分、REQ-005 的来源定位基础；AC-003 的持久化索引部分随下一项完成。

变更说明：

1. 新增严格联合校验的 `SourceLocator`，统一携带文档、版本、来源类型和块序号；分别保存 PDF 页码/坐标、Word 标题与段落/表格行、Markdown 标题与源行、Excel 工作表与单元格范围。
2. 新增 PyMuPDF、python-docx、markdown-it-py、openpyxl 格式适配器和 parser registry，领域契约不暴露第三方对象；解析结果记录 parser/schema 版本。
3. 新增集中式资源限制和稳定解析错误码，拒绝超大/异常压缩 Office、损坏或加密文件、非 UTF-8 Markdown 和超页数 PDF；无可提取文本的 PDF 返回 `OCR_REQUIRED`。
4. 新增结构感知 chunker，页、标题路径、工作表和表格边界优先于预算；表格按行组合并重复表头，超长块拆分后仍直接继承原始 locator，不在切分后反推来源。
5. 新增运行时生成的 `.docx`、文本型 `.pdf`、`.md`、`.xlsx` 样本测试，覆盖结构、精确定位、扫描 PDF、损坏文件、资源上限和切分边界。

验证方式：后端 68 个测试全部通过，总覆盖率 89.46%；本次 `documents` 15 个源文件 `mypy --strict` 零错误，Pylint 10.00/10，Black/isort 检查通过；全仓 Bandit 中高危问题 0。全仓 mypy 仍有 identity/systems 既有 26 个错误，未计为本功能通过。

后续注意：本轮未接入对象存储、PostgreSQL/Celery 持久任务和真实 ESB 文件，AC-003 尚未完整验收；测试环境为内置 Python 3.12.13，目标 Python 3.11/Linux 仍需集成验证。Phase 1 下一项为对象存储与可恢复文档入库任务。

### 2026-08-02 - 修复统一来源定位与解析评审问题

类型：缺陷修复

相关需求：REQ-004、REQ-005；TD-007。

review 修复（5 阻塞 + 3 建议 + 3 提醒）：

1. 中文 token 预算改为逐 CJK 字符保守计数，超长表头和仅表头表格统一遵守硬预算；补齐普通块 overlap、超长表格行重复表头和完整 locator 传播测试，chunker 覆盖率提升到 90%。
2. Markdown 表格行直接使用 AST token 的源行映射，不再根据表头和分隔行算术反推；多数据行引用可精确回到原始行。
3. `SourceLocator` 补齐格式内联合约束：Word 段落/表格位置互斥，Markdown/XLSX 表格字段成组出现，PDF 坐标必须为有限值。
4. 损坏 DOCX/XLSX 内部 XML 统一映射为 `INVALID_FILE`；文件、归档展开、压缩比、归档条目、PDF 页/块、Word/Markdown 块及 Excel 结构上限均可配置并增量生效。
5. parser port 改为同步 worker 契约，避免 CPU 密集解析被误放入 FastAPI 事件循环；MIME 匹配支持 `charset` 等参数。
6. 新增 `DocumentProcessingSettings` 和 `KNOWAGENT_DOCUMENT_*` 环境变量，本地开发与架构文档同步配置和 worker 资源边界。

验证方式：后端 81 个测试全部通过，总覆盖率 90.80%，`chunking.py` 覆盖率 90%；Black/isort 检查通过，`documents` 与平台 settings 共 16 个源文件 `mypy --strict` 零错误，Pylint 10.00/10，全仓 Bandit 中高危问题 0；目标 Python 3.11 未运行，`py -0p` 确认本机没有已安装 Python。

后续注意：本轮仍使用 Python 3.12.13；Celery 任务软/硬超时、进程内存限制和真实 Office/PDF 样本需在下一项持久入库任务及目标 Python 3.11/Linux 集成环境验证。

### 2026-08-02 - 完成 Phase 1 对象存储与可恢复持久化入库任务

类型：新功能

相关需求：REQ-004 的对象存储、持久任务和可恢复处理部分；AC-003、AC-009。

变更说明：

1. 新增 S3 兼容对象存储适配器，支持流式/multipart 上传、读取和删除，配置受控 TLS/CA、连接与读取超时及 SDK 标准有限重试；对象 key 确定生成，凭据只从环境提供且不进入配置对象 repr。
2. 新增 `documents`、`document_versions`、`ingestion_jobs` ORM 与 Alembic 迁移，持久记录任务状态、处理阶段、进度、尝试预算、租约、派发、错误和 parser/manifest 元数据，并用账号+系统幂等作用域、检查约束和乐观版本列保护一致性。
3. 新增上传用例和 API：管理员或系统负责人可上传，同一账号与系统内只有文档名、文件元数据和内容摘要全部一致时重复幂等键才返回同一任务；数据库或审计持久化失败会尽力清理孤儿对象。任务查询和人工重试均执行系统归属权限与 CSRF 校验。
4. 新增 Celery ingestion Worker、仅携带 `job_id` 的派发器和 Beat 恢复扫描。PostgreSQL 保持业务事实源；Worker 通过租约领取，持久推进 `STORED -> PARSING -> CHUNKING -> COMPLETED`，并写入确定性 `chunks-v1.json` manifest。
5. 新增可重试/永久失败分类、指数退避、自动尝试预算、人工重试预算重置和租约过期恢复；自动重试与恢复清除旧 Celery 派发元数据，耗尽后 fail closed。
6. 新增状态机、S3 配置/错误、repository、processor/recovery、幂等上传、孤儿清理、权限和 API 测试，并同步技术决策、路线图、追溯矩阵、架构和本地运行说明。

review 修复（5 阻塞 + 4 建议 + 2 提醒）：

1. 为 Worker 状态写入增加 owner + attempt + 有效期 fencing，并约束租约必须长于 Celery 硬超时；过期 Worker 无法覆盖重新领取后的任务。
2. 非 `FAILED` 任务人工重试改为稳定 `INGESTION_JOB_NOT_RETRYABLE` 409，API 工厂按传入 Settings 构造相同 Redis Broker 的 Dispatcher。
3. 解析与切分完成后的版本状态改为 `CHUNKED`，Embedding 和知识索引完成前不再提前进入 `READY_DRAFT`；租约恢复时版本同步回到 `UPLOADED`。
4. S3 TLS 和 Cookie 安全布尔配置改为严格解析，未知值启动失败；幂等键唯一范围改为账号+业务系统，避免跨租户键占用。
5. 上传审计纳入对象补偿边界，审计或数据库持久化失败时尽力删除本次对象；API 契约同步当前 job-centric 查询与重试路径。
6. 补充 Dispatcher Broker、Worker task 装配、租约竞争、非法重试、幂等作用域、严格配置和审计补偿测试，并统一格式化本次修改的集成测试文件。

验证方式：后端 115 项测试全部通过，总覆盖率 91.07%；review 相关 42 项定向测试通过；本次 30 个相关源文件 `mypy --strict` 零错误，Pylint 10.00/10，全仓 Bandit 中高危 0；本次 28 个未提交 Python 文件 Black/isort 检查通过，`git diff --check` 通过；隔离 SQLite 空库 `alembic upgrade head` 与 `alembic check` 通过且 ORM/迁移无新增差异。全仓 mypy 仍为 identity/systems 既有 6 文件 26 个错误，未计为本功能通过。

后续注意：本轮为纯后端能力，无页面手动测试；未连接公司真实 PostgreSQL、Redis、S3 兼容端点或 ESB 文件，尚未验证签名/TLS/multipart/权限和重启恢复的真实基础设施契约；测试运行于 Python 3.12.13，目标 Python 3.11/Linux 仍需集成验证。Phase 1 下一项为文档版本、发布状态和基于 `system_id` 强过滤的知识隔离基础模型。
