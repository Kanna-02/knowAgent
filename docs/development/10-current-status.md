# Current Status

本文档用于跨对话、跨开发者、跨 AI 助手接续项目。每次阶段性暂停、切换对话、完成重要功能、遇到阻塞或准备交接时，都必须更新。

## 1. 快照时间

```text
更新时间：2026-08-06（Phase 3 代码完成；本机/Docker 资源盘点完成，Rerank 权重可复用、运行时待安装）
更新人/助手：Codex
当前分支：master
远程仓库：git@github.com:Kanna-02/knowAgent.git
当前环境：Python 3.11.15；PostgreSQL 17.10 + vector 0.8.6 + pg_trgm 1.6；Redis 8.10.0；MinIO RELEASE.2025-10-15T17-29-55Z；Node.js 24.16.0；本地 Ollama 0.3.14 + bge-m3；Qwen qwen3.5-27b
```

## 2. 当前阶段

```text
当前阶段：Phase 2 关闭门禁待真实评测数据；Phase 3 质量与运营增强已开始（1/4）
阶段目标：保留 Phase 2 系统隔离问答/工单闭环，同时完成混合检索调优、Rerank 和用户可见降级
当前任务：Phase 3 第 1 项代码、自动化和真实向量降级浏览器链路已完成；资源盘点确认已有 Rerank 权重，下一步先拆分本地加载路径，再安装缺失运行时并做真实推理
任务状态：Phase 3 1/4 功能范围完成；后端 284 passed / 24 skipped、覆盖率 86.64%，model-service 49 passed / 1 skipped、覆盖率 85.63%，前端 47/47；真实 PostgreSQL/Redis/API/SSE/浏览器已验证向量降级拒答和工单创建。Phase 2 仍因 AC-004/AC-005 真实质量数据未关闭
```

## 3. 已完成

