# Current Status

本文档用于跨对话、跨开发者、跨 AI 助手接续项目。每次阶段性暂停、切换对话、完成重要功能、遇到阻塞或准备交接时，都必须更新。

## 1. 快照时间

```text
更新时间：2026-08-03
更新人/助手：Codex
当前分支：master
远程仓库：git@github.com:Kanna-02/knowAgent.git
当前环境：Python 3.11.11；PostgreSQL 16.14；Redis 7；Node.js 24.16.0；本地 Ollama 0.3.14 + bge-m3
```

## 2. 当前阶段

```text
当前阶段：Phase 2 问答与工单闭环（Phase 1 真实 S3 补验并行待办）
阶段目标：系统隔离检索、带引用回答、可靠拒答、内置工单和审核回流
当前任务：Phase 2 第 3/4 项，工单分派/处理/追加/关闭/重开/审核入库（基础代码完成，待补工单 API 路由、检索纳入 TICKET 来源与端到端验收）
任务状态：前三项基础代码与自动化验证完成；第 2 项迁移往返、真实 pgvector/Qwen 组合集成、问答 API/SSE、工单 API 路由、检索层纳入 TICKET 来源与第 4 项待补
```

## 3. 已完成

1. 初始化需求、路线图、前端设计、开发规则和追溯矩阵。
2. 完成 `knowledge-rag` 跨项目资产盘点。
3. 已确认 TD-001 至 TD-011，包括全 Python、PostgreSQL 混合检索、独立模型服务、Celery、双入口 Redis Session、格式专用解析、S3 兼容对象存储、原生 Linux 部署、LangGraph 编排和应用框架版本基线。
4. 已同步双端登录、统一账号体系、用户批量导入、管理员后台新增和首次强制改密，并完成跨文档一致性检查。
5. 已确认四类文档解析器边界、统一 `SourceLocator`、结构化切分约束和扫描 PDF 显式失败策略。
6. 已确认 systemd + Nginx + 版本化发布目录，以及向后兼容数据库迁移和应用回滚边界。
7. 已确认 LangGraph 只负责编排、PostgreSQL 保持事实源，并区分知识缺口拒答与系统故障。
8. 已确认 FastAPI + SQLAlchemy + React/Ant Design 技术包，并按用户决定将后端运行时调整为 Python 3.11。
9. 模块化单体、Celery Worker、独立 model-service、类型化 API/Provider、数据模型、核心数据流、systemd/Nginx 拓扑和降级策略已通过架构确认。
10. 已补齐后端、模型服务和前端的依赖管理、类型检查、Lint、格式化和测试覆盖配置；npm 锁文件已生成。
11. 18 项需求已填充实现模块并从 `pending` 推进为 `skeleton`。
12. REQ-001 已完成：双登录入口、统一账号认证、用户批量导入、管理员后台新增、首次改密、三角色 RBAC 和 SSO 禁用适配边界均已落地。
13. Alembic 账号/审计迁移、Redis Session/CSRF、会话撤销、登录限流、最后管理员保护和只追加审计已实现并通过自动化测试。
14. 用户/管理员登录、首次改密、用户成功页和管理员账号页已构建；管理路由已拆包。
15. 已修复认证切片评审发现的并发管理员保护、失败限流、CLI/摘要校验、请求 ID、前端认证竞态和覆盖率门禁问题。
16. REQ-002 的系统管理与选择基础切片已完成：业务系统创建、编辑、启停、负责人替换/追加语义和可见系统查询已实现，系统标识统一规范化并保持唯一；知识/检索强隔离待后续模块实现后完成 AC-002 验收。
17. `business_systems` 与 `account_system_roles` ORM/迁移已落地；负责人账号必须为有效 `SYSTEM_OWNER`，当前用户响应返回类型化系统角色映射。
18. 管理后台已新增业务系统表格、编辑/启停和负责人配置抽屉；用户问答首页要求显式选择启用中的业务系统。
19. 已修复系统切片评审问题：负责人映射变更撤销旧 Session，管理员系统列表服务端分页，负责人候选支持搜索和独立重试，普通用户不接收负责人详情，编辑表单不复用旧说明。
20. REQ-003 的 Phase 1 基础切片已完成：双端复用响应式壳层，支持桌面侧栏、移动抽屉、当前路由状态、独立退出入口和路由级懒加载。
21. 已新增统一 loading/empty/error 反馈、API 请求追踪 ID、列表与系统选择原位重试，以及不暴露内部异常的应用错误边界。
22. 已完成 REQ-003 评审修复：管理列表忽略过期请求、重试期间禁止重复提交，工作区在 `<1024px` 使用抽屉导航并通过高 DPI 临界视口验证。
23. 已实现统一 `SourceLocator`，所有格式均绑定文档、版本和原始块序号，并按 PDF 页码/坐标、Word 标题与段落/表格、Markdown 标题与源行、Excel 工作表与单元格范围做严格联合校验。
24. 已实现 PyMuPDF、python-docx、markdown-it-py、openpyxl 四个隔离解析适配器及 registry；扫描/空 PDF 标记 `OCR_REQUIRED`，旧格式、损坏、加密、编码和资源超限均使用稳定错误码。
25. 已实现结构感知 chunker：不跨 PDF 页、标题路径、工作表或表格边界，超长块按预算拆分，表格分组重复表头，每个 chunk 保留完整 locator 集合。
26. 已完成 REQ-004/REQ-005 评审修复：中文与表头严格遵守 chunk 预算，Markdown 表格使用 AST 精确源行，locator 格式内组合严格校验，损坏 OOXML 统一错误，解析限制配置化并改为同步 worker 契约。
27. 已实现 S3 兼容对象存储适配器，支持受控 TLS/CA、multipart、连接/读取超时和 SDK 有限重试；凭据仅从环境读取并从配置对象 repr 隐藏。
28. 已实现 `documents`、`document_versions`、`ingestion_jobs` 持久模型和迁移，以及上传/查询/人工重试 API；数据库事实记录幂等键、任务/版本状态、阶段进度、尝试次数、租约、派发和错误信息。
29. 已实现 Celery 入库 Worker 与 Beat 恢复扫描：消息只携带 `job_id`，任务按数据库租约领取，解析与切分 manifest 使用确定性对象 key；自动退避重试、耗尽失败、人工重置预算和进程重启恢复均由 PostgreSQL 状态机驱动。
30. 已完成持久入库 review 修复：Worker 写入使用 owner/attempt 租约 fencing，解析完成停在 `CHUNKED`，非法重试返回稳定 409，API/Worker 共用同一 Broker 配置，安全布尔值严格解析，幂等键按账号+系统隔离，审计失败执行对象补偿。
31. 已完成文档多版本上传：现有上传接口可带 `document_id` 创建 v2+，版本号按逻辑文档递增，跨系统文档 ID 按不存在处理。
32. 已新增 `DRAFT/PUBLISHED/RETIRED` 独立发布状态、文档当前发布指针、`knowledge_sources` 和 `knowledge_chunks`，处理状态与发布状态不再混用。
33. 已实现发布/退役事务：新版本发布会原子切换当前指针并退役旧版本、来源和片段；发布查询只返回指定 `system_id` 下的 `PUBLISHED` 片段。
34. 已通过复合外键将文档、版本、来源和片段的 `system_id` 串成数据库隔离链，并为系统+发布状态查询建立索引；REQ-002/REQ-011 追溯状态已推进为 `implementing`。
35. 已完成版本/发布 review 修复：幂等请求保存原始父文档 ID并使用任务上传者校验；当前发布指针同时约束文档和系统；发布/退役统一锁序；对象上传不再长期持有版本分配行锁。
36. 已完成 Phase 1 PostgreSQL/Redis 集成预验收：Python 3.11.11 下 129 项测试通过，PostgreSQL 16 迁移/Schema 一致性、真实 Redis Session、双系统越权拒绝、Markdown 入库、v2 发布切换、跨系统零泄漏及租约恢复派发均通过。
37. 已实现 PostgreSQL `pg_trgm` 关键词召回、pgvector 余弦召回和 RRF 融合；两个查询均在排序前强制限定 `system_id`、`PUBLISHED` 和文档来源，Embedding 故障时只降级到关键词。
38. 已实现批量 Embedding 索引与原子写回，模型名、版本、维度、归一化、数量、超时和批大小均有契约或配置校验；新增 `vector`/`pg_trgm` 迁移和 trigram 索引。
39. 已实现证据条数/字符预算、稳定证据编号、Qwen OpenAI 兼容 SSE 生成、结构化回答解析和引用白名单/逐字验证，引用结果携带不可变来源与 locator 快照。
40. 已完成 Phase 2 第 1 项 review 修复：数据库向量异常可观测降级、版本化 Prompt、成功流终止校验、声明级引用支撑、批量向量写回和超预算证据跳过均有回归测试。
41. 已实现 `model-service` Ollama `bge-m3` 适配：兼容新旧 Embedding API、限制请求、校验模型/数量/1024 维/有限非零向量、执行 L2 归一化，并提供存活/就绪健康检查；默认复用本机现有 1.158 GB 模型 volume。
42. 已完成 model-service review 修复：实际 tag/digest 与对外版本绑定，严格拒绝非数组和非数值向量，健康检查使用独立短超时，Provider 输出脱敏结构化耗时/错误日志，并增加可显式启用的真实 Ollama 集成测试门禁。
43. 已实现版本化确定性证据策略，覆盖无证据、定位缺失、低融合分、头部差值不足、必需词未覆盖、显式冲突和向量降级阈值倍率，并一次记录全部失败原因。
44. 已实现可靠问答分流：证据不足、证据预算清空和生成内容无法由引用原文支撑时拒答；检索/模型不可用和模型格式错误保持系统故障，不误建知识缺口工单。
45. 已实现证据判定与自动工单同事务持久化、`run_id` 幂等，以及按系统、规范化问题和时间窗合并重复工单；不同系统不合并。

