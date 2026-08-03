# 技术决策

本文件记录需要用户确认的技术选择。初始化阶段只记录已确认约束和待决事项，不将候选技术写成既定事实。

## 1. 当前技术约束

| 分类 | 已确认约束 | 待技术选型确认 |
| --- | --- | --- |
| 产品形态 | 企业内部 Web 产品；Python 3.11 + FastAPI 后端，React + Vite + Ant Design 前端 | 目标浏览器范围和公司前端制品发布规范 |
| 认证 | 用户端和管理端分别登录；统一账号表；用户 SQL 批量导入，管理员后台新增；Redis 服务端会话 | Redis Session 具体库/中间件版本、公司 SSO 协议 |
| 数据库 | 公司已有 PostgreSQL；确认 pgvector + pg_trgm、SQLAlchemy 2、Alembic、Psycopg 3 | DBA 扩展可用性、服务端版本、Schema 和权限 |
| 缓存 | 公司已有 Redis；确认用于 Celery broker 和服务端 Session，Python 客户端固定 redis-py 6.4.0 | 服务端版本、AOF/noeviction 配置、命名空间和容量 |
| 文件 | 公司已有对象存储；确认使用 S3 兼容协议和 boto3 客户端 | Endpoint、Bucket、Region、TLS CA 和最小权限账号 |
| LLM | 公司已有可发送内部知识的大模型 API | 协议、模型、限流、超时和费用 |
| Embedding | 公司没有现成 API；确认自建独立内网 Python 模型服务 | 目标服务器资源、模型精度/量化和性能基线 |
| Rerank | 公司没有现成 API；确认与 Embedding 共用独立内网模型服务 | 目标服务器资源、模型精度/量化和降级阈值 |
| 通知 | 公司已有通知 API | 契约、鉴权、模板、限流、回调和重试 |
| 部署 | 公司内网 Linux，禁止 Docker；确认 systemd + Nginx + 版本化发布目录 | 目标发行版/版本、目录权限、监控接入和发布账号 |
| 测试 | 外部服务和持久化必须有真实集成验证 | 无 Docker 条件下的隔离测试环境方案 |

## 2. 初始化阶段采用的规则

### TD-000：复用跨项目工程规则

```text
日期：2026-08-02
状态：已采用
确认依据：用户确认产品范围、账号方式、基础设施和部署约束
```

从 `retro/assets/rules/` 选择并按项目裁剪 7 条规则：

1. 产品应用定位边界。
2. 核心闭环后盘点可复用资产。
3. JWT/会话角色变更失效策略，最终实现取决于认证选型。
4. RAG 多通道降级，裁剪为 Rerank、向量、关键词、生成和工单链路。
5. LLM 提示词版本化。
6. 外部服务、持久化和异步流程集成测试；因禁止 Docker，使用隔离测试资源和类生产 Linux 环境，不强制 Testcontainers。
7. 模型、阈值、批大小、超时、重试和资源限制配置化。

未采用：Hibernate 实体脱敏规则（与 Python/SQLAlchemy 技术栈不适配）；图谱存储规则（当前需求不包含 GraphRAG）。

影响：这些是工程约束，不代表已经完成框架、模型或部署技术选型。

## 3. `knowledge-rag` 迁移评估输入

2026-08-02 对 `/Users/qijishuma/Documents/AI_Agent/knowledge-rag` 的代码和配置进行了只读盘点。结论是“按模块重构迁移”，不是复制项目或沿用其完整技术方案。

| 来源能力 | 结论 | 对本项目的约束 |
| --- | --- | --- |
| 模块化单体的 ingest / retrieval / conversation 边界 | 借鉴设计 | 架构阶段保持领域边界，但重新定义输入输出模型 |
| 前端 API 解包、401 事件、POST SSE 解析、流式状态 hook | 重构后迁移 | 抽离业务 URL 和事件类型，补协议解析、401、取消和异常关闭测试 |
| SSE 阶段事件、错误事件优先级、Prompt token 预算 | 高价值设计 | 进入问答编排协议和测试基线 |
| SHA-256 幂等、异步入库状态、失败降级 | 重构后迁移 | 入库任务改为持久化可恢复；降级需覆盖关键词检索和工单 |
| Citation snippet 持久化 | 继承设计 | 引用保存证据快照和结构化 `SourceLocator` |
| parser / chunker | 仅作反例和重构起点 | 来源实现不支持 Excel 精确定位，且 `sourceRef` 为空；先设计定位模型再实现解析与切分 |
| embedding / rerank provider | 继承接口思想，重做适配层 | 去除 bge-m3 1024 维、Ollama、TEI 和 `ChunkVector` 的硬耦合 |
| vectorstore / retrieval | 重构后迁移 | 用 `system_id` 强过滤；增加关键词混合召回、证据充分性判断和可靠拒答 |
| 本地认证、异常、响应、Bootstrap | 仅借鉴模式 | 来源实现存在角色 claim 过期、异常处理 TODO、Bootstrap 弱校验等问题，不直接复制 |
| Docker、Compose、容器监控和容器备份脚本 | 不迁移 | 公司明确禁止 Docker；只参考 Nginx SSE、密钥、备份校验和监控指标思想 |
| GraphRAG | 首版不迁移 | 当前问题不需要图谱复杂度，先用混合检索和 Rerank 验证 |

