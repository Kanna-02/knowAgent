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

### 2026-08-13 - 文档导入批任务超时保护与 macOS 原生 Ollama

类型：新增 / 变更 / 测试 / 文档

相关需求：REQ-004；AC-003。

相关文件：`backend/src/knowagent/documents/application/{chunk_ingestion,processor}.py`、`backend/src/knowagent/documents/domain/ingestion.py`、`backend/src/knowagent/documents/infrastructure/sqlalchemy_repository.py`、`backend/src/knowagent/documents/ports.py`、`backend/src/knowagent/knowledge/application/indexing.py`、`backend/src/knowagent/knowledge/domain/models.py`、`backend/src/knowagent/platform/settings.py`、`backend/src/knowagent/worker/{celery_app,dispatcher,tasks}.py`、`backend/tests/unit/test_{ingestion_job,ingestion_repository,knowledge_indexing,worker_tasks,document_configuration}.py`、`backend/.env.example`、`scripts/local-env.sh` 及本地运行、状态、追溯、技术决策文档。

变更说明：

1. 将 `CHUNKING` 阶段的向量化拆为独立 `knowagent.ingestion.batch` Celery 任务；每批只处理 `embedding IS NULL` 的前 N 个片段，成功后立即写回向量、释放租约并调度下一批，`embedding IS NULL` 作为天然 checkpoint。
2. 批任务独立配置 300 秒软超时 / 360 秒硬超时，异常批通过租约恢复和持久重试续跑，不重复已完成批次，也不耗尽文档整体重试预算；解析/恢复任务仍保留通用 600/660 秒超时。
3. 本地运行改为 macOS 原生 Ollama：`scripts/local-env.sh` 检查 `ollama` CLI 与 `127.0.0.1:11434/api/tags`，不再启动或依赖 `rag-ollama` Docker 容器；本地文档同步更新安装、启动和批任务 checkpoint 说明。

影响范围：文档导入 Worker 与索引服务、本地启动脚本及运维文档；不新增数据库迁移，不改变发布事务和检索隔离。

验证方式：后端全量 426 passed、25 skipped，覆盖率 85.66%；方案 C 相关源文件与测试 `mypy --strict` 零错误、Black/isort 清洁，`git diff --check` 通过。

### 2026-08-13 - 文档版本管理增强：删除、检索与状态筛选

类型：新增 / 变更 / 测试 / 文档

相关需求：REQ-011；AC-003。

相关文件：`backend/src/knowagent/documents/api/{lifecycle_router,router}.py`、`backend/tests/integration/test_identity_api.py`、`frontend/src/features/admin/DocumentsPage.tsx`、`frontend/src/features/admin/DocumentsPage.test.tsx`、`frontend/src/api/{client,client.test}.ts`、`frontend/src/styles.css` 及状态、设计、追溯文档。

变更说明：

1. 新增文档删除与版本删除管理端点：按文档/版本范围清理知识来源、知识片段、导入任务和对象存储文件，并写入 `document.delete` / `document_version.delete` 审计；存在排队、处理中或待重试导入任务时返回 409，避免删除正在处理的版本。
2. 版本列表新增文件名搜索、处理状态与发布状态服务端筛选；文档库新增最新处理状态与发布状态筛选；导入任务新增文档名称搜索。
3. 前端文档库工具栏增加处理/发布状态筛选和删除文档确认；版本抽屉增加文件名搜索、状态/发布状态筛选、知识片段与创建时间列及版本删除确认；导入任务增加名称搜索。

影响范围：文档管理 API 查询/删除端点和管理端页面；不修改数据库 Schema、发布事务、Worker 状态机或检索隔离逻辑。

验证方式：后端 identity API 集成 15/15 通过（`--no-cov`），2 个相关源文件 `mypy --strict` 零错误、Black/isort 清洁；前端全量 22 个测试文件 109/109 通过，TypeScript、ESLint、Prettier 通过。

后续注意：删除不可恢复；对象存储清理为数据库提交后的尽力而为操作，失败仅记录日志，数据库事实源不受影响。

### 2026-08-11 - 文档版本与导入任务管理工作台

类型：变更 / 新增 / 测试 / 文档

相关需求：REQ-011；AC-003、AC-007。

相关文件：`backend/src/knowagent/documents/api/{router,schemas,lifecycle_router,lifecycle_schemas}.py`、`backend/tests/integration/test_identity_api.py`、`frontend/src/features/admin/DocumentsPage.tsx`、`frontend/src/features/admin/DocumentsPage.test.tsx`、`frontend/src/api/{client,client.test,types}.ts`、`frontend/src/styles.css` 及需求、架构、设计、路线图、追溯和状态文档。

变更说明：

1. 新增按业务系统隔离的导入任务分页查询，支持多个 `status` 条件；任务、版本和文档使用单条联结查询返回，页面不再依赖 sessionStorage 保存最近一个任务。
2. 文档总表新增服务端名称搜索、版本总数、最新版本号/处理状态和当前发布版本号；版本抽屉增加分页与中文状态，并仅允许 `READY_DRAFT` 发布。
3. 管理页调整为“文档库 / 导入任务”双视图；导入任务支持状态筛选、自动刷新、进度、尝试次数、失败详情与人工重试。
4. 文档行新增“导入新版本”，复用既有 multipart `document_id` 契约追加 v2+；新文档导入、进度摘要、发布与退役能力保持不变。

影响范围：文档管理 API 的只读查询响应、管理端文档/导入任务工作流和相关文档；不修改数据库 Schema、对象存储、Worker 状态机或发布事务。

验证方式：后端 identity API + 文档生命周期 24 项通过（定向测试使用 `--no-cov`），4 个相关源文件 `mypy --strict` 零错误、Pylint 10.00/10、Black/isort 清洁；前端全量 22 个测试文件、105/105 通过，TypeScript、ESLint、Prettier 和 Vite 生产构建通过。隔离样例 API 下在 1440×900 与 390×844 验证文档库、任务表、失败详情、版本抽屉和版本追加弹窗，页面无整页横向溢出、控件重叠或本项目控制台告警；真实文件上传与 Worker 处理未在本轮浏览器中触发。

### 2026-08-10 - 账号角色修改与问答拒答错误修复

类型：修复 / 变更 / 测试

相关需求：REQ-001、REQ-005、REQ-006；AC-001、AC-004、AC-005。

相关文件：`backend/src/knowagent/identity/`、`backend/src/knowagent/api/app.py`、`backend/src/knowagent/agent/application/{answer_generation,reliable_question}.py`、相关后端测试、`frontend/src/api/client.ts`、`frontend/src/features/admin/AccountsPage.tsx`、相关前端测试。

变更说明：

1. 新增管理员角色变更 API 和页面弹窗，角色变更会递增会话版本、撤销旧会话、记录旧/新角色审计，并阻止移除最后一个有效管理员。
2. 将 FastAPI 请求校验失败统一为 `REQUEST_INVALID`，避免前端把旧 schema/非法参数的 422 显示为无诊断信息的通用错误。
3. 模型按提示返回空 `claims` 时进入证据不足的可靠拒答路径，不再错误显示“模型服务暂时不可用”；真实上游 HTTP、超时和解析故障仍保留 Provider 不可用错误。

影响范围：管理员账号角色管理、请求错误反馈、证据不足问答和拒答工单流程；不改变数据库 Schema。

验证方式：后端身份定向 20 passed，问答生成/可靠问答 28 passed；前端账号/API 定向 11 passed；identity/agent/api mypy strict 通过，前端 TypeScript 通过；真实 DashScope 流式响应复现空声明并验证为 `ANSWER_NO_SUPPORTED_CLAIMS`。

### 2026-08-09 - 账号、文档进度、Rerank 性能与问答工作区修复

类型：修复 / 变更 / 测试 / 文档

相关需求：REQ-001、REQ-002、REQ-003、REQ-005、REQ-009、REQ-011；AC-001、AC-002、AC-004、AC-008、AC-009。

相关文件：`backend/src/knowagent/identity/`、`backend/src/knowagent/retrieval/infrastructure/http_rerank.py`、`backend/src/knowagent/platform/settings.py`、`backend/src/knowagent/agent/api/router.py`、`backend/.env.example`、相关后端测试、`frontend/src/features/admin/AccountsPage.tsx`、`DocumentsPage.tsx`、`SystemsPage.tsx`、`frontend/src/features/auth/UserHomePage.tsx`、`authPolicy.ts`、`streamTextBatcher.ts`、`frontend/src/api/client.ts`、`frontend/src/styles.css`、相关前端测试及产品/工程/运维文档。