1. 初始化需求、路线图、前端设计、开发规则和追溯矩阵。
2. 完成 `knowledge-rag` 跨项目资产盘点。
3. 已确认 TD-001 至 TD-012，包括全 Python、PostgreSQL 混合检索、独立模型服务、Celery、双入口 Redis Session、格式专用解析、S3 兼容对象存储、原生 Linux 部署、LangGraph 编排、应用框架版本基线及 `FlagEmbedding + PyTorch` Rerank 运行时。
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
36. 已完成并关闭 Phase 1：固定 `knowagent_integration`、Redis DB 15 和 `knowagent-phase1-it` 环境下，真实 S3 契约、四格式 S3→PostgreSQL→Worker、双系统越权/零泄漏、幂等、v2 发布切换和租约恢复均通过；验收资源可重复复用并在成功后恢复运行前状态。
37. 已实现 PostgreSQL `pg_trgm` 关键词召回、pgvector 余弦召回和 RRF 融合；两个查询均在排序前强制限定 `system_id`、`PUBLISHED` 和文档来源，Embedding 故障时只降级到关键词。
38. 已实现批量 Embedding 索引与原子写回，模型名、版本、维度、归一化、数量、超时和批大小均有契约或配置校验；新增 `vector`/`pg_trgm` 迁移和 trigram 索引。
39. 已实现证据条数/字符预算、稳定证据编号、Qwen OpenAI 兼容 SSE 生成、结构化回答解析和引用白名单/逐字验证，引用结果携带不可变来源与 locator 快照。
40. 已完成 Phase 2 第 1 项 review 修复：数据库向量异常可观测降级、版本化 Prompt、成功流终止校验、声明级引用支撑、批量向量写回和超预算证据跳过均有回归测试。
41. 已实现 `model-service` Ollama `bge-m3` 适配：兼容新旧 Embedding API、限制请求、校验模型/数量/1024 维/有限非零向量、执行 L2 归一化，并提供存活/就绪健康检查；默认复用本机现有 1.158 GB 模型 volume。
42. 已完成 model-service review 修复：实际 tag/digest 与对外版本绑定，严格拒绝非数组和非数值向量，健康检查使用独立短超时，Provider 输出脱敏结构化耗时/错误日志，并增加可显式启用的真实 Ollama 集成测试门禁。
43. 已实现版本化确定性证据策略，覆盖无证据、定位缺失、低融合分、头部差值不足、必需词未覆盖、显式冲突和向量降级阈值倍率，并一次记录全部失败原因。
44. 已实现可靠问答分流：证据不足、证据预算清空和生成内容无法由引用原文支撑时拒答；检索/模型不可用和模型格式错误保持系统故障，不误建知识缺口工单。
45. 已实现证据判定与自动工单同事务持久化、`run_id` 幂等，以及按系统、规范化问题和时间窗合并重复工单；不同系统不合并。
46. 已完成审核发布重新索引：批准前先生成 Embedding，失败保持候选 `PENDING` 且不发布，成功后事务内创建带向量的 `TICKET` 来源/片段并将候选标记为 `PUBLISHED`。
47. 已将关键词和向量检索扩展到已发布工单来源，文档与工单使用外连接组装来源名称/版本；工单 locator 使用 `ticket_id`，不伪造文档身份。
48. 已实现回答与引用快照持久化，保存回答、声明、模型/Prompt 版本、降级原因、逐字引用和完整 locator；原 chunk/source UUID 作为历史值保留，不依赖当前知识表生命周期。
49. 已新增并验证 `c1738febb896` 迁移，答案/引用复合隔离、运行唯一约束、工单来源复合外键和候选 `PUBLISHED` 状态均已落地到本地 PostgreSQL 17。
50. 已完成 Phase 2 第 4 项 review 修复：审核锁不再跨越 Embedding `await`，候选批准/拒绝统一串行化；答案重放在外部调用前返回历史快照并处理并发唯一冲突；本地进程停止校验 PID 启动身份；ORM 约束名和模型默认 digest 与迁移、运行配置一致。
51. 已新增 Phase 2 live 集成运行器，读取真实 `.env` 并固定复用 `knowagent_integration` 和 Redis DB 15；真实 Qwen 合约、双系统 pgvector 检索隔离、答案快照、可靠拒答、工单工作流、审核发布和 5 分钟内回流检索均通过。
52. 已修复 PostgreSQL 父子 INSERT 顺序：答案先于引用 flush，拒答判定先于工单发生记录 flush；2 个写入顺序回归和 25 项相关单测通过。
53. 已装配 Agent API（`POST /api/v1/questions`）：依赖注入 `CsrfContext` 强制 CSRF，跨系统访问鉴权复用共享 helper，并把 `HttpEmbeddingProvider`/`OpenAiCompatibleLlmProvider`/策略/`AnswerGenerator`/prompt 提升为进程级单例复用连接池。
54. 已装配 Tickets API（`/api/v1/tickets` 系列）：列表/详情/回复/分派/开始/解决/关闭/重开/答案提交/候选审核全链路端点，系统归属鉴权、CSRF 校验与审计落库；修复 list_tickets 在可见系统为空时退化为全表扫描的跨系统泄露。
55. 已抽出 `backend/src/knowagent/identity/api/access.py` 共享 `require_system_access`/`visible_system_ids`，消除 agent/tickets 重复实现；`visible_system_ids` 改为不受 1000 上限的 `systems.list`。
56. 已抽 `backend/tests/integration/_fakes.py` 共享 `FakeRedis`/`FakePipeline`，并新增 `test_agent_api.py`、`test_tickets_api.py`（21 项集成测试默认 skip，含 CSRF、跨系统泄露回归用例）。