迁移门禁：任何来源代码只有在技术栈确认、目标接口定义完成、来源测试证据核验后才能复制。`retro` 资产目录中的 README 不是可靠性证明，必须与当前源码和可执行测试交叉验证。

## 4. 后续技术选型清单

| ID | 决策主题 | 必须比较的方向 | 主要评价维度 | 状态 |
| --- | --- | --- | --- | --- |
| TD-001 | 前后端与应用形态 | Java + Python 推理、全 Python、纯 Java | 学习价值、维护、类型安全、生态、部署 | 已确认：全 Python |
| TD-002 | 检索与向量存储 | PostgreSQL 扩展、Qdrant、OpenSearch | 数据一致性、召回、运维、扩展 | 已确认：PostgreSQL 扩展，待 DBA 验证 |
| TD-003 | Embedding 推理与 provider 契约 | 应用内、独立内网服务、外部 API | 中文效果、维度契约、硬件、吞吐、隔离、升级 | 已确认：独立内网服务 |
| TD-004 | Rerank 推理与 provider 契约 | 本地交叉编码模型、LLM 重排、延后启用 | 候选模型契约、效果、延迟、成本、降级 | 已确认：独立内网服务 |
| TD-005 | 持久化异步任务机制 | Celery、Dramatiq、PostgreSQL 自研 worker | 幂等、租约、重试、重启恢复、无 Docker 部署、运维 | 已确认：Celery + Redis + PostgreSQL 状态 |
| TD-006 | 本地认证与 SSO 适配 | Redis Session、短 JWT、长 JWT | 撤销、CSRF、账号来源、扩展 SSO、安全 | 已确认：双入口 + Redis Session |
| TD-007 | 文档解析与统一来源定位 | 格式专用解析器组合、Unstructured、Apache Tika | PDF 页码、Word/Markdown 标题、Excel sheet/cell、性能、安全 | 已确认：格式专用 Python 解析器组合 |
| TD-008 | 非 Docker Linux 部署 | systemd 原生部署、Ansible 编排、Supervisor | 可重复、回滚、日志、权限、运维 | 已确认：systemd + Nginx + 版本化发布 |
| TD-009 | 检索、证据充分性与拒答决策 | LangGraph + 领域服务、自研状态机、端到端 RAG 框架 | `system_id` 隔离、召回、可解释阈值、降级、工单触发 | 已确认：LangGraph 状态图 + 自定义领域服务 |
| TD-010 | 应用框架、前端组件与核心版本基线 | FastAPI + SQLAlchemy、Django + DRF、FastAPI + SQLModel | 类型、异步/流式、后台效率、依赖兼容、维护 | 已确认：FastAPI + SQLAlchemy + React/Ant Design |
| TD-011 | 对象存储协议与客户端 | S3 + boto3、S3 + MinIO SDK、公司自定义 REST + httpx | 兼容性、流式上传、重试、维护和迁移 | 已确认：S3 兼容协议 + boto3 |

## 5. 技术决策记录要求

每项技术选型必须记录背景、2-3 个候选方案、性能影响、成本、维护复杂度、风险、推荐理由和用户确认。依赖版本需通过官方来源核验后再写入，不得在初始化阶段猜测版本。

## 6. 已确认技术决策

### TD-001：全 Python 后端与独立 Web 前端

- **日期**：2026-08-02
- **决策**：选择全 Python 后端方案；后端应用、异步任务和 RAG 编排使用 Python 技术栈，浏览器端继续采用独立 React/TypeScript Web 前端。
- **目的**：降低个人学习过程中的语言切换成本，并充分利用 Python 在文档处理、Embedding、Rerank、RAG 评测和模型推理方面的成熟生态。
- **原因**：用户在三套总体方案中明确选择全 Python。该选择与“通过真实项目提升个人 Agent 能力”的目标一致，也便于复用同一套领域模型、配置和测试工具。
- **备选方案**：Java 模块化单体 + Python 推理服务的企业治理能力更成熟，但需要维护两套语言和工具链；纯 Java 运行时更统一，但本地模型适配和实验成本更高。
- **权衡**：全 Python 能提高开发与模型实验效率，但必须通过模块边界、类型检查、数据库事务、后台任务隔离和真实集成测试避免原型式代码演变为难维护系统。
- **影响**：后续 TD-002 至 TD-009 均以 Python 生态重新比较；`knowledge-rag` 的 Java 代码不直接迁移，仅复用经过验证的协议、状态机和设计模式。
- **版本状态**：具体 Python、FastAPI、SQLAlchemy、前端和测试工具版本在完整技术包确认后统一锁定并核验。

### TD-003：独立内网 Embedding 服务

