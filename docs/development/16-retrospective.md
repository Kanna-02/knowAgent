# 回顾与跨项目资产盘点

---

## 附1：`knowledge-rag` 跨项目可复用资产盘点（2026-08-02）

**触发**：在 KnowAgent 技术选型前检查已有 `knowledge-rag` 项目，避免重复建设，同时防止把项目内耦合和未完成骨架带入新项目。
**复盘类型**：跨项目可复用资产盘点
**来源基线**：`/Users/qijishuma/Documents/AI_Agent/knowledge-rag`，commit `3ba82284a06941dd66500168f01d11da744a62ef`。
**检查方式**：本次环境没有技能要求的交互式多选工具，因此未代替用户评价主观得失；结论仅基于需求约束、源码、配置和测试证据。

### 1. 项目定位结论

`knowledge-rag` 和 KnowAgent 都是产品应用，不是通用 RAG 基础设施服务。前者围绕个人知识库和 `owner_id/kb_id` 建模，后者围绕公司内部业务系统、负责人、工单和知识审核闭环建模。两者领域边界不同，不能把前者整体复制后再改名。

迁移策略是：继承被真实代码验证的通用模式；对 RAG 核心模块只保留接口思想并按 KnowAgent 领域重构；Docker、GraphRAG 和个人知识库隔离模型不迁移。

### 2. 做得好的（可继承到 KnowAgent）

#### A. 业务代码模块：已识别 10 项

| 模块 | 复用价值 | 复用方式 | 结论 |
| --- | --- | --- | --- |
| parser | 中 | 仅参考 Tika 接入和格式校验 | 不支持目标 Excel/精确定位，不直接复制 |
| chunker | 中 | 参考接口和 overlap 参数 | 实际是字符级段落/句子切分，先重做结构化定位模型 |
| embedding | 中 | 继承 provider 接口思想 | 去除 Ollama、bge-m3、1024 维和阻塞重试耦合 |
| rerank | 中 | 继承可降级 provider 思想 | 候选类型改为领域无关 DTO，不依赖 `ChunkVector`/TEI |
| vectorstore | 中 | 参考 pgvector 持久化 | 改为 `system_id` 强过滤和模型维度单一配置源 |
| retrieval | 中 | 参考召回、扩展、重排编排顺序 | 增加关键词召回、证据充分性和可靠拒答；移除强制 GraphRAG |
| llm/prompt | 高 | 迁移 token 预算和上下文输入隔离模式 | 提示词需版本化，输入模型与持久化实体解耦 |
| ingest | 高 | 迁移 SHA-256 幂等、阶段状态和进度模式 | 内存 `@Async` 改为持久化可恢复任务，对象存储替代本地路径 |
| conversation | 中 | 迁移 SSE 事件语义 | 拆分 342 行 orchestrator，并增加“拒答 -> 工单”决策 |
| citation | 高 | 迁移 snippet 快照持久化 | 扩展统一 `SourceLocator`，保证历史引用不漂移 |

#### B. 可继承设计模式：已识别 8 项

1. 模块化单体和 ingest / retrieval / conversation 领域边界。
2. `retrieval_start -> retrieval_done -> token* -> done|error` 的阶段事件协议。
3. 已收到后端错误事件时，不用随后发生的网络断开覆盖真实错误。
4. Prompt token 预算、上下文标签隔离和超预算裁剪。
5. SHA-256 文档幂等、异步进度和可诊断失败状态。
6. Rerank 等可选依赖失败时显式降级并记录原因。
7. 引用证据片段随答案持久化，避免历史引用受文档更新影响。
8. 统一错误码、API 响应和分页响应的契约思想。

#### C. 前端组件与 API：已识别 5 项

| 资产 | 结论 |
| --- | --- |
| `api/client.ts` | 重构后迁移：保留统一解包、401 清理和事件派发；按 TD-006 改用 HttpOnly Cookie 承载 Redis Session，不复用 JWT 存储 |
| `api/sse.ts` | 高价值重构起点：保留 POST + ReadableStream 和真实错误优先；需补 CRLF、多行 data、401、非 JSON、流结束无 done 等协议测试 |
| `hooks/useChat.ts` | 重构后迁移：保留 AbortController、ref 防陈旧闭包和状态机；事件类型与目标工单流程重新定义 |
| ConfirmDialog / FormDialog / EmptyState / ErrorCard / Skeleton | 仅借鉴交互和 props 设计；样式依赖源项目 token，不直接复制 |
| ThreeColumnLayout / Sidebar | 低价值不沉淀：布局绑定个人知识库信息架构，与当前管理后台和系统选择流程不同 |