57. 已实现受证据约束的真实增量 SSE：仅完整、可解析且引用通过白名单/逐字校验的 claim 产生 `answer_delta`，最终产生 `answer_completed`；原始模型 JSON 和未验证事实不下发。
58. 已装配 `POST /api/v1/questions/stream` 与 `GET /api/v1/questions/stream/events`：Redis token 绑定账号、TTL 120 秒并单次消费，消费时重新检查系统权限；跨账号消费和重放均有回归测试。
59. 已接线可恢复文档索引 Worker：`ChunkIngestionService` 完成 manifest→chunk/source→Embedding→`READY_DRAFT`；Embedding 故障记录 `EMBEDDING_UNAVAILABLE` 并由持久任务状态机重试，只有索引成功才完成任务。
60. 已实现前端页面端到端：SSE 问答页（系统选择→问题/必含术语→取 token→`EventSource` 订阅→按事件更新流式文本/工单/错误）、工单页面（列表筛选+详情抽屉+状态流转 start/resolve/close/reopen+回复+答案候选+时间线+按角色管理 UI）、壳层工单导航与 `tickets` 路由、API 类型与客户端调用、配套样式与 cursor-blink 动画。
61. 已补本轮单测：后端 `test_answer_stream.py` 4 项、`test_question_stream.py` 5 项、`test_chunk_ingestion.py` 6 项；前端 `UserHomePage.stream.test.tsx` 2 项、`TicketsPage.test.tsx` 3 项；并同步更新 `test_worker_tasks.py`、`UserHomePage.test.tsx`、`authWorkflow.test.tsx`。
62. 已新增 Phase 2 离线评测门禁 `knowagent-evaluate-phase2`，强制至少 50 个真实可回答 ESB 问题、正确率/引用支持率/拒答召回率阈值、拒答工单完整性和零无依据回答。
63. 已扩展 Phase 2 集成运行器，真实 Worker→Embedding、Qwen 增量流、SSE token、Agent/Tickets API 和审核回流一次执行；`qwen3.5-27b` 下 23 passed、6 warnings、36.69 秒。
64. 已稳定前端默认测试运行：Vitest `fileParallelism: false`，默认 47/47 通过；TypeScript、ESLint 和生产构建通过。
65. 已补 `docs/development/22-phase2-evaluation.md`，明确真实数据、人工标注、JSONL 字段、执行命令和报告留存规则。
66. 已通过项目受控导入流程创建本地 `visual.tester` 测试用户，并创建启用的 `PHASE3_TEST` 系统；真实浏览器完成登录、首次改密、系统选择和问答提交。该数据仅存在本机开发库，不属于迁移或仓库种子。
67. 已实现可配置加权 RRF、严格 `HttpRerankProvider`、有限候选 Rerank 和 `VECTOR_UNAVAILABLE`/`RERANK_UNAVAILABLE` 两级显式降级；两种原因可同时保留并进入日志、指标、回答/拒答 SSE。
68. `model-service` 已实现 `/v1/rerank`、FlagEmbedding 延迟加载/线程推理/并发限制、请求资源上限和 Embedding 必需/Rerank 可降级 readiness；`FlagEmbedding==1.4.0` 仅作为 `rerank` optional extra。
69. 前端回答与拒答均展示具体降级原因；真实 PostgreSQL 17 + Redis + API/SSE + 浏览器已验证向量服务不可用时只用关键词、可靠拒答继续建单。1280x720 与 390x844 均无横向溢出、Alert 重叠或文本截断。
70. 已完成本机和 Docker 资源盘点：`bge-m3` 已在 Docker volume，原生/ONNX Rerank 权重已在 `knowledge-rag/deploy/models/`；四个 Python 环境均缺 Rerank 运行时，TEI 镜像/容器不存在。盘点写入 `docs/operations/09-runtime-resource-inventory.md`，未继续下载权重。

## 4. 正在进行

1. Phase 2 功能、自动化和真实服务集成已完成；正在等待真实标注评测集执行 AC-004/AC-005。实际本地账号已补齐并完成 Phase 3 向量降级拒答浏览器链路，完整带引用回答/工单管理人工验收仍需已发布知识和对应角色数据。
2. Phase 1 功能范围 6/6 已实现，并于 2026-08-04 在固定 PostgreSQL/Redis/MinIO integration 资源上完成四格式完整持久化与隔离验收，现已正式关闭。
3. 本地 PostgreSQL 17、pgvector、pg_trgm、Redis、MinIO、Ollama Embedding 和 Qwen `qwen3.5-27b` 已完成 Phase 2 API/SSE/Worker 组合联调。
4. Phase 3 第 1 项为 1/4：代码、单测、静态检查和真实向量降级页面通过；本机已有可复用 Rerank 权重，但 `model-service[rerank]` 未安装。当前先处理模型 ID/本地加载路径解耦，再安装运行时；目标 Linux 资源信息仍是生产门禁。

## 5. 未完成 / 下一步

1. 用户提供至少 50 条真实标注 ESB 可回答问题及无知识问题集，按 `docs/development/22-phase2-evaluation.md` 执行质量门禁并把脱敏汇总写入验收报告。
2. 拆分 Rerank 对外模型 ID 与本地加载路径，复用 `knowledge-rag` 已有权重；确认依赖树和缓存命中后再安装运行时，不重新下载模型。随后使用至少一条已发布知识补跑真实 Rerank 回答路径，并用 ESB 评测集对比基础 RRF 与 Rerank 质量。
3. 使用测试负责人/系统负责人账号补工单详情、回复、状态流转、答案提交和审核来源展示；当前普通用户账号仅覆盖问答与拒答入口。
4. 取得目标 Linux CPU/内存/GPU 信息，确定 PyTorch 原生、量化或 ONNX 替代方案并生成生产传递依赖锁；随后继续 Phase 3 多轮/版本项。

## 6. 阻塞点