- **日期**：2026-08-02
- **决策**：公司没有可用 Embedding API，因此使用独立 Python `model-service` 在内网部署成熟预训练模型，并通过稳定 HTTP provider 契约供主应用和任务 worker 调用。
- **目的**：为文档片段和用户问题生成向量，同时避免 Web 进程重复加载大模型或被推理阻塞。
- **原因**：独立服务可以单独配置进程、内存、批处理和超时，也允许后续替换模型而不改问答、入库和数据库领域逻辑。
- **备选方案**：模型直接加载进 FastAPI 主应用，原型简单但多 worker 重复占用内存且故障相互影响；外部商业 API 运维最少，但公司当前没有该服务且存在数据与费用边界。
- **权衡**：增加一个 systemd 服务和健康检查；换取模型资源隔离、独立升级和清晰降级能力。
- **初始评测基线**：以 `BAAI/bge-m3` 作为中文和多语言质量基线；模型名称、向量维度和归一化规则由模型注册配置唯一管理，不写死在实体或 SQL 中。
- **接口基线**：提供批量 `/v1/embeddings` 和 `/health`；限制批大小和文本长度，返回模型标识、版本和向量维度。
- **资源门禁**：在目标 Linux 服务器上用真实 ESB 样本完成延迟、吞吐和内存测试后，再确认 PyTorch、ONNX Runtime 或 INT8 量化方式；资源不足时可替换轻量模型而不改变 provider 契约。
- **本地适配决策（2026-08-03）**：用户确认先复用 `knowledge-rag` 已下载的 Ollama `bge-m3`。`model-service` 作为防腐层把 Ollama `/api/embed`（旧版回退 `/api/embeddings`）转换为稳定 `/v1/embeddings` 契约，并负责维度校验和 L2 归一化；主应用不直接依赖 Ollama 协议。
- **实施状态（2026-08-03）**：主应用侧 HTTP Provider、批量索引、模型契约校验和原子向量写回已实现；`model-service` 的 Ollama 适配、健康检查、请求限制及自动化测试已实现。适配层在 readiness 和每次推理前校验实际模型 tag 与 digest；配置的对外 `model_version` 必须以 8-64 位 digest 前缀结尾，避免模型替换后误用旧版本标签。健康检查使用独立短超时，推理日志只记录脱敏状态、耗时和错误类别。本地默认模型版本对应现有 digest 前缀 `daec91ff`，生产必须按实际 manifest 同步覆盖版本与 digest。真实 bge-m3 冒烟已返回 1024 维归一化向量，冷启动约 18.21 秒、热请求约 3.73 秒；目标 Linux 的最终推理运行时、量化和组合验收仍受资源门禁约束。

### TD-004：独立内网 Rerank 服务

- **日期**：2026-08-02
- **决策**：Rerank 与 Embedding 共用独立 Python `model-service` 的部署边界，但使用独立 provider 接口、模型配置、并发限制和超时。
- **目的**：对混合召回候选进行交叉编码精排，提高技术术语、配置项和相似接入问题的排序质量。
- **原因**：公司没有现成 Rerank API；独立接口可在模型不可用或超时时明确降级到基础召回排序，不阻塞问答主流程。
- **备选方案**：使用公司 LLM 对候选重排会增加费用、延迟和输出不稳定性；首版完全不启用 Rerank 运维最简单，但难以达到完整质量目标。
- **权衡**：Rerank 比 Embedding 更耗计算，因此只处理检索后的少量候选，并设置严格 top-k、超时和并发上限。
- **初始评测基线**：以 `BAAI/bge-reranker-v2-m3` 作为质量基线；是否量化或更换轻量模型由目标服务器压测与离线评测共同决定。
- **接口基线**：提供 `/v1/rerank` 和 `/health`，输入 query、候选文本和 `top_n`，输出原始索引、相关性分数、模型标识和版本。
- **降级**：超时、服务不可用或返回非法结果时，退回混合召回的融合排序并记录指标；不得跨 `system_id` 扩大候选范围。

### TD-002：PostgreSQL 混合检索与向量存储

- **日期**：2026-08-02
- **决策**：优先使用公司 PostgreSQL，并启用 `pgvector` 与 `pg_trgm`；向量 HNSW 召回和字符/技术术语召回在应用层通过 RRF 融合，再进入 Rerank。
- **目的**：在满足多系统混合检索的同时，减少新增基础设施并保证文档、片段、定位信息和向量的一致性。
- **原因**：当前咨询量和预期知识规模不需要独立搜索集群；PostgreSQL 已由公司提供，统一存储便于事务、权限过滤、备份和索引重建。
- **备选方案**：Qdrant 的向量过滤和扩展能力更强，但会增加无 Docker 环境下的安装、同步、备份和监控成本；OpenSearch 的 BM25 与混合搜索完整，但资源和运维成本对当前规模明显过高。
- **权衡**：超大规模向量检索能力不如专用服务，中文关键词质量也需要用 ESB 真实问题调优；换取更低的运维复杂度和更强的数据一致性。
- **数据隔离**：所有关键词和向量查询必须在数据库层强制过滤 `system_id` 与已发布文档版本，禁止先全局召回再由应用过滤。
- **迁移边界**：通过 `VectorStoreProvider` 和 `LexicalSearchProvider` 隔离存储实现；若未来规模或 DBA 限制不适合 PostgreSQL，可从原始片段重建 Qdrant/OpenSearch 索引。
- **实施前门禁**：由 DBA 确认 PostgreSQL 版本并允许执行 `CREATE EXTENSION vector`、`CREATE EXTENSION pg_trgm`；若任一扩展不可用，重新执行 TD-002 选型，不以字符串拼接或进程内向量索引绕过。
- **实施状态（2026-08-03）**：基础代码和迁移已落地，包含数据库层 `system_id + PUBLISHED + DOCUMENT` 过滤、pg_trgm 相似度、pgvector 余弦距离、RRF、数据库异常映射、结构化降级日志/指标端口、无固定维度向量列和 trigram GIN 索引。本机 PostgreSQL 16 无可加载的 pgvector 构件，因此真实 PostgreSQL 验收未通过门禁；Embedding 维度锁定前不创建 HNSW。