#### D. 后端基础设施：已识别 6 项

| 资产 | 结论 |
| --- | --- |
| SecurityConfig 的 stateless、方法级 RBAC、SSE ASYNC dispatch | 仅借鉴方法级 RBAC 和流式请求边界；TD-006 已确认 Redis Session，不迁移 stateless JWT 方案 |
| JwtAuthFilter + ThreadLocal 清理 | 借鉴 finally 清理；角色写入长期 JWT 会产生权限变更延迟，不直接复制 |
| Bootstrap 管理员 | 借鉴首次管理员启动问题的解决思路；强化密码策略、一次性禁用和日志脱敏 |
| BusinessException / ErrorCode / ApiResponse / PageResponse | 可作为契约设计参考；错误到 HTTP 状态的映射需补齐 |
| AuditLog 注解/切面 | 不迁移：切面只有 TODO，无可复用实现 |
| HashUtil | 可按语言和技术栈直接重写；属于标准库级能力，无需复制项目代码 |

#### E. 部署运维脚本：已识别 5 项，当前不迁移实现

`build.sh`、`backup.sh`、`restore.sh`、`init-letsencrypt.sh` 都以 Docker/volume/container 为核心，与公司禁用 Docker 的约束冲突。只继承备份清单、完整性校验、密钥强度检查、恢复演练和证书频率保护思路。`generate-secrets.sh` 可在 deploy 阶段改写为非容器 Linux 工具，但不能原样带入。

#### F. Docker/容器化模板：已识别 4 项，不迁移

后端/前端 Dockerfile、Compose 和容器网络隔离均不进入 KnowAgent。Nginx 中 SSE 的 `proxy_buffering off`、长连接超时、安全头和限流分区仅作为非容器 Nginx 配置参考。

#### G. 监控可观测性：已识别 3 项，仅借鉴设计

保留应用、主机、PostgreSQL 三类指标和 Grafana provisioning 思想；容器指标 cAdvisor 和 monitoring compose 不迁移。KnowAgent 需增加 Redis、对象存储、持久化任务队列、Embedding/Rerank 和通知 API 的延迟、错误、降级指标。

#### H. 跨项目规则：已识别 9 项，已裁剪复用 7 项

当前 `AI_DEVELOPMENT_RULES.md` 已复用产品定位、资产盘点、会话失效、RAG 降级、提示词版本、真实集成测试和参数配置化。Hibernate 脱敏与已确认的 Python/SQLAlchemy 技术栈不适配，GraphRAG 规则因当前不采用图谱而不启用。

#### I. 配置模式：已识别 4 项

可继承 `rag.*` 参数集中、环境变量覆盖、数据库批处理和环境模板说明模式。不能继承生产可用默认密码、固定 bge-m3/1024 维、默认启用 GraphRAG，以及配置与代码中重复维护模型约束的做法。

### 3. 做得不好的（复用角度的失败设计）

1. 资产 README 与源码不一致：parser README 声称支持 Excel，实际扩展名白名单不含 Excel；chunker README 声称标题语义切分，实际 `sourceRef` 仍为空。
2. 个人知识库语义泄漏到通用层：`owner_id`、`kb_id`、`ChunkVector` 进入检索、Rerank、向量存储和 Prompt 接口。
3. 模型和存储强耦合：bge-m3、Ollama、TEI、1024 维同时出现在配置、实体和 SQL，切换模型会跨层修改。
4. 只有向量召回，没有关键词混合召回、证据充分性或可靠拒答，无法支撑自动建工单。
5. 入库依赖本地文件路径和进程内异步任务，进程重启会丢失执行状态，不适合公司环境。
6. `ChatOrchestratorImpl` 过度集中检索、生成、SSE、引用和持久化职责，难以单独测试拒答与工单路径。
7. 后端基础设施含未完成骨架：`AuditLogAspect` 为空，`GlobalExceptionHandler` 留有 TODO，Bootstrap 注释声称 SHA-256 但实现使用 `String.hashCode()`。
8. 多个关键集成测试被 Surefire 排除或 `@Disabled`，不能用测试文件数量证明迁移成熟度。
9. Docker 部署、容器备份和 cAdvisor 监控对当前目标环境属于不适配设计，而不是可复用优势。