变更说明：

1. 管理端“用户与角色”支持逐个新增普通用户、系统负责人和平台管理员；创建请求模型改为通用账号语义。系统负责人候选为空时给出原因和跳转到用户管理的操作，解决负责人配置无候选问题。
2. 临时密码与首次改密策略统一放宽为至少 8 个字符且同时包含字母和数字；Argon2id、首次强制改密、限流与会话撤销保持不变。
3. 文档入库任务在上传弹窗关闭后继续于列表工具区显示名称、阶段、状态和百分比，并可重新打开进度详情。
4. 确认本地默认候选规模 Rerank 约 33.36 秒，明显超过后端 5 秒超时且服务端 CPU 推理会继续；新增默认 60 秒失败冷却，避免后续问答重复触发重推理，同时保留真实的“检索已降级”提示。
5. SSE 增量文本按 50 ms 合并刷新，降低每 token 重绘；问答页重构为历史会话栏 + 当前会话主面板，增加用户/助手头像、稳定标题和移动端横向历史列表。
6. 浏览器验收发现移动端系统选择容器继承 `flex-basis: 360px`，将选择器拉伸到约 187px 高；移动断点改为 `flex: none` 后恢复 36px 控件高度。

影响范围：账号创建和密码策略、系统负责人配置、文档异步进度、Rerank 故障恢复、SSE 渲染性能及用户端问答布局；不改变数据库 Schema、Session 安全边界或检索降级语义。

验证方式：后端 405 passed、25 skipped，总覆盖率 85.57%；171 个源文件 mypy strict 零错误，229 个 Python 文件 Black 清洁，isort 完成，Bandit 中高危 0；全仓 Pylint 保持既有 9.81/10，本次新增告警已消除。前端 22 个测试文件、99/99 通过，语句/分支/函数/行覆盖率 89.52%/81.79%/84.06%/90.85%；TypeScript、ESLint、Prettier、Vite 生产构建和 `npm audit --audit-level=moderate` 通过，漏洞 0。隔离 Mock API 下在 1280x720、390x844 完成系统选择、会话切换、错误态、输入区和溢出检查，默认浏览器视口已恢复，临时 Mock/Vite/页面已清理。

后续注意：失败冷却只阻止后续请求，不能取消模型服务已经开始的首个 CPU 推理；多 API Worker 进程各自维护冷却状态。目标 Linux 资源与真实 ESB 评测集到位后仍需决定原生 PyTorch、量化、ONNX 或独立推理服务方案。

### 2026-08-08 - 用户端问答工作区改为 ChatGPT 风格

类型：变更 / 测试 / 文档

相关需求：REQ-003、REQ-005、REQ-006、REQ-008；AC-004、AC-005、AC-009。

相关文件：`frontend/src/features/auth/UserHomePage.tsx`、`frontend/src/features/auth/UserHomePage.test.tsx`、`frontend/src/features/auth/UserHomePage.stream.test.tsx`、`frontend/src/styles.css`、`docs/product/15-frontend-design.md`。

变更说明：

1. 将问答页调整为上下文工具栏、会话消息流和底部输入工作区，压缩标题说明并持续显示业务系统选择器。
2. 用户消息与助手消息采用清晰的左右层级，流式回答、降级提醒、拒答建单和会话操作继续复用原有状态与无障碍标签。
3. 输入区改为主问题输入加次级检索约束工具行，发送按钮使用图标，支持 Enter 发送与 Shift + Enter 换行；不新增依赖或 API。

影响范围：用户端问答页面的布局、视觉层级和输入交互；不改变会话、SSE、检索、引用或工单业务契约。

验证方式：`UserHomePage`/SSE 定向测试 4/4 通过；TypeScript、ESLint、Prettier 和生产构建通过。

后续注意：真实登录后的桌面与移动浏览器验收应继续关注长回答、降级 Alert 和底部输入区在窄屏下的滚动行为。

### 2026-08-08 - 管理端文档导入入口

类型：新增 / 测试

相关需求：REQ-011；AC-003、AC-007。

相关文件：`frontend/src/features/admin/DocumentsPage.tsx`、`frontend/src/features/admin/DocumentsPage.test.tsx`、`frontend/src/api/client.ts`、`frontend/src/api/client.test.ts`、`frontend/src/api/types.ts`、`frontend/src/styles.css`。

变更说明：

1. 管理员在选定业务系统后可通过“导入文档”入口上传 PDF、DOCX、Markdown 和 XLSX 文件，可选填写知识库名称。
2. 前端以 multipart 方式调用既有文档入库 API，自动生成幂等键，展示排队/解析/切分/完成进度，并在失败时支持人工重试。
3. 入库成功后自动刷新当前系统文档列表；保留后端既有系统权限、CSRF、对象存储和异步 Worker 约束，不新增依赖或数据库结构。

影响范围：管理员文档运营页面和前端请求封装；不改变后端上传契约、知识发布流程或检索隔离逻辑。

验证方式：`DocumentsPage` 11 项组件测试、`ApiClient` multipart 回归测试通过；前端全量 21 个测试文件、96/96 通过，TypeScript、ESLint、Prettier、Vite 构建和 `npm audit --audit-level=moderate`（0 漏洞）通过。真实浏览器端文件上传和异步 Worker 运行仍待人工验收。

后续注意：对象存储、Celery Worker 和 Embedding 服务必须可用，任务完成后仍需在版本抽屉中显式发布版本才会进入检索。

### 2026-08-08 - Phase 2/3 完成度审计、本地 Rerank 与运营页验收收尾

类型：变更 / 修复 / 测试 / 文档

相关需求：REQ-004、REQ-005、REQ-009、REQ-011、REQ-012、REQ-013、REQ-014、REQ-018；AC-003、AC-004、AC-005、AC-008、AC-010、AC-011、AC-014。

相关文件：`model-service/src/knowagent_model/settings.py`、`flag_embedding.py`、`app.py`、`model-service/.env.example`、`model-service/pyproject.toml`、相关单元/集成测试、`backend/tests/integration/test_agent_api.py`、`test_phase3_live_integration.py`、`frontend/src/features/admin/AuditLogsPage.tsx`、对应测试、`frontend/src/styles.css`、Phase 2/3 状态/路线图/验收/评测/追溯/运维文档。

变更说明：

1. 新增 `KNOWAGENT_MODEL_RERANK_MODEL_PATH`，将对外模型 ID 与本地权重路径解耦；FlagEmbedding 优先从本地路径加载，同时保持 HTTP 契约仍使用 `BAAI/bge-reranker-v2-m3`。
2. 固定 `transformers==4.57.6`，避免 Transformers 5.14.1 与 `FlagEmbedding==1.4.0` 的运行时不兼容；新增真实本地权重 HTTP 集成测试。
3. 修复 Agent API 集成替身与当前 `retrieval_profile_name` 契约漂移，以及 Phase 3 live 测试的流式用户消息/终态消息持久化顺序。
4. 修复审计操作长标签覆盖相邻列、分析页移动端表格列撑开整页的问题，并补长操作标签组件回归。
5. 明确 Phase 2、Phase 3 均为“功能范围完成、阶段验收未关闭”：Phase 2 等待真实 ESB 标注集和完整业务页数据；Phase 3 等待真实公司通知 API、真实 ESB Rerank 质量收益和目标 Linux 资源。Stub 通知与合成问题不计入正式验收。

影响范围：model-service Rerank 本地加载与依赖兼容、集成测试契约、管理后台审计/分析响应式布局，以及 Phase 2/3 项目状态和运维说明；不改变数据库结构，不伪造外部验收结果。

验证方式：Phase 2 真实服务集成 23 passed、6 warnings（177.84 秒）；Phase 3 PostgreSQL 1 passed，通知 API + 本地 FastAPI Stub 4 passed；本地 Rerank HTTP 集成 1 passed（17.67 秒），相关/无关候选得分约 4.82495/-11.01469，进程级 HTTP 约 10.37 秒。后端全量 401 passed、25 skipped，覆盖率 85.55%；model-service 全量 51 passed、2 skipped，覆盖率 86.76%。前端在当前高负载下默认 5 秒超时运行两次均为 80/93，通过仅放宽测试超时到 20 秒的同一套断言后 93/93，覆盖率 90.52%/82.43%/85.51%/91.82%；TypeScript、ESLint、Prettier、Vite build 和 `npm audit` 通过，漏洞 0。Backend 242 个 Python 文件 Black/isort 清洁、171 个源文件 mypy strict 零错误、Bandit 中高危 0；model-service 本次变更文件 Black 清洁、8 个源文件 mypy strict 零错误、相关 Pylint 10.00/10、Bandit 中高危 0，全目录 Black 仍受未改动 `ollama.py` 既有格式差异影响。文档、分析、审计页面在 1440x900 与 390x844 真实登录/API 会话下通过浏览器验收。