### TD-005：Celery 异步任务与 PostgreSQL 状态事实源

- **日期**：2026-08-02
- **决策**：使用 Celery + 公司 Redis 负责异步任务投递和 worker 调度，PostgreSQL `jobs`/领域任务表保存任务状态、阶段进度、幂等键、租约、重试次数和最终错误。
- **目的**：可靠执行文档解析、切分、Embedding、索引、重新索引、知识回流和通知重试，并在 API、worker 或服务器重启后恢复。
- **原因**：Celery 的重试、超时、并发、定时调度和运维生态比自研任务队列成熟；Redis 已由公司提供。把 PostgreSQL 作为事实源可避免把不可审计的 broker 状态等同于业务状态。
- **备选方案**：Dramatiq API 更轻但复杂工作流和运维生态较弱；使用 PostgreSQL `SKIP LOCKED` 自研 worker 可减少基础设施，但需要自行实现调度、心跳、租约、恢复和并发控制，研发风险更高。
- **权衡**：增加 Celery 配置和至少一个独立 worker 进程；换取成熟任务执行能力。Celery 消息只携带 `job_id`，不得携带文档全文、向量或大对象。
- **可靠性配置**：启用 late ack、worker 丢失时拒绝确认、低预取、软/硬超时和指数退避；Redis 需要 AOF、合理持久化策略、独立命名空间和禁止因缓存淘汰任务消息。
- **幂等与恢复**：任务每个阶段依据数据库状态和幂等键执行；定时扫描超时租约并恢复或转人工重试，允许 broker 重复投递但禁止重复发布知识或重复写入向量。
- **通知一致性**：工单和知识事务内写入 Outbox，Celery 只发送已提交的 Outbox 记录；通知失败不回滚工单状态，并保留永久失败和人工重试入口。
- **部署边界**：至少运行 `knowagent-api.service` 和 `knowagent-worker.service`；需要周期恢复和统计时增加单实例 `knowagent-scheduler.service`。

### TD-006：双登录入口与统一服务端会话

- **日期**：2026-08-02
- **决策**：保留用户端和管理端双方登录，提供独立登录表单和接口，但共享单一账号表、认证服务、Argon2id 密码策略、Redis 服务端 Session 和审计逻辑。
- **目的**：满足用户与管理员不同的入口、账号来源和操作范围，同时避免维护两套密码、会话和安全实现。
- **账号来源**：普通用户账号由受控 SQL/导入脚本批量创建；管理员账号由已登录管理员在后台新增；首个管理员通过一次性 CLI 或受控初始化 SQL 创建。
- **角色模型**：账号至少包含 `USER`、`SYSTEM_OWNER`、`ADMIN`；系统负责人是用户账号通过业务系统负责人映射获得的权限，不建立第三套账号表或登录入口。
- **默认密码**：导入过程只允许写 Argon2id 摘要，不允许 SQL 文件包含明文默认密码；新账号设置 `must_change_password=true` 和凭据签发批次，首次登录完成改密前只能访问改密、登出和必要的会话检查接口。
- **会话**：登录成功生成高熵随机 Session ID，仅通过 `HttpOnly`、`Secure`、`SameSite=Lax` Cookie 返回，服务端存入 Redis；首版不实现 JWT、Refresh Token 或“记住登录”。
- **入口隔离**：用户入口仅接受 `USER`/`SYSTEM_OWNER`，管理入口仅接受 `ADMIN`；所有 API 在服务端重新校验角色和系统负责人映射，不能依赖不同表单或前端隐藏按钮完成授权。
- **备选方案**：短 JWT + Refresh Token 适合多入口客户端但刷新、轮换和撤销复杂；长 JWT 实现简单但角色、禁用和密码变更无法及时失效。Redis Session 更符合当前同域内部 Web 和现有基础设施。
- **权衡**：每个请求增加一次 Redis 会话读取，并需要处理 Redis 不可用；换取即时注销、禁用和角色变更生效。Redis 故障时鉴权失败关闭，不允许默认放行。
- **安全底线**：登录限流、失败审计、会话固定防护、修改类请求 CSRF 防护、密码重置后撤销全部 Session；默认密码策略属于临时开户流程，不得长期有效。
- **SSO 演进**：认证层保留 `IdentityProvider` 接口；未来接入 OIDC/SAML 后仍映射到本地账号、角色和系统负责人关系，保留本地管理员应急入口。

### TD-007：格式专用解析器组合与统一来源定位