## 4. 正在进行

1. Phase 2 功能范围 3/4 的基础代码已完成；第 2 项新迁移往返、问答 API/SSE、答案引用持久化、Worker 索引接线、检索层纳入 TICKET 来源、工单 API 路由与第 4 项仍待补；第 3 项工单工作流与审核入库单测和静态检查已通过。
2. Phase 1 功能范围 6/6 已实现且 PostgreSQL/Redis 预验收通过；真实 S3 与四格式完整持久化链路仍是并行补验项。
3. 本地 Ollama Embedding 适配已就绪；等待可加载 `vector` 的 PostgreSQL 和完整 Qwen Key 完成组合联调。
4. 等待目标 Linux 服务器资源信息以最终确定 Embedding/Rerank 推理后端、量化方式和 Python 传递依赖锁；本地 Ollama 方案不自动等同生产选型。

## 5. 未完成 / 下一步

1. 提供隔离 S3 endpoint/Bucket 后，补跑四种格式的 S3→PostgreSQL→Worker 完整链路和页面手测；仅需复验对象存储相关集成点。
2. 在支持 `vector`/`pg_trgm` 的 PostgreSQL 执行 `c8784d439b23`，启动真实 `/v1/embeddings` 服务并配置完整 Qwen Key，跑通索引、双通道检索、生成和引用集成样例。
3. 在隔离数据库补跑 `cc99b700f739` 的升级/降级/升级往返与 `alembic check`，再接入问答 API/SSE 和会话/答案/引用持久化。
4. 实现 Phase 2 第 3/4 项：按系统分派、处理、追加、关闭、重开和审核入库。（基础代码与 24 项单测已完成，待补工单 API 路由、检索层纳入 TICKET 来源与真实链路验收）
5. 接入索引 Worker 阶段并完成 AC-004 至 AC-007 的端到端验收；随后在类生产 Linux 环境验证迁移锁时长、模型运行和发布回滚。