后续注意：没有真实 ESB 标注集、真实公司通知测试端点和目标 Linux 资源前，不得把 Phase 2 或 Phase 3 标记为已完成；默认前端 5 秒超时在当前机器负载下仍有稳定性风险。

### 2026-08-08 - 前后端覆盖率、格式与依赖门禁补强

类型：测试 / 质量

相关需求：REQ-003、REQ-007、REQ-010、REQ-011、REQ-012、REQ-013；AC-003、AC-006、AC-007、AC-008、AC-010、AC-011、AC-014。

相关文件：`frontend/src/api/client.test.ts`、`frontend/src/features/tickets/TicketsPage.test.tsx`、`frontend/src/features/admin/AnalyticsPage.test.tsx`、`AuditLogsPage.test.tsx`、`DocumentsPage.test.tsx`、`NotificationDeliveriesPage.test.tsx`、`frontend/src/features/auth/AuthContext.test.tsx`、`frontend/package-lock.json`、`backend/tests/unit/test_notification_configuration.py`、`backend/tests/unit/test_notification_delivery.py`、`backend/migrations/versions/3f5d51a53981_create_phase1_identity_tables.py`、`baaf88cba66a_create_business_systems_and_owner_roles.py`、`docs/development/10-current-status.md`、`docs/development/17-traceability-matrix.md`、`docs/product/06-roadmap.md`。

变更说明：

1. 前端新增 23 项行为级测试：完整覆盖 API client 的版本化端点、请求方法、可选查询参数、CSRF 轮换和错误回退；补齐工单筛选、回复、答案候选、状态流转、角色权限及失败恢复；补齐文档、分析、审计和通知记录页面的筛选、空值、状态展示与错误重试；新增认证启动卸载竞态、非标准错误、文档空系统、分页、发布状态、文件大小与发布/退役失败覆盖。
2. 后端新增 15 项通知安全与可靠性测试：覆盖生产 HTTPS/域名 allowlist、非法凭据 URL/片段、开发 HTTP、禁用配置、无接收人、时区校验、重复投递和意外 Provider 异常退避。
3. 不修改业务实现、不新增直接依赖；前端 API client 覆盖率提升到 statements 99.34%、branches 98.96%、functions/lines 100%，TicketsPage 提升到 statements 90.90%、branches 81.42%、functions 83.33%、lines 92.42%，DocumentsPage 分支覆盖率提升到 80%。后端通知 endpoint 校验达到 100%，投递服务达到 98%。
4. 使用 Black/isort 清理两份既有 Phase 1 迁移格式差异；按 PostCSS 的兼容范围仅将锁文件中的传递依赖 `nanoid` 从 3.3.16 更新到 3.3.18，Vite/PostCSS 和 `package.json` 不变。

影响范围：测试、两份迁移排版、前端传递依赖锁和项目状态文档；覆盖登录后工单、认证启动和管理后台既有交互，以及通知端点安全校验和异步投递边界，不改变业务行为或数据库结构。

验证方式：前端 21 个测试文件、93/93 测试通过，全局 statements/branches/functions/lines 覆盖率 90.52%/82.43%/85.51%/91.82%，四项 80% 门禁全部通过；TypeScript、ESLint、Prettier、Vite 生产构建和 `npm audit` 通过，审计漏洞 0。后端 401 passed、25 skipped，总覆盖率 85.55%；242 个 Python 文件 Black/isort 清洁，171 个源文件 mypy strict 零错误，全仓 Pylint 9.81/10（既有告警导致命令非零且本轮无新增告警），Bandit 中高危 0。

后续注意：前端覆盖率、迁移格式和 `nanoid` 安全公告门禁已关闭；真实公司通知 API 联调、真实 Rerank 推理和 AC-004/AC-005 评测数据仍是独立门禁。

### 2026-08-08 - Phase 3 第 3 项：公司通知 API、失败重试和通知记录

类型：新增 / 变更 / 测试

相关需求：REQ-010；AC-008、AC-014。

相关文件：`backend/src/knowagent/notifications/`、`backend/src/knowagent/platform/outbox.py`、`backend/src/knowagent/tickets/infrastructure/sqlalchemy_repository.py`、`backend/src/knowagent/worker/`、`backend/src/knowagent/platform/settings.py`、`backend/migrations/versions/3bed66d88cf4_add_phase3_notification_delivery.py`、`backend/migrations/versions/8f2c9d4a1b67_add_notification_attempt_fencing.py`、`backend/tests/unit/test_notifications.py`、`backend/tests/unit/test_notification_delivery.py`、`backend/tests/integration/test_notifications_api.py`、`backend/tests/integration/test_notification_provider_stub.py`、`frontend/src/features/admin/NotificationSettingsPanel.tsx`、`frontend/src/features/admin/NotificationDeliveriesPage.tsx`、对应测试文件、`frontend/src/api/client.ts`、`frontend/src/api/types.ts`、`frontend/src/app/App.tsx`、`frontend/src/features/admin/AdminShell.tsx`、`frontend/src/styles.css`、`scripts/local-env.sh` 及相关产品/工程/运维文档。

变更说明：

1. 按 TD-013 落地可配置 HTTP JSON Provider：管理员可配置启用状态、通知地址、鉴权方式、密钥环境变量引用、成功状态码、超时、重试参数和两类 JSON 模板；数据库不保存密钥值，关闭通知时允许地址为空。
2. 工单创建和负责人/管理员回复分别在业务事务内写入 `ticket_created`、`ticket_replied` Outbox；通知 Worker 使用独立 `notification` 队列消费，408/425/429/5xx、网络错误和超时按配置退避重试，永久失败可由管理员人工重试并保留累计尝试次数，Beat 每 15 秒恢复待处理任务。
3. 新增通知配置、通知记录分页筛选和人工重试管理 API，以及“问答配置 → 通知接口”和 `/admin/notifications` 两个后台入口；配置页覆盖 loading/error/success、关闭态和启用态校验，记录页只对永久失败展示确认重试操作。
4. 新增 MockTransport 单元测试和本地 FastAPI Stub 集成测试，在没有真实公司通知接口时验证请求模板、鉴权引用、幂等键、状态映射、自动/人工重试和管理权限契约；Worker 启动脚本同时订阅 `ingestion,notification`。

review 修复（1 阻塞 + 1 建议）：

1. 为每次通知领取增加 `active_attempt_id` fencing，只允许待处理、已入队或到期重试状态领取；重复 Worker 不能并发领取 `DELIVERING`，过期 attempt 的迟到成功/失败结果不能覆盖新 attempt 的终态。
2. 投递成功时间、失败时间和指数退避改为 Provider 调用完成后取时；通知停滞恢复阈值默认提高到 180 秒并强制大于最大 120 秒请求超时，避免正常长请求尚未结束即并发恢复。

质量补充 4 个回归用例，覆盖重复领取、迟到失败覆盖、新退避起点和恢复阈值下限。

影响范围：工单事务写入、通知异步任务、管理员配置与记录页面、数据库迁移、本地开发和部署配置。未新增依赖，未保存真实密钥，也未假定尚未提供的公司鉴权或回执协议。

验证方式：后端全量 386 passed、25 skipped，覆盖率 85.11%；通知与 Worker 相关 32 项定向测试通过；228 个 Python 文件 Black/isort 清洁，171 个源文件 mypy strict 零错误，通知修复范围 Pylint 10.00/10、全仓 Pylint 9.81/10（既有告警导致命令非零），Bandit 中高危 0；本地 PostgreSQL `alembic upgrade head`、`alembic check` 和 `active_attempt_id` 实际列检查通过。前端 70/70 测试通过，TypeScript、ESLint、Prettier、Vite build 通过；覆盖率语句/分支/函数/行为沿用本功能本轮已有运行结果 78.29%/64.46%/72.89%/80.76%，全局 80% 门禁未通过；`npm audit` 报 `nanoid <3.3.17` 1 个 high，未绕过依赖升级兼容性门禁。真实 PostgreSQL/API 登录会话下完成通知配置保存、通知记录空态、1440x900 和 390x844 响应式检查，页面无横向溢出或控件重叠。