- **日期**：2026-08-02
- **决策**：采用格式专用 Python 解析器组合：文本型 PDF 使用 PyMuPDF，`.docx` 使用 `python-docx`，Markdown 使用 `markdown-it-py` token/AST，`.xlsx` 使用 `openpyxl`。第三方库统一封装在 `DocumentParser` 适配层之后，领域层不直接依赖其对象模型。
- **目的**：在解析 PDF、Word、Markdown 和 Excel 时保留各格式特有的结构和精确引用位置，为结构化切分、答案引用、历史证据快照和重新索引提供稳定输入。
- **统一契约**：解析器输出格式无关的语义块和 `SourceLocator`，至少包含 `document_id`、`document_version_id`、`source_type` 和块序号；PDF 增加页码及可选坐标，Word 增加标题路径及段落/表格序号，Markdown 增加标题路径及源行范围，Excel 增加工作表名及单元格范围。字段采用按格式校验的联合类型，禁止把定位信息压成不可校验的自由文本。
- **切分边界**：先解析为标题、段落、列表、代码块和表格等语义块，再按标题层级和 token 预算组合；表格按可读行组切分并重复必要表头，不跨工作表拼接；重叠只发生在同一结构边界内。每个知识片段保存完整定位集合和证据文本快照，不能在切分后反推来源。
- **安全与资源限制**：上传时校验扩展名、MIME 和文件签名，限制文件大小、页数、段落数、工作表数、行列数及解析时间；Office 文件不得执行宏或外部链接，压缩容器需防解压炸弹，受密码保护或损坏文件进入可诊断失败状态。解析只在受限 Celery worker 中进行，原文件保存在对象存储。
- **扫描与旧格式边界**：首版支持文本型 `.pdf`、`.docx`、`.md`、`.xlsx`。扫描 PDF 通过文本密度等信号识别并标记 `OCR_REQUIRED`，不得以空内容成功入库；旧版 `.doc`/`.xls` 返回明确不支持状态。OCR 是否进入后续阶段根据真实样本另行选型。
- **性能影响**：按文件格式仅调用对应解析器，避免通用解析框架的完整依赖链；大文件在 worker 中流式或分页处理并批量写入，API 进程不执行解析。Excel 必须设置工作簿和单元格上限，避免整表加载导致内存失控。
- **成本与维护**：无需新增常驻解析服务，软件许可成本低；代价是维护四个适配器、统一语义块模型和各格式回归样本。每种格式必须覆盖结构、定位、损坏文件、资源上限和幂等重跑测试。
- **备选方案**：Unstructured 格式覆盖广、原型快，但依赖和资源占用较重，精确引用仍需二次加工；Apache Tika 类型覆盖成熟，但需要 Java 运行时且输出偏扁平，不符合全 Python 主方案和精确来源定位要求。
- **风险与回滚**：复杂排版、合并单元格和异常 Office 文件可能产生结构损失。解析结果记录 `parser_name`、`parser_version` 和 `schema_version`；升级单个适配器失败时可回退其版本，并从对象存储原文件重新解析，不影响其他格式。
- **版本状态**：本决策只锁定库边界，不猜测依赖版本；在完整技术包锁定时通过官方包源核验 PyMuPDF、`python-docx`、`markdown-it-py`、`openpyxl` 与目标 Python 版本的兼容性。

### TD-008：systemd + Nginx 的非 Docker Linux 部署

- **日期**：2026-08-02
- **决策**：目标 Linux 服务器采用原生 systemd 管理服务、Nginx 提供前端静态资源和反向代理，并通过版本化发布目录与 `current` 软链接完成切换；Docker、Compose 和容器运行时不作为部署前提。
- **目的**：在公司禁止 Docker 的条件下，为 Web API、Celery worker、单实例 scheduler 和模型服务提供可重复安装、进程守护、健康检查、日志、升级和回滚能力。
- **进程边界**：至少包含 `knowagent-api.service`、`knowagent-worker.service` 和 `knowagent-model.service`；需要周期恢复、统计或 Outbox 扫描时增加单实例 `knowagent-scheduler.service`。各服务独立设置用户、资源限制、重启策略、启动超时和环境文件，禁止以 root 运行应用进程。
- **反向代理**：Nginx 托管前端构建产物并代理 `/api` 和流式问答连接；流式路由关闭代理缓冲并设置合理的读取超时。TLS、安全头、请求体限制、上传超时和登录/API 限流在部署阶段按公司内网规范固化。
- **发布布局**：使用 `/opt/knowagent/releases/<release_id>` 保存不可变发布版本，`/opt/knowagent/current` 指向当前版本；配置和密钥位于受权限保护的 `/etc/knowagent`，运行时临时目录和模型文件与应用版本分离。发布包包含后端构建产物、锁定依赖或离线 wheelhouse、前端 `dist`、迁移文件、配置模板、校验和及发布清单，不打包真实密钥。
- **发布流程**：在切换前校验包完整性、创建目标 Python 虚拟环境、安装锁定依赖、校验配置、执行数据库迁移并运行健康检查；通过后原子切换 `current`，按依赖顺序重启服务，再验证 API、worker、模型服务和静态页面。模型权重独立版本化和校验，避免每次应用发布重复复制大文件。
- **数据库迁移与回滚**：Alembic 迁移采用 expand/contract 和向后兼容策略；新增结构先发布，删除或重命名推迟到旧应用不再可能回滚后的独立发布。应用回滚通过恢复旧 `current` 指针并重启完成；数据库只在已验证且必要时执行专门回滚，不能把破坏性 downgrade 当作默认自动步骤。
- **日志与监控**：应用输出结构化日志，由 journald 收集并设置保留策略；Nginx 访问/错误日志按公司规范轮转。至少监控进程存活、健康端点、请求错误率和延迟、Celery 队列/失败任务、模型服务延迟、磁盘空间以及 PostgreSQL/Redis 依赖状态。
- **性能与成本**：systemd 和 Nginx 资源开销低，无额外软件许可或容器平台成本；前端静态资源由 Nginx 直接服务，API、任务和推理进程可独立配置并发与资源上限。维护成本集中在发布脚本、unit、Nginx 模板和类生产 Linux 验证。
- **备选方案**：Ansible + systemd 更适合多服务器统一初始化，但对首版单套环境增加学习和维护成本，可在服务器数量增加时补充；Supervisor 配置简单，但会增加进程管理层，权限、服务依赖、系统启动和日志整合不如 systemd 原生方案。
- **风险与缓解**：原生部署可能出现环境漂移，通过锁定依赖、离线构建物、发布清单、校验和、幂等安装脚本和类生产验证降低风险。磁盘保留最近若干稳定版本并设置清理策略；回滚前必须确认目标版本与当前数据库 Schema 兼容。
- **版本状态**：目标 Linux 发行版、Python、Nginx、systemd 和 Node 构建环境版本待服务器信息确认后统一锁定；生产服务器只运行前端构建产物，不要求安装 Node.js。