| 问题 | 影响 | 需要谁处理 | 当前状态 |
| --- | --- | --- | --- |
| 缺至少 50 条真实标注 ESB 可回答问题和无知识问题集 | 无法真实计算 AC-004/AC-005 的正确率、引用支持率和拒答召回率，阻塞 Phase 2 关闭 | 用户/业务评测负责人 | 待提供；CLI 门禁和格式已就绪 |
| 本地开发库缺业务知识和负责人数据 | 已完成普通用户登录、向量降级拒答与建单；无法形成真实 Rerank 回答、工单处理/审核完整页面记录 | 用户/测试负责人 | `visual.tester` + `PHASE3_TEST` 已补；待已发布知识与负责人账号 |
| Rerank 运行时未安装，模型 ID 与本地路径尚未解耦 | 已有权重不能在保持外部模型契约不变的前提下直接加载 | 开发 | 权重已盘点；禁止重复下载，待新增独立加载路径配置 |
| 模型服务器 CPU/内存/GPU 信息未知 | 影响生产 Embedding/Rerank 运行时和量化；本地 Ollama 适配不受阻 | 运维/用户 | 待提供 |
| 公司通知协议及真实对象存储端点契约待验证 | 影响后续通知 provider 和 S3 兼容性证明 | 用户/第三方 | 待提供/验证 |

## 7. 最近改动文件