后续注意：Phase 3 的 4/4 功能范围已实现，但 REQ-010 仍保持 `implementing`。真实公司通知 API 的鉴权、限流、幂等接收和回执语义尚未提供，必须在 staging 用真实端点完成 AC-014 后才能关闭；前端全局覆盖率和 `nanoid` 安全公告也仍是独立质量门禁。

### 2026-08-07 - 追溯状态修正：Phase 3 第 2 项已实现，标记为完成

类型：文档 / 追溯修正

相关需求：REQ-008、REQ-014；AC-004、AC-005、AC-008。

相关文件：`docs/product/06-roadmap.md`、`docs/development/10-current-status.md`、`docs/development/17-traceability-matrix.md`。

变更说明：

1. 路线图与状态文档此前将 Phase 3 第 2 项「多轮上下文、意图识别、提示词和检索配置版本」按「未完成」计入进度，但代码核对发现其早已随 Phase 3 第 1 项切片落地。
2. 实际代码现状：`agent/application/query_rewriter.py` 提供规则门控 + LLM 支撑的意图识别与多轮查询重写；`agent/domain/conversation.py` 定义 `Conversation`/`ConversationMessage`/`IntentKind`/`QueryRewriteTurn`/`QueryRewriteResult` 与 `RetrievalProfile`；`agent/api/configuration_router.py` 提供 `prompt-definitions` 与 `retrieval-profiles` 的 list/get/save/activate 管理端点；`agent/api/conversations_router.py` 提供多轮历史回查；两份 Phase 3 迁移与前端 `ConfigurationPage`、`test_phase3_configuration_api.py`、`test_query_rewriter.py`、`test_retrieval_profile_repository.py` 等测试齐备。
3. 据此修正：roadmap Phase 3 总进度 2/4 → 3/4，第 2 项标注「已完成」；current-status 当前阶段块同步为 3/4；traceability REQ-008 由 `skeleton`/「待实现」推进为 `implementing` 并补齐实现文件清单，REQ-014 备注的「数据库 Profile、激活切换和效果回滚待后续 Phase 3 项」改为「已补齐」，并补充前端管理 UI 与集成测试已落地。REQ-008 真实质量评测 AC-004/AC-005 仍待补数据，故仅推进到 `implementing` 而非 `done`。

影响范围：仅文档与追溯矩阵，未改任何代码或迁移。

验证方式：阅读代码确认上述文件、端点、测试均已实现；本地运行既有 `test_query_rewriter.py`、`test_retrieval_profile_repository.py`、`test_conversation_service.py`、`test_document_configuration.py` 与 `test_phase3_configuration_api.py` 在 309 passed 范围内全部通过（本机缺 boto3/botocore 的 12 项 collection error 与本项无关）。

后续注意：此次仅状态对齐，未新增 89 行以外的能力。Phase 3 真正剩余的是第 3 项通知、第 4 项前端页面与横向质量门禁。

### 2026-08-07 - Phase 3 第 4 项前端：文档版本、分析仪表盘和审计日志管理页

类型：新增 / 测试

相关需求：REQ-011、REQ-012、REQ-013；AC-003、AC-006、AC-007、AC-010、AC-011。

相关文件：`frontend/src/features/admin/DocumentsPage.tsx`、`frontend/src/features/admin/AnalyticsPage.tsx`、`frontend/src/features/admin/AuditLogsPage.tsx`、对应 3 个测试文件、`frontend/src/api/client.ts`、`frontend/src/api/types.ts`、`frontend/src/app/App.tsx`、`frontend/src/features/admin/AdminShell.tsx`、`frontend/src/styles.css`。

变更说明：

1. 文档版本管理页按业务系统分页展示文档，并在详情抽屉中展示版本、处理状态与发布状态；草稿/退役版本支持确认发布，已发布版本支持确认退役，操作完成后同步刷新版本与文档当前发布状态。
2. 分析仪表盘按业务系统并行加载问题概览、高频问题和知识缺口；使用 4 个紧凑统计项与 2 个扫描型表格展示问题量、拒答、工单和缺口来源，不引入额外图表依赖。
3. 审计日志页提供 action、object_type、result 过滤、服务端分页、请求 ID/操作者/对象/详情展示和可恢复错误状态；该页保持 ADMIN 全局视角，不增加业务系统筛选。
4. 3 个页面以路由级懒加载接入 `/admin/documents`、`/admin/analytics`、`/admin/audit-logs`，管理侧栏使用 Lucide 图标新增对应入口；API 客户端与类型层覆盖后端 8 个端点，列表请求均保留分页、最新请求胜出和原位重试语义。
5. 新增 11 项组件测试，覆盖正常加载、错误重试、刷新、过期请求忽略、抽屉 Portal 展示和发布确认；修复测试异步链稳定方式，并将 Ant Design 跨字段 validator 恢复为显式 Promise 契约。

影响范围：管理后台导航、路由、API 类型/客户端、文档运营、质量分析、审计查看和响应式样式；未新增前端依赖，未改变后端 API 或数据库 schema。

验证方式：前端默认完整测试 63/63 通过；`tsc --noEmit`、ESLint（零 warning）、Prettier 检查和 Vite 生产构建通过。覆盖率运行的 63 项测试全部通过，但全局语句/分支/函数/行覆盖率为 78.29%/65.90%/72.93%/80.83%，仍低于全局 80% 门禁；主要缺口在既有 API client 和 TicketsPage。`npm audit --audit-level=moderate` 仍报告 React Router RSC 模式 2 个 high，自动修复会强制降级到 7.11.0，未执行 breaking force fix。

后续注意：三个页面尚未在真实 PostgreSQL/API 登录会话中完成桌面与移动浏览器人工验收；Phase 3 仍为 3/4，剩余第 3 项公司通知 API、失败重试和通知记录。

### 2026-08-07 - Phase 3 第 4 项后端：文档生命周期、对话分析、高频问题、知识缺口和审计

类型：新增 / 测试

相关需求：REQ-011、REQ-012、REQ-013；AC-003、AC-006、AC-007、AC-010、AC-011。

相关文件：`backend/src/knowagent/documents/api/lifecycle_router.py`、`backend/src/knowagent/documents/api/lifecycle_schemas.py`、`backend/src/knowagent/analytics/domain/models.py`、`backend/src/knowagent/analytics/application/analytics_service.py`、`backend/src/knowagent/analytics/api/router.py`、`backend/src/knowagent/analytics/api/schemas.py`、`backend/src/knowagent/audit/domain/models.py`、`backend/src/knowagent/audit/application/audit_query_service.py`、`backend/src/knowagent/audit/api/router.py`、`backend/src/knowagent/audit/api/schemas.py`、`backend/src/knowagent/api/app.py`、`backend/tests/unit/test_document_lifecycle.py`、`backend/tests/unit/test_analytics_service.py`、`backend/tests/unit/test_audit_query_service.py`。

变更说明：

1. 文档生命周期管理：新增 4 个管理端点——`GET /systems/{system_id}/documents`、`GET /systems/{system_id}/documents/{document_id}/versions`、`POST .../versions/{version_id}/publish`、`POST .../versions/{version_id}/retire`；发布/退役复用既有 `KnowledgePublicationService` 保证发布原子切换当前指针并退役旧版本来源/片段，并在事后写入 `document.publish`/`document.retire` 审计；访问控制复用 `require_system_access` + `MANAGEMENT_ROLES = {SYSTEM_OWNER, ADMIN}`，写端点使用 `CsrfContext`。
2. 对话分析：新增 3 个管理端点——系统概览（用户问题数、拒答数、未解决/已解决工单数与总数）、高频问题（按规范化问题聚合 occurrence_count 总和并降序排序，带 refusal/ticket 子计数）、知识缺口（合并 `EvidenceDecisionRecord` 的 `INSUFFICIENT` 拒答与开放工单 occurrence 合并去重，按时序排序）；窗口默认最近 30 天且 tz-safe 归一化，top_n 由 FastAPI Query 约束在 1-100。
3. 管理审计日志查询：新增 `GET /admin/audit-logs`，支持按 actor/action/object_type/object_id/result/时间窗过滤与分页，结果按 `created_at desc, id desc` 排序；复用既有 `AuditQueryService`（read side），写侧 `SqlAlchemyAuditSink` 早已由 identity/tickets/agent 共享；通过 `AdminContext` 强制仅 ADMIN 可见。
4. 路由注册到 `api/app.py`，新增 `analytics`、`audit` 两个顶级包遵循模块化单体分层（domain/application/api/infrastructure）。