### TD-009：LangGraph 状态图与可解释的 RAG 决策链

- **日期**：2026-08-02
- **决策**：采用 LangGraph 的类型化状态图编排单次问答和多轮分支，检索、权限、证据判断、引用、工单和持久化由自定义领域服务实现。LangGraph 通过项目自有 `QuestionWorkflow` 接口接入，不允许框架类型穿透 API、领域模型或存储层。
- **目的**：在支持意图识别、多轮问题改写、混合检索、Rerank、流式回答和工单分支的同时，保持每个决策节点可测试、可观测、可替换，避免把可靠拒答交给单次提示词或不可解释的端到端链。
- **状态事实源**：PostgreSQL 保存账号、会话业务记录、对话、消息、证据快照、问答判定、工单和分析数据，是唯一业务事实源。LangGraph state/checkpoint 只服务于一次工作流执行和技术恢复，不替代领域事务，不作为工单或知识状态的最终依据。
- **主流程**：服务端先校验账号、角色和所选 `system_id`，再执行意图识别与多轮问题改写、向量/关键词并行召回、RRF 融合、Rerank、证据充分性判断、基于证据生成、引用校验和结果持久化；证据不足时进入拒答及工单创建/合并分支。用户切换业务系统必须显式选择并重新鉴权，模型不能自行扩大检索范围。
- **多轮策略**：从 PostgreSQL 加载有界的最近消息和滚动摘要，解析“这个配置”“上一步”等指代并生成独立检索问题；原始问题、改写问题和摘要版本均留痕。历史上下文只能帮助改写，不能作为公司事实证据，最终答案仍必须由当前系统的已发布知识支撑。
- **检索与隔离**：向量和关键词查询都必须在数据库层先过滤 `system_id`、可见范围和已发布文档版本，再各自召回；应用层只对同一隔离范围内的结果执行 RRF 和 Rerank。Rerank 失败降级到融合排序，向量服务失败降级到关键词检索，但任何降级都不得取消系统隔离。
- **证据充分性**：先执行确定性硬门禁，包括是否存在有效证据、定位是否完整、候选分数/差距、关键实体或步骤覆盖和引用可用性；阈值全部配置化并由 ESB 评测集校准，不在代码中猜测固定值。仅对边界样本调用结构化 LLM evaluator 判断问题是否被证据覆盖，LLM 自信度不能覆盖硬门禁失败。
- **回答与引用校验**：生成模型只能使用编号证据片段并输出声明级引用。基础门禁要求每条声明逐字出现在对应引用原文中，服务端校验引用 ID、`SourceLocator`、证据快照和声明映射；校验失败转为证据不足，不把模型生成文本直接保存为已验证答案。问答 Prompt 使用随包发布的不可变版本资源并记录运营元数据，运行结果携带模型和 Prompt 版本。
- **拒答与工单**：只有 `INSUFFICIENT_EVIDENCE`、`CONFLICTING_EVIDENCE` 等知识原因创建或合并工单；LLM、Embedding、Rerank、PostgreSQL 或网络故障归类为 `SYSTEM_FAILURE`，返回可重试错误并告警，不污染知识缺口统计。工单幂等键至少包含业务系统、规范化问题和有效时间窗，相似工单只关联或追加，不无界重复创建。
- **流式与错误语义**：对外暴露稳定的阶段事件、文本增量、完成和错误事件；一旦后端已返回业务错误，后续连接断开不得覆盖真实原因。客户端取消只终止可取消的生成，不回滚已经提交的审计或工单事务。
- **性能与成本**：LangGraph 调度开销相对模型和检索延迟可忽略；通过合并意图识别与问题改写、限制召回/Rerank top-k、仅在边界样本调用 evaluator、限制上下文消息和 token 预算控制延迟与 API 成本。每个节点记录耗时、候选数量、降级原因和 prompt/model 版本。
- **备选方案**：完全自研显式状态机依赖更少，但复杂多轮、分支、流式追踪和恢复逻辑需长期自行维护；LlamaIndex/LangChain 端到端 RAG 原型快，但容易与既定解析器、`SourceLocator`、PostgreSQL 事实源及数据库层 `system_id` 强隔离产生耦合。
- **风险与回滚**：主要风险是状态图膨胀和框架版本变化。图节点保持薄编排，领域规则放在普通 Python 服务；通过固定版本、工作流契约测试和 `QuestionWorkflow` 适配层隔离 LangGraph。需要移除框架时，可按相同节点顺序改用自研 orchestrator，复用全部领域服务和测试。
- **版本状态**：LangGraph 及其兼容依赖在完整技术包锁定时通过官方包源核验；不因选择 LangGraph 默认引入 LangChain 的端到端检索、向量存储或文档模型。