## 6. 阻塞点

| 问题 | 影响 | 需要谁处理 | 当前状态 |
| --- | --- | --- | --- |
| 当前 PostgreSQL 16 无可加载的 `vector` 扩展 | 阻塞真实向量列迁移和 pgvector 查询；代码与 SQLite 迁移测试不受影响 | 用户/DBA | 本机 Homebrew pgvector 仅含 PG17/18 构件，待提供兼容实例 |
| 模型服务器 CPU/内存/GPU 信息未知 | 影响生产 Embedding/Rerank 运行时和量化；本地 Ollama 适配不受阻 | 运维/用户 | 待提供 |
| Qwen 完整 API Key 未配置 | 阻塞真实回答生成联调 | 用户/运维 | Qwen base/model 已知；Key 待提供 |
| 公司通知协议及真实对象存储端点契约待验证 | 影响后续通知 provider 和 S3 兼容性证明 | 用户/第三方 | 待提供/验证 |
| 本机无 S3 兼容服务或测试 Bucket | 阻塞 Phase 1 真实对象存储与四格式完整链路关闭门禁 | 用户/运维 | 待提供隔离 endpoint、Bucket 和凭据 |

## 7. 最近改动文件

| 文件 | 改动说明 | 状态 |
| --- | --- | --- |
| `docs/product/01-requirements-clarification.md` | 同步双登录、账号来源、默认密码规则并清理框架待确认旧状态 | 已完成 |
| `docs/engineering/04-tech-decisions.md` | 记录正式架构决策并将运行时调整为 Python 3.11 | 已完成 |
| `docs/product/06-roadmap.md` | Phase 1 功能推进至 6/6，并保留真实基础设施集成验收门禁 | 已完成 |
| `docs/product/15-frontend-design.md` | 增加双登录流程和 TD-010 前端组件策略 | 已完成 |
| `docs/development/17-traceability-matrix.md` | 18 项需求映射实现模块并推进到 `skeleton` | 已完成 |
| `AI_DEVELOPMENT_RULES.md` | 更新本项目账号与会话规则 | 已完成 |
| `docs/README.md` | 修正需求和技术选型状态及下一步门禁 | 已完成 |
| `docs/development/16-retrospective.md` | 将来源项目认证迁移结论同步到 TD-006 | 已完成 |
| `docs/development/03-feature-changelog.md` | 记录架构确认和 Python 3.11 调整 | 已完成 |
| `docs/development/20-phase1-integration-acceptance.md` | 记录 Phase 1 PostgreSQL/Redis 验收证据、跳过项和 S3 复验计划 | 已完成 |
| `docs/engineering/11-project-structure.md` | 完整架构方案通过确认 | 已完成 |
| `backend/pyproject.toml` | Python 3.11 后端依赖和质量工具配置 | 已完成 |
| `model-service/src/knowagent_model/`、`.env.example`、`pyproject.toml` | Ollama bge-m3 适配、批量/旧接口兼容、归一化、健康检查、配置和进程入口 | 已完成；生产运行时待硬件门禁 |
| `model-service/tests/unit/`、`tests/integration/` | Ollama 请求转换、回退、模型身份、严格向量、日志、限额、健康检查、CLI、配置回归和真实服务门禁 | 已完成；真实门禁待服务恢复后复跑 |
| `frontend/package.json` 等 | TypeScript/Vite/ESLint/Vitest 配置和 npm 锁文件 | 已完成 |
| `backend/src/knowagent/identity/` | 账号领域、统一认证、RBAC、导入和基础设施适配 | 已完成 |
| `backend/migrations/versions/3f5d51a53981_create_phase1_identity_tables.py` | 账号与审计表基线迁移 | 已完成 |
| `frontend/src/features/auth/`、`frontend/src/features/admin/` | 双登录、首次改密、路由守卫和管理员账号管理 | 已完成 |
| `backend/tests/`、`frontend/src/**/*.test.ts(x)` | 认证、并发保护、限流、校验和页面工作流回归测试 | 已完成 |
| `docs/operations/07-local-development.md` | 本地启动、迁移、初始化和导入说明 | 已完成 |
| `backend/src/knowagent/systems/` | 系统领域、服务、SQLAlchemy 适配和 API | 已完成 |
| `backend/migrations/versions/baaf88cba66a_create_business_systems_and_owner_roles.py` | 业务系统与负责人映射迁移 | 已完成 |
| `frontend/src/features/admin/SystemsPage.tsx` | 系统管理、启停和负责人配置 | 已完成 |
| `frontend/src/features/auth/UserHomePage.tsx` | 前台启用系统加载与显式选择 | 已完成 |
| `backend/src/knowagent/systems/`、`backend/src/knowagent/identity/` | 映射变更会话撤销、管理员分页、候选搜索和普通用户数据最小化 | 已完成 |
| `frontend/src/features/admin/SystemsPage.tsx` | 服务端分页、负责人搜索/重试和编辑表单清理 | 已完成 |
| `frontend/src/shared/WorkspaceShell.tsx`、`frontend/src/features/auth/UserShell.tsx`、`frontend/src/features/admin/AdminShell.tsx` | 双端响应式壳层、导航、上下文标题和账号菜单 | 已完成 |
| `frontend/src/shared/FeedbackState.tsx`、`frontend/src/shared/uiError.ts`、`frontend/src/app/AppErrorBoundary.tsx` | 统一局部状态、请求追踪与全局错误兜底 | 已完成 |
| `frontend/src/features/auth/UserHomePage.tsx`、`frontend/src/features/admin/AccountsPage.tsx`、`frontend/src/features/admin/SystemsPage.tsx` | 可恢复加载/空/错状态、最新请求胜出和原位重试锁定 | 已完成 |
| `frontend/src/**/*.test.ts(x)` | 导航、移动抽屉、错误边界、追踪 ID、恢复路径和乱序请求回归测试 | 已完成 |
| `backend/src/knowagent/documents/domain/models.py` | `SourceLocator`、语义块、解析文档和知识 chunk 契约 | 已完成 |
| `backend/src/knowagent/documents/infrastructure/parsers/` | 四类格式解析器、资源限制、错误分类和 parser registry | 已完成 |
| `backend/src/knowagent/documents/application/chunking.py` | 结构边界优先的预算切分与 locator 传播 | 已完成 |
| `backend/tests/unit/test_source_locator.py`、`test_document_parsers.py`、`test_document_chunking.py` | 四类真实生成样本、定位、异常和切分回归测试 | 已完成 |
| `backend/src/knowagent/platform/settings.py`、`backend/.env.example` | 文档解析、归档、格式结构和 chunk 预算环境配置 | 已完成 |
| `backend/tests/unit/test_document_configuration.py` | 文档配置加载与非法边界回归测试 | 已完成 |
| `docs/operations/07-local-development.md` | 文档解析配置与同步 worker 执行边界 | 已完成 |
| `backend/src/knowagent/platform/object_store.py`、`backend/src/knowagent/platform/settings.py`、`backend/.env.example` | S3 兼容对象存储适配器、超时/TLS/multipart/重试和入库任务配置 | 已完成 |
| `backend/src/knowagent/documents/domain/ingestion.py`、`application/`、`infrastructure/`、`api/` | 持久任务状态机、上传幂等用例、处理/恢复流程、SQLAlchemy 适配和 API | 已完成 |
| `backend/src/knowagent/worker/` | Celery ingestion 队列、仅 `job_id` 派发和 Beat 恢复扫描 | 已完成 |
| `backend/migrations/versions/d1a97d2e451b_create_document_ingestion_tables.py` | 文档、版本和入库任务表及约束/索引 | 已完成 |
| `backend/tests/unit/test_*ingestion*.py`、`test_s3_object_store.py`、`backend/tests/integration/test_identity_api.py` | 状态机、幂等、重试、恢复、对象存储、权限和 API 回归测试 | 已完成 |
| `backend/tests/unit/test_worker_tasks.py`、入库相关回归测试 | Worker 装配、租约 fencing、Broker 一致性、非法重试、幂等作用域和对象补偿 review 回归 | 已完成 |
| `backend/src/knowagent/knowledge/` | 知识来源/片段领域模型、发布事务与强制系统过滤仓储 | 已完成 |
| `backend/src/knowagent/documents/` | 文档 v2+ 上传、版本 `system_id` 与独立发布状态 | 已完成 |
| `backend/migrations/versions/3ba86a4c3d35_add_knowledge_publication_isolation_.py` | 版本回填、请求父文档指纹、发布状态、当前指针与隔离链复合外键、知识表和索引迁移 | 已完成 |
| `backend/tests/unit/test_knowledge_publication.py`、相关入库/API 测试 | 发布切换、统一锁序、幂等重放、操作类型、文档更新时间和复合约束回归 | 已完成 |
| `backend/pyproject.toml`、`.gitignore` | 保留实质重复检测并过滤声明式短映射噪音；忽略本地 Alembic/Pylint 产物 | 已完成 |
| `docs/operations/08-deployment.md` | 非 Docker 发布、迁移、验证与回滚基线 | 已完成（真实部署待 Phase 4） |
| `backend/src/knowagent/retrieval/` | Embedding Provider、关键词/向量检索、RRF、证据组织、可观测降级与指标端口 | 基础代码与 review 修复已完成；真实服务待验收 |
| `backend/src/knowagent/agent/` | 版本化 Prompt、Qwen 兼容流式生成、声明级回答和引用验证 | 基础代码与 review 修复已完成；API/持久化待后续 |
| `backend/src/knowagent/knowledge/application/indexing.py` | 批量 Embedding、模型契约校验与原子向量写回 | 基础代码已完成；Worker 接线待后续 |
| `backend/migrations/versions/c8784d439b23_add_phase2_vector_and_lexical_retrieval.py` | `vector`/`pg_trgm`、向量列和 trigram 索引 | SQLite 往返通过；真实 pgvector 待验收 |
| `backend/tests/unit/test_*retrieval.py`、`test_*embedding*.py`、`test_evidence_organizer.py`、`test_answer_generation.py`、`test_grounded_answer.py`、`test_knowledge_indexing.py` | Phase 2 第 1 项正常、边界、异常与隔离回归 | 已完成 |
| `backend/src/knowagent/agent/application/evidence_decision.py`、`reliable_question.py` | 确定性证据充分性、可靠拒答和故障分流 | 基础代码与单测/静态检查已完成；API/SSE 接线待补 |
| `backend/src/knowagent/tickets/`、`backend/src/knowagent/agent/infrastructure/sqlalchemy_models.py` | 判定留痕、拒答自动建单、运行幂等和系统内时间窗合并 | 基础代码与单测/静态检查已完成；完整工单状态机待补 |
| `backend/migrations/versions/cc99b700f739_add_evidence_decisions_and_refusal_.py` | `evidence_decisions`、`tickets`、外键、唯一约束和查询索引 | 已生成并人工修正 JSONB；迁移往返与 `alembic check` 本轮未运行 |
| `backend/tests/unit/test_evidence_policy.py`、`test_refusal_tickets.py`、`test_reliable_question.py` | Phase 2 第 2 项正常、边界、异常、幂等和故障分流回归 | 已完成 |