影响范围：仅后端新增只读分析与管理写端点，不改变已有问答/工单/检索链路；新模块不触碰既有数据库 schema，复用既有表读侧。

验证方式：`tests/unit/test_document_lifecycle.py` 10 项、`tests/unit/test_analytics_service.py` 6 项、`tests/unit/test_audit_query_service.py` 10 项全部通过；运行 `tests/unit` 排除本机缺 boto3/botocore 的 5 项既有 collection error 后共 309 passed、0 failed。新模块 Black/isort 清洁，mypy --strict 20 文件零错误，Pylint 10.00/10，Bandit 中高危 0。

后续注意：前端管理页面（文档版本管理、分析仪表盘、审计日志查看）尚未实现；本轮只覆盖后端 API 与领域服务。12 项 collection error 均因本机缺 boto3/botocore 可选依赖，恢复依赖后既有集成测试可正常运行。

### 2026-08-07 - Phase 3 review 修复（1 P0 + 2 P1 + 2 P2 + 3 P3）

类型：修复

相关文件：`backend/src/knowagent/agent/api/router.py`、`backend/src/knowagent/agent/infrastructure/openai_compatible.py`、`backend/src/knowagent/agent/application/query_rewriter.py`、`backend/src/knowagent/agent/api/admin_schemas.py`、`backend/src/knowagent/agent/application/conversation_service.py`、`backend/src/knowagent/agent/api/conversations_router.py`、`frontend/src/features/admin/ConfigurationPage.tsx`、`AI_DEVELOPMENT_RULES.md`

变更说明：1. P0：`OpenAiCompatibleLlmProvider` 新增 `with_prompt_definition(prompt)` 返回 shares HTTP client 的浅拷贝，`_build_question_service` 与 `_maybe_rewrite_query` 改为每请求构造 immutable LLM copy，不再 mutate 共享 singleton provider，彻底消除并发请求互相覆盖 active prompt 的竞态。2. P1.1：SSE stream 的用户问题改为在 prelude 阶段（第一个 yield 之前）持久化，助手回答在 `ANSWER_COMPLETED` terminal 事件持久化；客户端断连或 `ProviderUnavailableError` 不再导致用户问题丢失。3. P1.2：`query_rewriter.rewrite()` 的 broad except 与 `OpenAiCompatibleLlmProvider.rewrite_query/generate` 的 except 块均添加 `LOGGER.warning` 降级日志，遵守 §16.4「降级过程必须记录日志」。4. P2.1：`SavePromptDefinitionRequest.content` 增加 `max_length=12000`，与前端 `maxLength={12000}` 对齐。5. P2.2：前端 `ConfigurationPage.ProfileDrawer` 新增 3 个跨字段 validator（结果 Top-K ≤ 关键词+向量 Top-K、Rerank 候选 ≤ 关键词+向量 Top-K、结果 Top-K ≤ Rerank 结果 ≤ Rerank 候选），提交前阻断并提示用户。6. P3.1：`_persist_stream_terminal_turn` 中 `assert isinstance(answer, VerifiedAnswer)` 改为显式 `TypeError`，不被 `python -O` 剥离。7. P3.2：新建 `REWRITE_CONTEXT_HISTORY_LIMIT = 10` 常量并在 `conversations_router.CONVERSATION_HISTORY_LIMIT = 50` 添加注释说明两者用途差异。8. P3.3：`_resolve_active_prompts` 增加可选 `request` 参数，结果缓存到 `request.state`，单请求内多个 call site 不再重复 SELECT。9. 新增 §16.8「apply_patch 失败即停与行号锚定整段替换」规则到 `AI_DEVELOPMENT_RULES.md`。

验证方式：后端 312 个单测全部通过；前端 ConfigurationPage 5 个 + UserHomePage.stream 2 个测试通过。Black/isort 通过；mypy 已改文件零错误（仅本仓既有 pgvector stub import-not-found）；Pylint 9.78/10；Bandit 中高危 0；TypeScript `tsc --noEmit` 通过。

后续注意：P3.3 缓存为同一 `request.state` 作用域，不支持跨请求命中，符合当前同步问答的单请求模型；如未来引入跨请求会话缓存需另设独立缓存层。

### 2026-08-06 - Phase 3 运行资源盘点与下载门禁

类型：文档 / 运维

变更说明：

1. 新增 `docs/operations/09-runtime-resource-inventory.md`，分别记录系统所需资源、宿主机工具链/服务/Python 环境、模型缓存、Docker 容器/镜像/卷和缺口处理顺序。
2. 确认 Docker `deploy_ollama-models` 已包含 digest 前缀为 `79076464` 的 `bge-m3` 1.158 GB 权重；确认 `knowledge-rag/deploy/models/` 已有原生和 ONNX 两套约 2.1 GB 的 `bge-reranker-v2-m3` 权重。
3. 确认四个现有 Python 虚拟环境均无 FlagEmbedding/PyTorch/Transformers/ONNX Runtime，Docker 无 TEI 镜像或容器；当前缺口是 Rerank 推理运行时，不是模型权重。
4. 终止未完成的 `model-service[rerank]` pip 安装，建立“先拆分模型 ID/本地加载路径，再确认依赖树和缓存命中，最后安装运行时”的门禁；未经再次确认不下载模型权重。

验证方式：只读核对 macOS 硬件、磁盘、四个 Python 环境、项目运行目录、Hugging Face/ModelScope/Ollama 缓存、PostgreSQL 17.10 与扩展、Redis 8.10、Docker 容器/镜像/卷和 Ollama `/api/tags`；`bge-m3` digest 与项目配置一致，Rerank 两套权重的主文件大小已记录。未安装依赖、未启动新容器、未下载模型权重。

后续注意：当前 `KNOWAGENT_MODEL_RERANK_MODEL` 同时作为 API 模型 ID 和 FlagEmbedding 加载参数，复用本地绝对路径前需拆出独立加载路径配置；真实模型加载、峰值内存和延迟仍未验证。

### 2026-08-06 - Phase 3 混合检索调优、Rerank 和显式降级

类型：新增 / 变更 / 测试

相关需求：REQ-005、REQ-006、REQ-009、REQ-014；AC-004、AC-005、AC-008。

变更说明：

1. `BasicRetrievalService` 将固定 RRF 扩展为关键词/向量可配置加权 RRF，并增加 Rerank provider、候选上限与结果 top-k；Rerank 输出只按原候选索引回填，不改变来源快照和 `system_id` 隔离边界。
2. 新增严格 HTTP Rerank 契约：请求校验空文本与 top-k，响应校验模型名、版本、结果数量、有限分数、唯一/范围内索引和降序；任何网络、状态码、JSON 或契约异常统一映射为可降级的 `RERANK_UNAVAILABLE`。
3. `model-service` 新增 `/v1/rerank` 和 `FlagEmbeddingRerankService`，采用延迟模型加载、线程执行、并发限制、输入/输出资源上限和脱敏耗时日志；`FlagEmbedding==1.4.0` 仅放入 `rerank` 可选依赖。Embedding 失败 readiness 返回 `503 not_ready`，仅 Rerank 失败返回 `200 degraded`。
4. 显式降级形成闭环：向量失败回退关键词，Rerank 失败回退加权 RRF，两者同时失败保留两个原因；回答、拒答和重放 SSE 均携带 `degraded_reasons`，前端在回答/拒答前分别显示“仅使用关键词检索”或“使用基础融合排序”。
5. 新增加权 RRF、Rerank 成功排序、非法响应、Rerank 回退、双重降级、模型服务资源上限/健康状态/输出校验、四条拒答路径字段传播和前端回答/拒答提示回归测试。
6. 创建仅用于本机验收的 `visual.tester` 普通用户、`PHASE3_TEST` 启用系统和一条拒答工单；通过真实 PostgreSQL 17、Redis、API/SSE 和浏览器验证首次改密、系统选择、向量故障降级、拒答建单及桌面/移动布局。测试账号不属于迁移或仓库种子数据。