### TD-010：FastAPI + SQLAlchemy + React/Ant Design 应用基线

- **日期**：2026-08-02
- **决策**：后端采用 Python 3.11、FastAPI、Pydantic 2、SQLAlchemy 2、Alembic 和 Psycopg 3；前端采用 React、TypeScript、Vite、React Router、TanStack Query、Ant Design 和 Lucide React。SQLAlchemy ORM 实体、Pydantic API DTO 和领域模型保持分离，不使用 SQLModel 合并这些职责。
- **目的**：为双登录入口、问答流式响应、文档异步处理、管理后台密集表格和复杂领域事务提供类型清晰、生态成熟且适合 Python RAG 的统一应用基础。
- **后端边界**：FastAPI 负责 HTTP、校验、依赖注入和流式协议；Pydantic 负责配置及边界 DTO；SQLAlchemy 负责显式事务和查询；Alembic 负责 Schema 演进；Celery 只执行异步任务；LangGraph 只编排问答流程。API 层不得直接拼接向量 SQL 或承载工单/权限领域规则。
- **前端边界**：Ant Design 提供表单、表格、分页、抽屉、弹窗、菜单和反馈等成熟控件，并通过主题配置映射项目设计 token；Lucide React 统一图标，不混用 Ant Design 图标体系；TanStack Query 管理服务端状态，React Router 管理用户端/管理端路由与守卫。本地 UI 状态保持在组件或轻量 context，不默认引入全局状态库。
- **性能策略**：问答、用户端和管理后台按路由拆包；Ant Design 按模块导入，图表、文档预览和编辑器延迟加载；表格使用服务端分页、筛选和排序。后端使用异步 HTTP 客户端和数据库连接池，但 CPU/模型/文档任务不在 API event loop 中执行。
- **核心版本基线**：

  | 类别 | 组件 | 基线版本 |
  | --- | --- | --- |
  | 运行时 | Python | 3.11.x |
  | Web/API | FastAPI | 0.141.1 |
  | 数据模型 | Pydantic | 2.13.4 |
  | ORM | SQLAlchemy | 2.0.51 |
  | 迁移 | Alembic | 1.18.5 |
  | PostgreSQL 驱动 | Psycopg | 3.3.4 |
  | pgvector Python 适配 | pgvector | 0.5.0 |
  | 异步任务 | Celery | 5.6.3 |
  | Redis 客户端 | redis-py | 6.4.0 |
  | Agent 编排 | LangGraph | 1.2.10 |
  | 前端运行时 | React / React DOM | 19.2.8 |
  | 前端构建 | Vite | 8.2.0 |
  | 路由 | React Router DOM | 7.18.2 |
  | 服务端状态 | TanStack Query | 5.101.4 |
  | UI 组件 | Ant Design | 6.5.3 |
  | 图标 | Lucide React | 1.28.0 |
  | 构建运行时 | Node.js | 24.x，仅构建环境 |

- **兼容性证据**：2026-08-02 已通过 PyPI/npm 官方索引核验上述版本存在；核心 Python 直接依赖组合使用 `pip --dry-run --ignore-installed` 解析通过。React Router、TanStack Query、Ant Design 和 Lucide 的 peer range 均覆盖 React 19，Vite 8 支持 Node 24。redis-py 8.1.0 与 Celery 5.6.3 使用的 Kombu `<6.5` 约束冲突，因此明确固定为兼容的 6.4.0。
- **运行时调整**：用户在 2026-08-02 明确将运行时从 Python 3.12 调整为 Python 3.11，以直接复用开发机现有的 3.11.11 环境并减少跨版本验证成本。代价是放弃 Python 3.12 的部分新特性和更长生命周期；当前项目不依赖 3.12 专属语法或标准库能力，回滚到 3.12 只需重新确认依赖并调整运行时约束。
- **验证限制**：当前开发机 Python 3.11.11 可用于本地配置和依赖验证；目标 Linux 上的完整安装、导入、构建和模型推理仍未验证，不把本地解析结果视为生产部署验证。
- **备选方案**：Django + DRF 内置治理能力强，但自带后台和认证与本项目定制双入口、React 管理后台存在重复，异步流式和模型服务边界更重；FastAPI + SQLModel 原型简洁，但会模糊 API DTO、领域模型和 ORM 实体边界，不利于复杂向量查询、权限和工单事务。Radix/shadcn 的 UI 自由度更高，但表格、表单和后台状态需要更多自行组装。
- **成本与维护**：所有核心组件均为开源软件，无新增许可费用；代价是维护 Python 与 TypeScript 两套构建和检查工具。通过固定直接依赖、提交锁文件、自动化安全扫描和版本化发布控制升级风险。
- **回滚与升级**：升级以单独变更执行，先更新锁文件和兼容性测试，再进入发布；出现回归时恢复上一份锁文件和发布目录。禁止使用不受约束的宽版本范围直接构建生产包。
- **锁定状态**：核心应用、TD-007 解析器和测试/静态检查工具的直接版本已写入 `backend/pyproject.toml`；前端直接与传递依赖已写入 `frontend/package-lock.json`。Python 传递依赖锁和 PyTorch/Transformers/ONNX 模型运行时仍必须等待目标 Linux 与模型服务器资源后生成，不能在此猜测。