## 8. 已运行验证

| 命令/方式 | 结果 | 说明 |
| --- | --- | --- |
| `rg` 认证关键词交叉检查 | 通过 | 双登录、账号来源、首次改密、Argon2id、Redis Session 和 TD-006 均已贯穿相关文档 |
| `rg` 冲突与旧状态检查 | 通过 | 未发现用户免登录、TD-006 待决定或产品文档待用户确认的遗留表述 |
| `rg` TD-007 交叉检查 | 通过 | 技术清单、决策正文、REQ-004/REQ-005 追溯关系和当前状态一致 |
| `rg` TD-008 交叉检查 | 通过 | 部署约束、决策正文、REQ-003/REQ-013 追溯关系和当前状态一致 |
| `rg` TD-009 交叉检查 | 通过 | 技术清单、决策正文、REQ-006/REQ-008/REQ-009 追溯关系和当前状态一致 |
| 官方包索引 + `pip --dry-run` | 通过 | 核心版本均存在，Python 直接依赖组合可解析；识别并规避 redis-py 8.1.0 冲突 |
| 架构章节与 REQ 映射检查 | 通过 | 18 个需求均有已确认实现模块，追溯矩阵状态为 `skeleton` |
| 架构依赖方向自检 | 通过 | 审计通过通用端口接入；业务模块不反向依赖 Agent，未发现设计级循环依赖 |
| TOML/JSON/JavaScript 配置语法检查 | 通过 | 两个 `pyproject.toml`、package/tsconfig/Prettier 和 ESLint 配置可解析 |
| Python 3.11 约束断言 | 通过 | backend/model-service 的 `requires-python`、Black、mypy 和 Pylint 目标均为 3.11 |
| npm 锁文件生成 | 通过 | Node.js 24.16.0 下完成依赖树解析，生成 `frontend/package-lock.json` |
| npm peer 契约核验 | 通过 | TypeScript 固定 5.9.3，满足 typescript-eslint `<6.1` 约束；Vite/Vitest 支持 Node 24 |
| 后端 `pytest tests -v` | 通过 | 32 个测试通过，覆盖率 91.29%；覆盖双入口、失败限流及边界、并发管理员锁语义、首次改密、CSRF、RBAC、账号校验和 CLI |
| Alembic `autogenerate` + `upgrade head` + `check` | 通过 | ORM 与迁移无新增差异；SQLite 用于差异生成和迁移语法验证 |
| 前端 test/coverage/typecheck/lint/format/build | 通过 | 27 个测试；全局语句/分支/函数/行覆盖率 92.68%/80.41%/86.36%/95.03%；TypeScript、ESLint、Prettier 和 Vite 生产构建无错误 |
| REQ-002 后端 pytest/覆盖率 | 通过 | 37 个测试通过，总覆盖率 91.55%；覆盖两个系统、重复标识、启停、负责人映射、CSRF/RBAC 和前台可见性 |
| REQ-002 Alembic autogenerate/upgrade/check | 通过 | 自动生成两表迁移并人工核对列、枚举、外键、唯一约束和索引；`check` 无差异 |
| REQ-002 前端 test/coverage/typecheck/lint/format/build | 通过 | 34 个测试；全局语句/分支/函数/行覆盖率 93.36%/80.00%/88.72%/95.98%；生产构建成功 |
| REQ-002 评审修复全量验证 | 通过 | 后端 39 项测试、覆盖率 92.07%；前端 35 项测试，语句/分支/函数/行覆盖率 92.56%/81.73%/87.50%/95.34%；TypeScript、ESLint、Prettier 和 Vite 构建通过 |
| REQ-003 前端 test/coverage/typecheck/lint/format/build | 通过 | 42 项测试；语句/分支/函数/行覆盖率 92.49%/85.11%/85.62%/94.63%；TypeScript、ESLint、Prettier 和 Vite 生产构建无错误 |
| REQ-003 浏览器响应式检查 | 通过 | 1440x900、390x844 及 1023px/1024px 临界视口通过；`<1024px` 使用抽屉、`>=1024px` 使用固定侧栏，页面均无横向溢出或控件重叠 |
| REQ-004 后端全量测试/覆盖率 | 通过 | 81 个测试通过，总覆盖率 90.80%，`chunking.py` 覆盖率 90%；四类运行时生成样本及评审回归全部通过 |
| REQ-004 Black/isort | 通过 | 本次 `documents`、平台 settings 源码和 4 个新增测试文件检查通过 |
| REQ-004 `mypy --strict` | 通过（本模块） | `documents` 与平台 settings 共 16 个源文件零错误；全仓仍有 identity/systems 既有 26 个错误 |
| REQ-004 Pylint/Bandit | 通过 | `documents` 与平台 settings 的 Pylint 10.00/10；全仓 Bandit 中高危 0 |
| REQ-004 评审修复定向验证 | 通过 | 42 项 locator/parser/chunker/config 定向测试通过；损坏 OOXML、MIME 参数、中文预算、超长表头、多行 Markdown 表格和非法配置均已覆盖 |
| Phase 1 持久入库定向测试 | 通过 | 42 项 ingestion/S3/config/worker/API review 回归测试通过 |
| Phase 1 持久入库后端全量测试 | 通过 | 115 项测试通过，总覆盖率 91.07% |
| Phase 1 持久入库 Black/isort | 通过（本次范围） | 本次 28 个未提交 Python 文件 Black/isort 检查通过，集成测试历史格式问题已统一修复 |
| Phase 1 持久入库 `mypy --strict` | 通过（本次模块） | `documents`、object store、settings、worker 和 API 共 30 个源文件零错误；全仓仍为 identity/systems 既有 6 文件 26 错误 |
| Phase 1 持久入库 Pylint/Bandit | 通过 | 本次源文件 Pylint 10.00/10；全仓 Bandit 中高危 0 |
| Phase 1 持久入库 Alembic | 通过 | 隔离 SQLite 空库 `upgrade head` 与 `alembic check` 通过；人工核对三表列、枚举、外键、唯一/检查约束和索引与 ORM 一致 |
| Phase 1 版本/发布/隔离全量测试 | 通过 | review 修复后端 129 项测试通过，总覆盖率 91.54%；覆盖跨上传者幂等、创建/追加操作切换、对象写入与版本锁顺序、请求指纹持久化及当前指针复合约束 |
| Phase 1 版本/发布/隔离静态检查 | 通过 | 本次 39 个 Python 文件 Black/isort 清洁；相关 32 个源文件 mypy strict 零错误；Pylint 10.00/10；Bandit 中高危 0 |
| Phase 1 版本/发布/隔离 Alembic | 通过 | 全新隔离 SQLite 空库完成 `upgrade head -> downgrade d1a97d2e451b -> upgrade head` 往返，`alembic check` 确认 ORM/迁移无差异 |
| Phase 1 Python 3.11 全量测试 | 通过 | 129 项测试通过，总覆盖率 91.54%；四类运行时生成样本及边界/异常回归通过 |
| Phase 1 PostgreSQL 16 迁移 | 通过 | 隔离数据库 `upgrade head` 与 `alembic check` 通过，无 ORM/Schema 差异 |
| Phase 1 PostgreSQL/Redis 核心链路 | 通过 | 双系统授权、未授权上传 403、幂等、Markdown 入库、v2 发布切换、B 系统 0 发布 chunk、Redis Session 和 1 个过期任务恢复派发通过 |
| Phase 1 S3/四格式完整链路 | 跳过 | 本机没有 S3 兼容服务或测试 Bucket；详见集成验收报告 |
| Phase 2 第 1 项后端全量测试 | 通过 | review 修复后 167 项测试通过，总覆盖率 91.06%；45 项相关测试覆盖召回、数据库异常降级/指标、索引、证据预算、Prompt、流终止、声明支撑和引用异常 |
| Phase 2 第 1 项静态检查 | 通过 | 相关 27 个源文件 mypy strict 零错误；本次 36 个 Python 文件 Black/isort 清洁；Pylint 10.00/10；全仓 Bandit 中高危 0 |
| Phase 2 第 1 项 Alembic | 通过（SQLite） | `upgrade head -> downgrade 3ba86a4c3d35 -> upgrade head` 和 `alembic check` 通过；真实 PostgreSQL 因 `vector` 扩展不兼容未运行 |
| model-service Ollama 适配自动化验证 | 通过 | review 修复后 39 项测试通过、1 项真实服务测试显式跳过，总覆盖率 90.58%；源文件与测试 mypy strict 零错误；Bandit 中高危 0 |
| model-service 真实 bge-m3 冒烟 | 通过（本地） | Ollama 0.3.14 复用 1.2 GB 模型 volume；ready 200，真实 `/api/embed` 返回 1024 维归一化向量；冷启动 18.21 秒、热请求 3.73 秒 |
| pgvector/Embedding/Qwen 真实链路 | 未运行 | Ollama 适配已实现；缺少可加载 `vector` 的 PostgreSQL 和完整 Qwen Key，不宣称组合集成成功 |
| Phase 2 第 2 项后端单测/覆盖率 | 通过 | 46 项定向测试全部通过；证据决策、可靠问答和工单核心模块分支覆盖率 92.83% |
| Phase 2 第 2 项静态检查 | 通过（本次范围） | 18 个相关源/测试文件 Black/isort 清洁；111 个源文件 mypy strict 零错误；本次源文件 Pylint 10.00/10；全仓 Bandit 中高危 0 |
| Phase 2 第 2 项 Alembic/真实集成 | 未运行（用户限定范围） | 未运行 `cc99b700f739` 往返、`alembic check`、真实 PostgreSQL/pgvector、Ollama/Qwen 或端到端链路 |