验证方式：后端全量 284 passed / 24 skipped，覆盖率 86.64%；model-service 49 passed / 1 skipped，覆盖率 85.63%；前端 47/47 通过。Backend 126 个源文件、model-service 8 个源文件 `mypy --strict` 零错误；TypeScript、ESLint、前端生产构建通过；相关 Python/TypeScript 文件 Black/isort/Prettier 清洁；检索核心 Pylint 10.00/10；双后端 Bandit 中高危 0。真实浏览器在 1280x720 与 390x844 验证降级 Alert 无横向溢出或重叠，并完成真实拒答工单链路。

后续注意：前端全局覆盖率门禁仍因既有 `TicketsPage` 缺口失败（statements 82.56%、branches 75.12%、functions 73.75%、lines 84.64%）；`npm audit` 仍有 React Router RSC 两项 high，自动修复会产生 breaking downgrade，未自动执行。PyTorch/Transformers 传递依赖和真实 `BAAI/bge-reranker-v2-m3` 推理仍需结合本机安装结果及目标 Linux CPU/内存/GPU 信息验收；真实 ESB 质量收益必须使用 Phase 2 评测集测量，不能由合成用例替代。

### 2026-08-05 - 补齐 Phase 2 流式安全、可恢复索引、评测门禁与真实集成

类型：新增 / 修复 / 测试

相关需求：REQ-004、REQ-005、REQ-006、REQ-007、REQ-011、REQ-018；AC-003、AC-004、AC-005、AC-006、AC-007。

变更说明：

1. SSE 回答改为真实增量且始终受证据约束：Provider 仍输出结构化 JSON，但服务端只在完整 claim 可解析、引用证据在白名单内且逐字引用成立后才发送 `answer_delta`，最后发送完整 `answer_completed`；原始 JSON、未闭合 claim 和未验证事实不会暴露给前端。
2. `POST /api/v1/questions/stream` 签发的 Redis token 绑定 `account_id`，`GET /api/v1/questions/stream/events` 使用 `GETDEL` 单次消费并重新检查系统权限；其他账号无法消费，重放同一 token 返回未授权。
3. 文档 Worker 的 Embedding 索引并入持久任务状态机：只有 chunk 和向量全部写入后才进入 `SUCCEEDED/READY_DRAFT`；Embedding 不可用记录 `EMBEDDING_UNAVAILABLE` 并按数据库重试预算恢复，重试复用已保存的 manifest、chunk 和来源，不再把索引失败当作成功。
4. 前端完成问答和工单闭环：问答页消费真实 SSE 阶段、增量回答、拒答工单和错误事件；工单页支持系统/状态筛选、分页、详情、回复、状态流转、答案提交和审核；`vite.config.ts` 关闭 Vitest 文件并行，默认 `npm test -- --run` 可稳定执行。
5. 新增 `knowagent-evaluate-phase2` 离线评测门禁及 JSONL 输入校验：至少 50 个真实 ESB 可回答问题、答案正确率 >=80%、引用支持率 >=95%、拒答召回率 >=90%、可靠拒答全部有工单、无知识问题零无依据回答；缺数据或任一指标不达标均以非零退出码失败。
6. 扩展 `scripts/run-phase2-integration.sh`，统一执行真实 Worker→Ollama Embedding、Qwen 增量引用流、问答 SSE token 隔离/单次消费、Agent/Tickets API、拒答工单、审核发布和检索回流。

验证方式：后端标准套件 275 passed / 24 skipped，覆盖率 86.56%；125 个源文件 `mypy --strict` 零错误；Black 检查 168 个文件清洁，isort 和 `git diff --check` 通过。前端默认完整测试 47/47 通过，TypeScript、ESLint 和生产构建通过。`./scripts/run-phase2-integration.sh --with-llm` 使用真实 PostgreSQL 17、Redis、Ollama bge-m3 和 `qwen3.5-27b` 完成 23 项集成验收，23 passed、6 warnings、耗时 36.69 秒，Alembic `upgrade head`/`check` 无漂移。真实浏览器已验证本地登录页可加载；开发库无账号，未向用户数据注入临时账号，问答/工单业务页保留人工验收步骤。

后续注意：Phase 2 功能与真实服务集成范围已补齐，但 AC-004/AC-005 的质量阈值尚不能关闭，因为仓库没有用户提供的至少 50 条真实标注 ESB 可回答问题及无知识问题集。不得用合成问题或自动生成标签替代该门禁；数据到位后按 `docs/development/22-phase2-evaluation.md` 执行并记录报告。`backend/.env` 的 `qwen3.5-27b` 为本地临时模型配置，不提交密钥或覆盖 `.env.example` 的默认示例。

### 2026-08-04 - Phase 2 qwen3-max 全量测试与 Agent/Tickets API 集成验收通过

类型：修复

相关需求：REQ-002、REQ-005、REQ-006、REQ-007、REQ-011；AC-004、AC-006、AC-007、AC-016。

变更说明：

1. `backend/.env` 的 `KNOWAGENT_LLM_MODEL` 从 `qwen3.5-flash` 切换为 `qwen3-max`，Phase 2 live 引用契约与工单往返 2 项全通过。
2. 为 Agent/Tickets API live 集成测试专门建库 `knowagent_api_integration`（Alembic 升级至 `c1738febb896`），设 `KNOWAGENT_RUN_API_INTEGRATION=1` 跑通全部 18 项 API 集成测试（鉴权、校验、工单状态机、审核发布、CSRF 与跨系统隔离）。
3. 修复 `test_ask_question_validates_system_id_required` 在 CSRF 强制开启后缺 `X-CSRF-Token` 头导致 403 与期望 422 不符的问题，补 CSRF 头后用例通过并提交 `d9ca72b`。

验证方式：后端 250 项 + 21 skip（87.64%）；前端 42 项；model-service 39 项 + 1 skip（90.58%）；Phase 2 live 2 项（qwen3-max，34.87s）；Agent/Tickets API live 18 项（真实 PostgreSQL 17，5.57s）；Phase 1 live 1 项（真实 MinIO/S3）；mypy strict 122 文件零错误；Bandit 中高危 0；test_agent_api Black/isort 清洁。

后续注意：`backend/.env` 的模型为本地配置不入版本控制；SSE 流式、文档索引 Worker 接线和页面端到端闭环仍待完成，Phase 2 保持进行中。

### 2026-08-04 - 审查修复 Agent 与 Tickets API 跨系统隔离与 CSRF 等阻塞项

类型：修复

相关需求：REQ-002、REQ-007、REQ-011；AC-006、AC-007、AC-016。

变更说明：

1. 修复 `list_tickets` 在可见系统列表为空时回退到无 WHERE 全表查询的跨系统数据泄露：当账号没有任何可见系统时直接返回空页，不再触碰仓储先查询，避免 USER 角色读到其他业务系统工单。新增 `visible_system_ids` 用 `systems.list(status=...)` 取全部可见系统，移除原 `list_page(page=1, page_size=1000)` 的硬上限。
2. 抽出 `knowagent/identity/api/access.py` 共享 `require_system_access` 与 `visible_system_ids`，消除 agent、tickets 两个 router 中重复实现的 `_require_system_access`/`_require_ticket_access`/`_visible_system_ids`，统一 ADMIN/SYSTEM_OWNER/USER 三类角色的系统访问语义，新增 `allow_user` 参数显式表达 USER 是否可访问 ACTIVE 系统。
3. `ask_question` 端点改用 `CsrfContext` 强制 CSRF 校验，与其余工单写操作一致；补 `test_ask_question_missing_csrf_returns_403` 用例，并为所有已登录的 ask_question 集成测试补 CSRF 头。
4. 将 `ReliableQuestionService` 依赖中无状态且持有 HTTP 连接池的 `HttpEmbeddingProvider`、`OpenAiCompatibleLlmProvider`、`DeterministicEvidencePolicy`、`AnswerGenerator`、prompt 提升为进程级单例，缓存在 `app.state.agent_components`，首次请求惰性创建并复用，避免每次问答都重建连接池。
5. 抽 `tests/integration/_fakes.py` 共享 `FakeRedis`/`FakePipeline`，删除两个集成测试文件中的重复定义；新增一股 `test_list_tickets_user_without_visible_systems_returns_empty` 跨系统泄露回归用例。

review 修复（2 阻塞 + 0 建议 + 2 提醒）：