| 文件 | 改动说明 | 状态 |
| --- | --- | --- |
| `backend/src/knowagent/agent/application/answer_generation.py`、`backend/src/knowagent/agent/application/reliable_question.py`、`backend/src/knowagent/agent/domain/models.py` | 受证据约束的真实增量 claim、`QuestionStreamEvent` 领域类型与 `resolve_stream` | 已完成；真实 Qwen 增量流通过 |
| `backend/src/knowagent/agent/api/router.py`、`backend/src/knowagent/agent/api/schemas.py` | `POST/GET /questions/stream`、账号绑定/单次 Redis token 与 SSE 事件模型 | 已完成；真实 Redis/API 集成通过 |
| `backend/src/knowagent/documents/application/processor.py`、`backend/src/knowagent/documents/application/chunk_ingestion.py`、`backend/src/knowagent/documents/ports.py` | 可恢复 `ChunkIngestionService`、`ChunkIngestionHook` 与 `EMBEDDING_UNAVAILABLE` 重试状态 | 已完成；真实 Worker→Embedding 通过 |
| `backend/src/knowagent/worker/tasks.py` | `_runtime()` 注入复用的 `HttpEmbeddingProvider` + `ChunkIngestionService` | 已完成；真实 Worker 集成通过 |
| `frontend/src/api/types.ts`、`frontend/src/api/client.ts` | SSE token、Answer/Claim/Citation/Locator/Evidence 视图模型、6 种 SSE 事件、Ticket/Reply/Transition/Candidate 视图与枚举、流式问答与工单全链路调用 | 已完成 |
| `frontend/src/features/auth/UserHomePage.tsx`、`frontend/src/features/tickets/TicketsPage.tsx`、`frontend/src/features/auth/UserShell.tsx`、`frontend/src/app/App.tsx`、`frontend/src/styles.css` | 问答页、工单页、工单导航与路由、配套样式 | 已完成（前端构建与单测通过） |
| `backend/tests/unit/test_answer_stream.py`、`test_question_stream.py`、`test_chunk_ingestion.py`；`frontend/src/features/auth/UserHomePage.stream.test.tsx`、`frontend/src/features/tickets/TicketsPage.test.tsx` | 本轮新增单测及同步更新用例 | 已完成 |
| `backend/src/knowagent/agent/evaluation.py`、`evaluation_cli.py`、`backend/tests/unit/test_phase2_evaluation.py`、`backend/pyproject.toml` | AC-004/AC-005 JSONL 离线评测门禁和 CLI 入口 | 已完成；真实数据待用户提供 |
| `frontend/vite.config.ts` | 关闭文件并行，稳定默认完整测试 | 已完成；47/47 通过 |
| `docs/product/01-requirements-clarification.md` | 同步双登录、账号来源、默认密码规则并清理框架待确认旧状态 | 已完成 |
| `docs/engineering/04-tech-decisions.md` | 记录正式架构决策并将运行时调整为 Python 3.11 | 已完成 |
| `docs/product/06-roadmap.md` | Phase 1 功能推进至 6/6，并保留真实基础设施集成验收门禁 | 已完成 |
| `docs/product/15-frontend-design.md` | 增加双登录流程和 TD-010 前端组件策略 | 已完成 |
| `docs/development/17-traceability-matrix.md` | 18 项需求映射实现模块并推进到 `skeleton` | 已完成 |
| `AI_DEVELOPMENT_RULES.md` | 更新本项目账号与会话规则 | 已完成 |
| `docs/README.md` | 修正需求和技术选型状态及下一步门禁 | 已完成 |
| `docs/development/16-retrospective.md` | 将来源项目认证迁移结论同步到 TD-006 | 已完成 |
| `docs/development/03-feature-changelog.md` | 记录架构确认和 Python 3.11 调整 | 已完成 |
| `docs/development/20-phase1-integration-acceptance.md` | 记录 Phase 1 PostgreSQL/Redis/MinIO 四格式完整验收证据和遗留风险 | 已完成（正式通过） |
| `backend/tests/integration/test_phase2_live_integration.py`、`scripts/run-phase2-integration.sh` | Phase 2 固定资源 Worker/SSE/API/工单 live 验收与真实 Qwen 门禁 | 已完成；23/23 通过 |
| `docs/development/21-phase2-integration-acceptance.md`、`22-phase2-evaluation.md` | 记录 23 项真实集成证据、阶段关闭门禁、评测输入和执行规范 | 已完成；真实质量数据待提供 |
| `backend/src/knowagent/agent/api/`、`backend/src/knowagent/tickets/api/`、`backend/src/knowagent/identity/api/access.py` | 装配 Agent/Tickets API 端点与共享系统访问 helper，并修跨系统泄露与 CSRF 缺口 | 已完成；非集成测试 250 通过、18 项 API 集成测试已在真实 PostgreSQL 17 跑通 |
| `backend/tests/integration/test_agent_api.py`、`test_tickets_api.py`、`_fakes.py` | Agent/Tickets API 集成测试与共享 FakeRedis | 已完成；默认 skip 待环境变量启用 |
| `backend/tests/integration/test_agent_api.py` | 修复 `test_ask_question_validates_system_id_required` CSRF 头缺失（`d9ca72b`） | 已完成；18 项 API 集成测试在真实 PostgreSQL 17 全部通过 |
| `backend/.env` | 本地临时 LLM 模型切换为 `qwen3.5-27b` | 已完成；Phase 2 live 增量引用流通过；文件保持忽略 |
| `docs/development/03-feature-changelog.md` | 记录 Agent/Tickets API 装配与 review 修复 | 已完成 |
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
| `backend/src/knowagent/retrieval/` | Embedding Provider、关键词/向量检索、RRF、证据组织、可观测降级与指标端口 | 基础代码、review 修复和真实核心服务验收已完成 |
| `backend/src/knowagent/agent/` | 版本化 Prompt、Qwen grounded 增量流、声明级回答、引用验证、API/SSE 和答案快照 | 已完成；真实 `qwen3.5-27b` 集成通过，质量数据待评测 |
| `backend/src/knowagent/knowledge/application/indexing.py` | 批量 Embedding、模型契约校验与原子向量写回 | 已完成并接入 Worker；真实 Ollama/pgvector 通过 |
| `backend/migrations/versions/c8784d439b23_add_phase2_vector_and_lexical_retrieval.py` | `vector`/`pg_trgm`、向量列和 trigram 索引 | SQLite 往返和真实 PostgreSQL 17/pgvector 通过 |
| `backend/tests/unit/test_*retrieval.py`、`test_*embedding*.py`、`test_evidence_organizer.py`、`test_answer_generation.py`、`test_grounded_answer.py`、`test_knowledge_indexing.py` | Phase 2 第 1 项正常、边界、异常与隔离回归 | 已完成 |
| `backend/src/knowagent/agent/application/evidence_decision.py`、`reliable_question.py` | 确定性证据充分性、可靠拒答、故障分流和 SSE 事件 | 已完成；API/SSE 与真实 PostgreSQL 集成通过 |
| `backend/src/knowagent/tickets/`、`backend/src/knowagent/agent/infrastructure/sqlalchemy_models.py` | 判定留痕、拒答自动建单、运行幂等、时间窗合并和完整工单状态机 | 已完成；真实数据库/API/审核回流通过 |
| `backend/migrations/versions/cc99b700f739_add_evidence_decisions_and_refusal_.py` | `evidence_decisions`、`tickets`、外键、唯一约束和查询索引 | PostgreSQL 17 迁移与 `alembic check` 通过 |
| `backend/tests/unit/test_evidence_policy.py`、`test_refusal_tickets.py`、`test_reliable_question.py` | Phase 2 第 2 项正常、边界、异常、幂等和故障分流回归 | 已完成 |
| `backend/src/knowagent/tickets/application/review.py`、`tickets/infrastructure/sqlalchemy_repository.py` | 审核前 Embedding、工单来源/发布片段和候选发布事务 | 已完成；API 装配待补 |
| `backend/src/knowagent/retrieval/infrastructure/sqlalchemy_search.py`、`documents/domain/models.py` | `TICKET` 来源检索和工单 locator 契约 | 已完成；真实组合链路待验收 |
| `backend/src/knowagent/agent/application/answer_snapshots.py`、`agent/infrastructure/sqlalchemy_repository.py` | 回答与历史引用快照服务；父答案先于引用 flush | 真实 PostgreSQL 验证通过；问答 API 装配待补 |
| `backend/migrations/versions/c1738febb896_add_phase2_answer_citation_snapshots.py` | 答案/引用表、复合隔离约束、候选发布状态和工单来源外键 | SQLite 往返/check 与 PostgreSQL 17 升级通过 |
| `backend/tests/unit/test_knowledge_review.py`、`test_answer_snapshots.py`、`test_sqlalchemy_retrieval.py` | 审核重索引、来源追踪、历史快照和检索回归 | 已完成 |
| `backend/src/knowagent/agent/application/reliable_question.py`、`tickets/application/review.py`、`scripts/local-env.sh`、`model-service/src/knowagent_model/settings.py` | Phase 2 第 4 项 review 并发、幂等、进程安全和配置一致性修复 | 已完成并通过自动化验证；PID 沙箱外运行复验因审批服务 503 待补 |
| `backend/src/knowagent/retrieval/`、`backend/src/knowagent/platform/settings.py` | Phase 3 加权 RRF、Rerank provider、候选限制、严格契约与两级降级 | 已完成；后端全量、mypy、格式、安全扫描和检索核心 Pylint 通过 |
| `model-service/src/knowagent_model/`、`model-service/pyproject.toml` | `/v1/rerank`、FlagEmbedding 运行时、资源限制、健康降级和 optional extra | 代码与自动化完成；本机依赖安装/真实模型推理收尾中，目标 Linux 锁待资源信息 |
| `frontend/src/features/auth/UserHomePage.tsx`、`frontend/src/api/types.ts`、`frontend/src/styles.css` | 回答/拒答降级原因保存、文案和响应式 Alert | 组件回归与真实向量降级浏览器链路通过 |
| `docs/engineering/04-tech-decisions.md`、`docs/engineering/11-project-structure.md`、`docs/product/06-roadmap.md`、`docs/product/15-frontend-design.md`、`docs/operations/07-local-development.md` | TD-012、Phase 3 进度、模块/API、UI 与本地运行说明 | 已同步 |
| `docs/operations/09-runtime-resource-inventory.md` | 系统基线、宿主机/Docker/模型/Python 资源与缺口清单 | 已完成只读盘点；未安装或下载资源 |

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
| Phase 1 最终 live 集成验收 | 通过 | 固定 integration 资源复跑通过；真实 S3 put/get/delete、multipart、四格式持久化、幂等、v2 切换、双系统零泄漏和 1 个租约过期任务恢复均符合预期 |
| Phase 2 第 1 项后端全量测试 | 通过 | review 修复后 167 项测试通过，总覆盖率 91.06%；45 项相关测试覆盖召回、数据库异常降级/指标、索引、证据预算、Prompt、流终止、声明支撑和引用异常 |
| Phase 2 第 1 项静态检查 | 通过 | 相关 27 个源文件 mypy strict 零错误；本次 36 个 Python 文件 Black/isort 清洁；Pylint 10.00/10；全仓 Bandit 中高危 0 |
| Phase 2 第 1 项 Alembic | 通过（SQLite） | `upgrade head -> downgrade 3ba86a4c3d35 -> upgrade head` 和 `alembic check` 通过；真实 PostgreSQL 因 `vector` 扩展不兼容未运行 |
| model-service Ollama 适配自动化验证 | 通过 | review 修复后 39 项测试通过、1 项真实服务测试显式跳过，总覆盖率 90.58%；源文件与测试 mypy strict 零错误；Bandit 中高危 0 |
| model-service 真实 bge-m3 冒烟 | 通过（本地） | Ollama 0.3.14 复用 1.2 GB 模型 volume；ready 200，真实 `/api/embed` 返回 1024 维归一化向量；冷启动 18.21 秒、热请求 3.73 秒 |
| pgvector/Embedding/Qwen 真实链路 | 通过（核心服务） | 固定 integration 资源上真实双系统检索、Qwen 引用契约、答案快照、拒答工单和审核回流通过 |
| Phase 2 第 2 项后端单测/覆盖率 | 通过 | 46 项定向测试全部通过；证据决策、可靠问答和工单核心模块分支覆盖率 92.83% |
| Phase 2 第 2 项静态检查 | 通过（本次范围） | 18 个相关源/测试文件 Black/isort 清洁；111 个源文件 mypy strict 零错误；本次源文件 Pylint 10.00/10；全仓 Bandit 中高危 0 |
| Phase 2 第 2 项 Alembic/真实集成 | 通过（核心服务） | PostgreSQL 17 迁移/check、可靠拒答、证据判定、工单合并和完整状态往返通过 |
| Phase 2 第 4 项后端测试/覆盖率 | 通过 | 59 项相关测试和 243 项全量测试通过，总覆盖率 90.80% |
| Phase 2 第 4 项静态检查 | 范围通过 | 149 个 Python 文件 Black/isort 清洁；115 个源文件 mypy strict 零错误；14 个相关源文件 Pylint 10.00/10；全仓 Bandit 中高危 0。全仓 Pylint 9.77/10，剩余为 identity/systems 既有告警 |
| Phase 2 第 4 项 Alembic | 通过 | SQLite autogenerate、`upgrade -> downgrade -> upgrade` 和 `alembic check` 通过；本地 PostgreSQL 17.10 已升级到 `c1738febb896` |
| Phase 2 第 4 项 review 修复 | 通过（运行级 PID 复验待补） | 39 项定向回归、248 项后端测试和 90.72% 覆盖率通过；model-service 39 项/90.58%，前端 42 项、TypeScript、ESLint、生产构建，双后端 mypy/Bandit、相关 Pylint、SQLite 迁移往返/check、Bash 语法和 diff 检查通过 |
| Phase 2 核心服务 live 验收与 FK 顺序修复 | 通过 | 2 项 live 用例 36.85 秒通过；250 项标准测试通过、3 项 live 门禁跳过，覆盖率 90.72%；Black/isort、115 文件 mypy strict、本次范围 Pylint 10.00/10、Bandit 中高危 0 和 Bash 语法通过 |
| Phase 2 qwen3-max 全量测试与 API 集成验收 | 通过 | 后端 250 项 + 21 skip（87.64%）；前端 42 项；model-service 39 项 + 1 skip（90.58%）；Phase 2 live 2 项（qwen3-max，34.87s）；Agent/Tickets API live 18 项（真实 PostgreSQL 17 `knowagent_api_integration` 库，5.57s）；Phase 1 live 1 项（真实 MinIO/S3）；mypy strict 122 文件零错误；Bandit 中高危 0；test_agent_api CSRF 头修复已提交 `d9ca72b` |
| Phase 2 最终代码/静态验证 | 通过 | 后端 275 passed / 24 skipped，覆盖率 86.56%；125 个源文件 mypy strict 零错误；Black 检查 168 个文件清洁，isort 和 diff 检查通过。前端默认完整测试 47/47，TypeScript、ESLint、生产构建通过 |
| Phase 2 Worker/SSE/API 真实集成 | 通过 | `qwen3.5-27b` + PostgreSQL 17 + Redis + Ollama bge-m3：23 passed、6 warnings、36.69 秒；Alembic upgrade/check 无漂移；覆盖真实 Worker→Embedding、增量 grounded stream、token 隔离/单次消费、Agent/Tickets API 和审核回流 |
| Phase 3 显式降级真实浏览器检查 | 通过（向量降级拒答路径） | 本地 `visual.tester` 经真实 PostgreSQL 17/Redis/API/SSE 完成首次改密、系统选择、向量不可用回退关键词、拒答建单；1280x720 与 390x844 Alert 无横向溢出/重叠。Rerank 成功/失败回答路径由组件测试覆盖，真实模型路径待补 |
| Phase 3 三端自动化 | 通过（前端覆盖率门禁除外） | 后端 284 passed / 24 skipped（86.64%）；model-service 49 passed / 1 skipped（85.63%）；前端 47/47，TypeScript、ESLint、生产构建通过。前端全局 branch/function 覆盖率仍低于 80% |
| Phase 3 静态与安全检查 | 通过（本次范围） | Backend 126 源文件、model-service 8 源文件 mypy strict 零错误；相关格式清洁；检索核心 Pylint 10.00/10；双后端 Bandit 中高危 0 |
| Phase 3 本机/Docker 资源盘点 | 完成 | M1/8 GB；Python/Node/PostgreSQL/Redis/MinIO 版本已核对；`bge-m3` Docker 权重和两套 Rerank 本地权重已确认；四个 Python 环境无 Rerank 运行时，Docker 无 TEI |