## 9. 未运行验证与风险

1. 双端壳层和业务系统页面已使用隔离测试 API 完成桌面/移动浏览器截图与交互检查；真实 PostgreSQL/Redis 后端的完整页面链路仍待集成环境补充。
2. 默认密码批量导入仍有共享密码泄露风险；实现已强制摘要、首次改密、限流、会话撤销和审计，凭据分发流程仍需组织侧控制。
3. 核心、解析器和质量工具直接版本已固定；Python 传递依赖锁仍需在目标 Linux/Python 3.11 环境生成。
4. 本地 Ollama 适配和修复前真实 bge-m3 冒烟已通过；review 修复时服务未运行，新增 digest 强校验集成测试待恢复服务后复跑。目标 Linux 运行时、量化与完整安装尚未验证，本轮前端生产构建已通过。
5. `npm audit` 的公告接口访问审批返回 503；`npm ci` 曾报告现有锁文件有 2 个 high 漏洞，未在未评估 breaking change 的情况下执行自动升级。
6. 四类解析器已接入 S3/PostgreSQL/Celery 端口和持久任务；PostgreSQL/Redis/Markdown 核心链路已在真实服务验证，但 S3 签名、TLS、Bucket 权限、multipart、对象补偿及四格式完整组合仍待隔离 S3 环境。扫描 PDF 仅返回 `OCR_REQUIRED`，首版不执行 OCR。
7. 本轮使用现有 Python 3.11.11 环境并在 `/tmp` 补充四个锁定依赖；FastAPI、Redis client、pytest/pytest-cov 小版本低于项目锁定版本，结果不替代目标 Linux 按完整锁定依赖安装的发布证明。
8. 新迁移已在真实 PostgreSQL 16.14 完成 `upgrade head` 和 `alembic check`，JSONB 与复合外键成功落库；迁移锁时长、已有生产量级回填和查询计划仍待类生产数据验证。
9. Phase 2 前三项基础代码已实现，但真实 PostgreSQL `vector` 扩展和 Qwen 尚未完成组合联调；HNSW 在模型维度最终确认前不创建。第 2 项新迁移尚未执行往返与 `alembic check`；问答 API/SSE、答案引用持久化、Worker 索引接线、检索层纳入 TICKET 来源、工单 API 路由与第 4 项仍待实现。

## 10. 继续开发建议

新对话或新开发者接手时，建议下一步：

1. 先阅读 TD-002、TD-003、TD-009、`retrieval`/`agent`/`tickets` 模块和 `c8784d439b23`、`cc99b700f739` 两个迁移。
2. 先补跑第 2 项迁移往返与 `alembic check`，再接入问答 API/SSE、会话/答案/引用持久化；环境可用时补 pgvector + Embedding + Qwen 的单条真实问答集成验收。
3. 随后补齐工单 API 路由、检索层纳入 TICKET 来源并实现 Phase 2 第 4 项（审核发布后重新索引与历史引用快照），再做 AC-004 至 AC-007 端到端验收；Phase 1 的真实 S3/四格式补验继续作为独立并行项。

## 11. 接手时必须先读

```text
AI_DEVELOPMENT_RULES.md
docs/00_START_HERE.md
docs/development/10-current-status.md
docs/development/03-feature-changelog.md
docs/product/06-roadmap.md
docs/engineering/04-tech-decisions.md
```