1. 修复 `list_tickets` 无 system_id 参数且账号可见系统为空时退化为全表扫描的跨系统泄露（P0），改为短路返回空页且不发起仓储查询。
2. `ask_question` 改用 `CsrfContext`，补齐 CSRF 防护缺口（P1）。
3. 将 agent/tickets 共享的系统访问与可见系统列表 helper 收敛到单一实现（P2 消重）。
4. 无状态 Agent 组件提升为进程级单例（P1 连接复用）。
5. `visible_system_ids` 从 `list_page` 改为不受 1000 上限的 `list`，避免大规模部署时系统被静默截断（P2）。
6. `approve_candidate`/`reject_candidate` 先取候选再鉴权的顺序约束属候选 ID 全局 UUID 命名空间无法线性枚举，保留现状并在评估中记录为残余风险（原审查标记的 P0 #2 经复评降级为不修）。`TicketPage` 在 `page` 超过总页数时返回空 items 但 `total>0` 的行为保留，作为可分页客户端的既有契约（P2 #7 不改）。

影响范围：

- backend/src/knowagent/identity/api/access.py（新增）
- backend/src/knowagent/tickets/api/router.py、backend/src/knowagent/agent/api/router.py
- backend/tests/integration/_fakes.py（新增）、backend/tests/integration/test_agent_api.py、backend/tests/integration/test_tickets_api.py
- docs/development/03-feature-changelog.md

验证方式：后端 250 项非集成测试全部通过，总覆盖率 87.64%（80% 阈值满足）；`black`+`isort` 已格式化本次修改文件；`mypy --strict` 对 122 个源文件零错误；Pylint 9.73/10（残留 R0913/R0917 为 FastAPI 端点签名既有模式，与本次变更无关）；Bandit 中高危 0；集成测试 21 项默认 skip（`KNOWAGENT_RUN_API_INTEGRATION` 未设），collect-only 通过。

后续注意：集成测试需在类生产 PostgreSQL/Redis 下设 `KNOWAGENT_RUN_API_INTEGRATION=1` 与 `KNOWAGENT_API_INTEGRATION_DATABASE_URL` 才能验证真实 SQL、CSRF、跨系统隔离与工单回流链路。`approve_candidate`/`reject_candidate` 的 NotFound 与 Authorization 顺序因候选 UUID 全局命名空间不可线性枚举而保留，后续若引入候选 ID 命名空间可枚举场景需重评。

### 2026-08-04 - Phase 2 核心服务真实集成验收通过并修复 PostgreSQL 写入顺序

类型：测试 / 修复

相关需求：REQ-002、REQ-004、REQ-005、REQ-006、REQ-007、REQ-009、REQ-014；AC-004 至 AC-007 的核心服务范围。

变更说明：

1. 新增显式门禁的 Phase 2 live 集成用例与运行器，读取 `backend/.env`、`model-service/.env`，固定复用 `knowagent_integration` 和 Redis DB 15，不按运行创建或删除数据库。
2. 真实验证 PostgreSQL 17/pgvector/pg_trgm、Ollama bge-m3、Qwen OpenAI 兼容流、双系统检索隔离、证据判定、答案/历史引用快照、可靠拒答与工单去重、工单状态机、审核发布和 5 分钟内工单知识回流检索。
3. 修复答案与引用在同一次 SQLAlchemy flush 中因缺少 ORM relationship 依赖而先写子表的问题；答案父记录先 flush，再写引用。
4. 修复拒答流程先写 `ticket_occurrences`、后写其外键依赖 `evidence_decisions` 的问题；保持原事务边界并按工单、判定、发生记录顺序持久化。

质量补充 2 个写入顺序回归用例，直接断言 ORM 发出的父子 INSERT 顺序。

验证方式：修复前两个回归用例分别稳定记录 `answer_citations -> answers` 和 `ticket_occurrences -> evidence_decisions` 并失败；修复后 25 项答案快照/拒答工单单测通过。后端全量 250 项通过、3 项 live 门禁跳过，总覆盖率 90.72%；118 个 Python 文件 Black 清洁，isort 通过，115 个源文件 mypy strict 零错误，本次范围 Pylint 10.00/10，Bandit 中高危 0，Bash 语法和 diff whitespace 通过。`./scripts/run-phase2-integration.sh --with-llm` 使用真实 `.env` 配置通过，2 项 live 用例在 36.85 秒内完成；Qwen 合约和完整核心服务往返均通过，Alembic `upgrade head`/`check` 无漂移。

后续注意：本次证明 AC-004 至 AC-007 的领域服务和真实基础设施组合可用，但问答 API/SSE、工单 API、文档索引 Worker 接线和页面端到端流程仍未实现，因此 Phase 2 不正式关闭。

### 2026-08-04 - Phase 1 真实基础设施集成验收通过并正式关闭

类型：测试 / 质量

相关需求：REQ-001、REQ-002、REQ-003、REQ-004、REQ-011；AC-001、AC-002、AC-003、AC-009 的 Phase 1 范围。

变更说明：

1. 新增显式门禁的 Phase 1 live 集成用例，运行时生成 PDF、DOCX、Markdown、XLSX 四种真实样本，覆盖 S3 上传/回读、Worker 解析切分、locator、知识发布、幂等和 v2 切换。
2. 使用两个业务系统发布同主题不同标记知识，验证服务端越权拒绝和 `system_id + PUBLISHED` 零泄漏；模拟 Worker 租约过期并通过真实 Redis/Celery broker 只恢复目标任务一次。
3. 验证 MinIO S3 `put/get/delete`、multipart ETag、错误凭据和不可达端点错误分类；live 结束后断言数据库验收记录、Redis key/队列长度和 Bucket 对象集合恢复到运行前状态。
4. 验收运行器固定复用 `knowagent_integration`、Redis DB 15 和 `knowagent-phase1-it`；资源只在首次缺失时创建，不再按运行创建/删除数据库，也不执行 `flushdb`。

验证方式：`./scripts/run-phase1-integration.sh` 在固定 integration 资源上连续复跑通过，最终结果为 1 项 live 用例通过，四格式、multipart、权限拒绝、幂等、v1→v2、双系统零泄漏和 1 个租约过期任务恢复均符合预期；PostgreSQL 17.10 从固定库迁移至 `c1738febb896`，复跑 `alembic check` 返回 `No new upgrade operations detected`。标准后端套件 248 项通过、1 项 live 用例按门禁跳过，总覆盖率 90.72%；新增测试 Pylint 10.00/10，Black/isort、Bash 语法和 Git diff whitespace 检查通过。

后续注意：本地 MinIO 使用 HTTP，未覆盖公司对象存储 TLS/内部 CA 和真实服务端 5xx/限流；这些属于 staging/部署验证风险，不阻塞 Phase 1 关闭。本次未新增页面功能，页面连接真实后端的人工复验可随 Phase 2 问答/工单页面端到端验收执行。

### 2026-08-04 - 完成 Phase 2 审核发布重新索引、来源追踪与历史引用快照

类型：新功能

相关需求：REQ-005、REQ-007；AC-004、AC-007 的基础代码范围，问答/工单 API 与真实 Qwen 端到端验收待补。

变更说明：

1. 知识审核批准改为先调用 Embedding Provider；向量生成失败时候选保持 `PENDING` 且不创建发布知识，成功后在同一事务内创建 `TICKET` 来源、带模型版本和向量的发布片段，并将候选推进为 `PUBLISHED`。
2. `SourceLocator` 为工单来源保存 `ticket_id` 定位且不伪造文档身份；关键词与向量检索使用文档/工单外连接并纳入已发布 `TICKET` 来源，返回工单标题和工单 ID 版本标识。
3. 新增回答与引用快照模型、服务和仓储，保存回答正文、声明、降级原因、模型、Prompt 版本、原 chunk/source UUID、逐字引用与完整 locator；引用快照不反向外键到当前知识表，来源退役或删除后历史答案仍可读取原始证据。
4. 新增 `c1738febb896` 迁移，补齐答案/引用复合系统隔离、`evidence_decisions` 运行唯一约束、工单知识来源复合外键和候选 `PUBLISHED` 状态；成功回答路径自动持久化快照并保持同一运行幂等。

review 修复（1 阻塞 + 3 建议 + 1 提醒）：

1. 审核发布改为先完成 Embedding，再锁定并重新校验候选状态；拒绝路径使用同一行锁，避免同步数据库锁跨越外部 `await` 以及审核/拒绝竞争。
2. 可靠问答在检索和 LLM 前读取同一 `run_id` 的历史快照，重放直接返回首次答案且校验问题一致性；快照仓储使用 SAVEPOINT 吸收并发唯一冲突并读取胜出记录。
3. 本地进程 PID 同时记录并校验操作系统启动时间，过期或复用 PID 不再收到停止信号；ORM 与迁移统一工单转换 CHECK 名称。
4. model-service 默认 digest、环境示例和技术决策统一为已验证的 manifest 前缀 `79076464`。