### TD-011：S3 兼容对象存储与 boto3 客户端

- **日期**：2026-08-02
- **决策**：对象存储采用 S3 兼容协议，基础设施适配器使用 `boto3==1.43.62`；业务层只依赖 `ObjectStore` 端口，不暴露 boto3、botocore 或厂商类型。
- **目的**：复用公司现有对象存储，可靠保存原始文档和确定性派生清单，并支持流式/分片上传、下载、删除、校验和可诊断错误。
- **方案比较**：boto3 对 MinIO、Ceph 和多数云厂商 S3 接口的兼容及运维经验最成熟，但依赖树较大且同步调用必须隔离出 API 事件循环；MinIO SDK 更轻、API 更直接，但跨厂商细节兼容与团队经验较弱；自定义 REST 可复用 httpx，却需要自行维护签名、分片、重试和错误映射，协议未知时风险最高。
- **性能与成本**：上传使用 SDK 管理的分片和连接池；FastAPI 通过受控线程执行同步 SDK 调用，解析 Worker 直接使用同步端口。继续使用现有对象存储，不新增服务费用；增加 boto3/botocore 依赖和版本维护成本。
- **安全**：Endpoint、Bucket、Region、Access Key、Secret Key、TLS 校验和可选 CA 路径全部由环境变量注入；凭据不进入数据库、日志或响应。对象 key 使用不可预测业务 ID，浏览器不接收长期存储凭据。
- **可靠性**：原文件和派生清单使用确定性 key；数据库幂等键、任务租约和终态决定业务结果，SDK/Broker 重试不替代 PostgreSQL 事实状态。只对明确的超时、连接和 5xx/限流错误自动重试，权限、Bucket、签名和输入错误直接失败。
- **风险与回滚**：公司 Endpoint 的具体兼容差异仍需用隔离 Bucket 做真实契约测试。若不兼容，通过 `ObjectStore` 端口替换为厂商适配器；数据库对象 key 和任务协议保持不变，业务模块无需改写。
- **确认**：用户于 2026-08-02 确认方案 A。

## 7. 架构方案：KnowAgent

- **日期**：2026-08-02
- **架构风格**：模块化单体 Web API + 独立 Celery Worker/Beat + 独立 Embedding/Rerank model-service + React 单页应用。
- **核心模块**：`common`、`platform`、`identity`、`systems`、`documents`、`knowledge`、`conversations`、`retrieval`、`agent`、`tickets`、`notifications`、`analytics`、`audit`、`model-service` 和 `web`。
- **关键决策**：PostgreSQL 是唯一业务事实源；Redis 只保存 Session、Broker 和临时加速状态；问答与文档任务使用独立 Celery 队列；所有检索在数据库层强制过滤 `system_id`；LangGraph 只编排领域服务；知识不足/冲突与基础设施故障使用不同终态；工单、通知和知识回流使用事务与 Outbox；历史答案保存引用文本和定位快照。
- **接口与数据**：采用版本化 `/api/v1`、Redis Session + CSRF、类型化 Provider port、可恢复 SSE run event、统一 `SourceLocator`，并为账号、系统、文档版本、知识片段、会话、证据判定、工单、知识候选、Outbox、通知、评测和审计建立明确的数据边界。
- **部署**：目标为无 Docker 的内网 Linux；Nginx 托管前端并代理 API/SSE，systemd 分别管理 API、交互 Worker、批处理 Worker、Beat 和模型服务，版本化发布目录支持应用回滚。
- **权衡**：模块化单体降低个人开发和强事务场景的分布式复杂度，但必须通过 Repository 私有化、公开 application port 和架构测试约束模块边界；独立 Worker/model-service 增加进程运维成本，换取任务恢复、队列隔离和模型资源隔离。
- **风险**：DBA 尚未确认 `vector`/`pg_trgm`；模型服务器资源和公司 LLM/通知/对象存储协议未知；无 Docker 环境存在开发生产差异。分别通过实施前扩展门禁、真实 ESB 样本压测、Provider 契约和类生产 Linux 演练缓解。
- **复用决策**：不迁移 `knowledge-rag` 的 Java/Docker 代码，只继承 SSE 富事件、引用快照、持久任务事实状态、显式降级和 Nginx 安全配置模式；迁移输入与验证边界见 `docs/development/16-retrospective.md` 和 `docs/engineering/11-project-structure.md`。
- **详细设计**：以 `docs/engineering/11-project-structure.md` 为架构、接口、数据流、部署和文件放置的事实文档。
- **确认人**：用户确认。