### 4. 关键判断：KnowAgent 是否需要 RAG？

需要。目标答案依赖模型训练数据之外、公司私有、持续变化且按业务系统隔离的接入文档，RAG 是核心能力。但需要的是“可靠检索、可验证引用、可解释拒答和人工回流”，不是 GraphRAG 或复杂 Agent 工具链。首版应优先做结构化解析、混合召回、证据充分性和工单闭环。

### 5. 如果重新开始这个阶段

**架构选择**：保留模块化单体，模型推理作为可替换 provider，耗时入库使用持久化任务；不把 RAG 核心先抽成独立服务。
**理由**：当前只有一个产品和有限用户量，服务化会增加无 Docker Linux 下的部署、监控和故障面；清晰接口已经足以支持后续替换。

**演进路径**：

1. 先定义 `system_id` 隔离、`SourceLocator`、引用快照、provider 契约和任务状态机。
2. 用 ESB 样本文档和真实问题验证 parser、chunker、混合检索、拒答和工单闭环。
3. 只有当多个产品稳定复用同一检索能力且出现独立扩缩容需求时，再抽取内部 RAG 服务。

### 6. 可复用规则

候选规则 1：**资产说明必须以可执行证据校验**。迁移前同时核对 README、当前源码和启用的测试；README 声明或被禁用的测试不能作为成熟度证明。
候选规则 2：**引用定位模型先于 parser/chunker**。需要可溯源回答时，先定义跨格式 `SourceLocator` 和历史引用快照，再选择解析器与切分器。

这两条与当前 §16.2、§16.6 部分相关但不完全重复。本次未追加到 `AI_DEVELOPMENT_RULES.md`，等待用户在后续规则门禁中决定，避免未经确认扩大跨项目规则。

### 7. 下一阶段行动项

1. `tech` 已完成 TD-001 至 TD-010 的 2-3 方案比较和核心版本基线确认。
2. 在 `architect` 中先定义 `SourceLocator`、provider DTO、`system_id` 过滤、任务状态机和“证据不足 -> 拒答 -> 工单”决策边界。
3. 建立四类真实文档样本和至少 50 个 ESB 问题的评测集，再做模型与切分参数选择。
4. 不迁移 GraphRAG、Docker/Compose、容器监控和源项目 orchestrator。
5. 技术栈确认后，只对选中的模块做逐文件迁移评审和测试补齐；不整包复制现有 `retro` 资产。

### 8. 关键证据

- parser 白名单与解析策略：`knowledge-rag/backend/src/main/java/com/rag/parser/service/TikaDocumentParser.java`
- chunk 定位模型：`knowledge-rag/backend/src/main/java/com/rag/chunker/dto/Chunk.java`
- 前端 API/SSE：`knowledge-rag/frontend/src/api/client.ts`、`api/sse.ts`、`hooks/useChat.ts`
- 安全与基础设施：`knowledge-rag/backend/src/main/java/com/rag/common/`
- 测试排除：`knowledge-rag/backend/pom.xml` 和 `backend/src/test/`
- 配置与部署：`knowledge-rag/backend/src/main/resources/application.yml`、`knowledge-rag/deploy/`
- 已沉淀资产说明：`ai-code-skills/skills/retro/assets/reusable-code/knowledge-rag/README.md`

### Skill 反馈扫描

- `init`：当前文档已经覆盖多系统、禁用 Docker、持久化基础设施和模型自建约束；本次通过迁移复盘补强精确引用和任务恢复，未发现必须修改 skill 源文件的问题。
- `tech`：TD 清单已补齐来源代码验证门禁、provider 契约和证据充分性选型，未发现 skill 流程缺口。
- `architect`：需在下一阶段按项目文档定义 `SourceLocator` 与拒答/工单边界，属于待执行事项，不是 skill 缺陷。
- `scaffold`：当前尚未进入代码骨架阶段，无证据表明 skill 需要修改。
- `retro`：交互式提问工具本轮不可用，已留痕并限制结论为代码证据；无需修改 skill 源文件。

### 资产处理记录

本次没有向 `retro/assets` 复制或更新代码。原因是当前技术栈尚未确认，且已有 `knowledge-rag` 资产与当前源码能力存在描述偏差；在用户选择具体模块并完成迁移门禁前，继续复制会放大错误复用风险。来源项目工作区保持只读，其已有未提交改动未被触碰。