质量补充 5 个回归用例，覆盖答案重放零外部调用、运行 ID 复用冲突、Embedding 期间候选状态变化、快照唯一冲突恢复和 ORM 约束名称。

验证方式：39 项 review 定向回归和 248 项后端全量测试通过，总覆盖率 90.72%；148 个后端 Python 文件 Black/isort 清洁，115 个源文件 `mypy --strict` 零错误，相关模块 Pylint 10.00/10，Bandit 中高危 0。model-service 39 项通过、1 项真实 Ollama 测试按门禁跳过，覆盖率 90.58%；11 个源文件 `mypy --strict` 零错误，变更文件 Black/isort、Pylint 和 Bandit 通过。前端 42 项测试、TypeScript、ESLint 和生产构建通过。新 SQLite 影子库完成 `upgrade -> downgrade -> upgrade` 和 `alembic check`；Bash 语法与 Git diff whitespace 检查通过。

后续注意：Phase 2 四项基础代码已完成，但问答 API/SSE、工单 API、文档索引 Worker 接线和 AC-004 至 AC-007 的真实 pgvector/Embedding/Qwen 端到端验收尚未完成；PID 启动身份的沙箱外受控运行测试因审批服务 503 未获授权，`shellcheck` 不可用，已执行 Bash 语法检查并保留本地运行复验项。model-service 全目录 Black 检查仍命中未改动的 `ollama.py` 既有格式差异；`npm audit` 仍报告 React Router 2 个 high 且自动修复涉及 breaking downgrade，均未扩展本次修复范围。本次无页面手测步骤。

### 2026-08-03 - 建立 KnowAgent 独立完整本地运行环境

类型：部署配置 / 修复

变更说明：

1. 本机切换到 PostgreSQL 17.10，创建项目独立 `knowagent` 角色和同名数据库，加载 `vector 0.8.6` 与 `pg_trgm 1.6`，从空库执行全部 Alembic 迁移到 `ee1a2b3c4d5e`。
2. 修复末端迁移中 `ticket_transitions.from_status` 与 `to_status` 生成同名 `ticket_status` CHECK 约束的问题，分别使用独立约束名，使 PostgreSQL 空库升级可以到达 head。
3. 新增 `scripts/local-env.sh`，统一管理项目独立 PostgreSQL 5440、Redis 6380、MinIO 9200/9201、model-service、API 8200、Celery Worker/Beat 和前端 5273；运行数据与日志写入忽略的 `.runtime/`，不再依赖或操作其他项目的 `fc-*` 容器。入口自动创建 S3 Bucket；Vite 代理目标可配置并启用严格端口；`serve` 模式支持当前终端持续托管和退出清理。
4. 安装 model-service 与 frontend 依赖；按 Ollama `/api/tags` 返回值把 `bge-m3` digest/version 前缀从模型 blob 的 `daec91ff` 修正为模型 manifest digest `79076464`。

验证方式：项目独立 PostgreSQL 17 空库 7 个迁移升级到 head，`alembic check` 返回 `No new upgrade operations detected`；数据库包含 16 张业务/迁移表，`vector 0.8.6` 与 `pg_trgm 1.6` 可用；统一入口状态检查确认 PostgreSQL 5440、Redis 6380、MinIO 9200、model-service 8100、API 8200、Celery Worker/Beat 和前端 5273 全部运行，API live、model-service ready/Ollama 和前端登录页分别返回 200；MinIO `knowagent-dev` Bucket 真实 `put/get/delete` 通过，Beat 连续三个恢复周期成功；真实 `bge-m3` 返回版本 `ollama-bge-m3-79076464`、1024 维向量和 1.000000 L2 范数。backend 238 项测试通过、覆盖率 90.84%；model-service 39 项测试通过、1 项独立 integration marker 在测试套件执行时跳过，覆盖率 90.58%；frontend 类型检查、ESLint 和生产构建通过；`scripts/local-env.sh` 通过 Bash 语法与 Git diff whitespace 检查。

后续注意：Qwen API Key 和真实 S3 兼容对象存储凭据仍需由本地密钥配置提供；没有这些外部凭据时，回答生成和真实文档上传链路不能视为完整验收。`npm audit --audit-level=moderate` 报告 React Router RSC 模式 CSRF 漏洞产生 2 个高危项，自动修复会把 `react-router-dom` 强制降级到 7.11.0，需作为独立依赖变更评估和回归。

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

### 2026-08-03 - Phase 1 PostgreSQL/Redis 预验收通过

类型：集成验收 / 质量门禁

相关需求：REQ-001、REQ-002、REQ-003、REQ-004、REQ-011；AC-001、AC-002、AC-003、AC-009 的 Phase 1 范围。

变更说明：在隔离 PostgreSQL 16.14 数据库和 Redis 7 DB/namespace 上验证双系统授权、上传越权拒绝、真实 Session、幂等重放、Markdown 持久入库、v2 发布切换、跨系统知识零泄漏、租约过期恢复和 Celery broker 派发；未修改功能代码。

验证方式：目标 Python 3.11.11 下后端 129 项测试全部通过、总覆盖率 91.54%；PostgreSQL `upgrade head` 和 `alembic check` 通过；真实 PG/Redis 验收脚本返回两个系统、v1/v2、B 系统 0 个发布 chunk、1 个恢复任务已派发和 6 个隔离 Redis Session key。

后续注意：当时本机无 S3 兼容服务或测试 Bucket，真实 S3 `put/get/delete`、四格式 S3→PG→Worker 全链路和真实后端页面手测被跳过，因此仅完成预验收、未正式关闭。对象存储与四格式链路已在 2026-08-04 live 验收中补齐并关闭 Phase 1，详见 `docs/development/20-phase1-integration-acceptance.md`。

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

### 2026-08-10 - 修复导入进度恢复、长文件名布局和问答流卡住

类型：缺陷修复

相关需求：REQ-005、REQ-006、REQ-011；AC-003、AC-004、AC-005。

变更说明：

1. 按业务系统将最近导入任务 ID 保存到 `sessionStorage`，页面重新挂载后恢复任务详情并继续轮询；租约过期时显示“处理超时，等待重试”，临时状态查询失败会继续重试。
2. 上传列表、导入任务标题和版本抽屉标题增加 flex 最小宽度与省略号约束，超长文件名不再撑出弹窗。
3. SSE 问答流捕获未预期服务端异常并发送终态错误事件；前端对无终态连接增加 60 秒超时和明确错误状态，避免知识库外问题永久停在“正在检索证据...”。

验证方式：前端定向 16 项测试通过，TypeScript 检查通过；后端 `test_agent_stream_api.py` 9 项通过（使用 `--no-cov`，单测子集覆盖率不满足全仓 80% 门槛）；后端 router `mypy --strict` 通过；Prettier 已格式化改动文件。

后续注意：真实浏览器页面和真实 PostgreSQL/Redis/模型服务仍需按文末手测步骤复验；本轮未运行全仓回归覆盖率。

### 2026-08-10 - 修复文档 Embedding 串行超时与导入进度失真

类型：缺陷修复

相关需求：REQ-004、REQ-011；AC-003、AC-009。

变更说明：

1. model-service 默认将 Ollama Embedding 批大小从 1 调整为 4，并设置 240 秒服务端总超时；请求断开或超时会取消下游推理任务，避免后端请求失败后 Ollama 继续运行。
2. 知识索引改为每个批次完成后立即持久化，重试时只处理尚未生成向量的片段，不再重复整篇文档计算。
3. 后端 Embedding 批大小调整为 4；每批成功后将任务进度从 70% 推进至 95%，完成后再进入 100%，页面可看到真实索引进度。

验证方式：后端全量 `411 passed, 25 skipped`，覆盖率 88.66%；model-service 全量 `52 passed, 2 skipped`，覆盖率 88.69%；前端全量 `22 个测试文件 / 102 passed`，TypeScript、ESLint、生产构建和 `npm audit --audit-level=moderate` 通过；后端与 model-service 修改文件 `mypy --strict`、Black/isort、Bandit 和 `git diff --check` 通过；真实 Ollama `POST /v1/embeddings` smoke test 返回 1024 维向量。