## 9. 未运行验证与风险

1. 双端壳层和业务系统页面已使用隔离测试 API 完成桌面/移动浏览器截图与交互检查；真实 PostgreSQL/Redis 后端的完整页面链路仍待集成环境补充。
2. 默认密码批量导入仍有共享密码泄露风险；实现已强制摘要、首次改密、限流、会话撤销和审计，凭据分发流程仍需组织侧控制。
3. 核心、解析器和质量工具直接版本已固定；Python 传递依赖锁仍需在目标 Linux/Python 3.11 环境生成。
4. 本地 Ollama bge-m3 及 digest 强校验已在 Phase 2 live 验收中通过；目标 Linux 运行时、量化与完整安装尚未验证，本轮未重跑前端构建。
5. `npm audit --audit-level=moderate` 仍报告 React Router RSC 模式 CSRF 公告产生 2 个 high；自动修复会强制降级 `react-router-dom` 到 7.11.0，未在缺少 breaking change 评估时执行。
6. 四类解析器的 S3/PostgreSQL/Worker 完整组合已在本地 MinIO 验收通过；公司对象存储 TLS/内部 CA、服务端 5xx/限流和目标 Linux 厂商差异仍待 staging 验证。扫描 PDF 仅返回 `OCR_REQUIRED`，首版不执行 OCR。
7. 本轮使用现有 Python 3.11.11 环境并在 `/tmp` 补充四个锁定依赖；FastAPI、Redis client、pytest/pytest-cov 小版本低于项目锁定版本，结果不替代目标 Linux 按完整锁定依赖安装的发布证明。
8. Phase 2 迁移已在本地 PostgreSQL 17.10 升级到 `c1738febb896`，JSONB、向量列与复合外键成功落库；迁移锁时长、已有生产量级回填和查询计划仍待类生产数据验证。
9. Phase 2 功能、问答/SSE、工单 API、文档索引 Worker 和真实 pgvector/Embedding/Qwen 组合联调已通过；HNSW 在生产模型维度最终确认前不创建。剩余关闭门禁是 AC-004/AC-005 真实评测数据和业务页人工验收。
10. PID 启动身份的沙箱外受控测试因审批服务 503 未获授权，`shellcheck` 当前不可用；脚本已通过 Bash 语法和 diff 检查，仍需在本地运行一次“伪造过期启动时间后 stop 不发送信号”的复验。model-service 全目录 Black 检查另有未改动 `ollama.py` 的既有格式差异，本次变更文件清洁。
11. 真实 PostgreSQL/Redis/Qwen SSE 与 Worker 端到端已经通过；前端 jsdom 仍以 `FakeEventSource` 做回答和 Rerank 降级组件回归。真实浏览器已覆盖登录后的向量降级拒答与建单，带引用回答、Rerank 成功/失败和工单管理仍待真实业务数据。
12. AC-004/AC-005 评测 CLI 已就绪，但仓库没有至少 50 条真实标注 ESB 可回答问题和真实无知识问题集；任何通过数字在数据到位前都不成立。

## 10. 继续开发建议

新对话或新开发者接手时，建议下一步：

1. 先阅读 `docs/development/21-phase2-integration-acceptance.md`、`22-phase2-evaluation.md` 及 `agent`/`tickets` 模块，避免重复已经通过的 SSE/Worker 真实集成工作。
2. 下一步先按 `docs/operations/09-runtime-resource-inventory.md` 拆分本地模型加载路径，再确认依赖安装；随后完成真实推理和已发布知识的 Rerank 页面路径。并行取得真实评测集运行 `knowagent-evaluate-phase2`，两项均需记录真实质量/资源数据。

## 11. 接手时必须先读

```text
AI_DEVELOPMENT_RULES.md
docs/00_START_HERE.md
docs/development/10-current-status.md
docs/development/03-feature-changelog.md
docs/product/06-roadmap.md
docs/engineering/04-tech-decisions.md
```
