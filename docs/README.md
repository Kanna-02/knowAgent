# KnowAgent 项目文档

KnowAgent 是面向公司内部人员的多系统智能客服产品。Phase 0 已完成；Phase 1 功能范围已完成（6/6），并于 2026-08-04 通过 PostgreSQL、Redis、MinIO 和四格式完整持久化集成验收后正式关闭。账号认证、多业务系统管理、双端基础界面、四类文档处理、可恢复入库、文档版本、发布状态和知识强隔离基础模型已实现。

## 开始阅读

1. 根目录 `AI_DEVELOPMENT_RULES.md`：长期开发规则。
2. `00_START_HERE.md`：项目工作流和确认门禁。
3. `product/01-requirements-clarification.md`：产品边界、角色、流程和验收标准。
4. `product/06-roadmap.md`：阶段计划。
5. `engineering/04-tech-decisions.md`：已确认约束、来源项目迁移边界和待选技术。
6. `engineering/11-project-structure.md`：已确认的完整系统架构和目标目录结构。
7. `development/16-retrospective.md`：`knowledge-rag` 九维度复用与迁移评估。

## 当前文档

| 分类 | 文档 | 状态 |
| --- | --- | --- |
| 产品 | `product/01-requirements-clarification.md` | 已确认，认证范围已同步 |
| 产品 | `product/06-roadmap.md` | Phase 1 已完成集成验收并关闭，Phase 2 核心服务集成验收通过，Agent/Tickets API 装配完成，SSE/Worker/页面端到端待补 |
| 产品 | `product/15-frontend-design.md` | 已确认，双登录流程已同步 |
| 工程 | `engineering/02-development-principles.md` | 初版完成 |
| 工程 | `engineering/04-tech-decisions.md` | TD-001 至 TD-011 及核心版本基线已确认 |
| 工程 | `engineering/11-project-structure.md` | 架构已确认 |
| 开发 | `development/03-feature-changelog.md` | 已记录 Phase 1 全部实现、评审修复与集成验收 |
| 开发 | `development/10-current-status.md` | Phase 1 已完成真实基础设施验收，Phase 2 核心服务集成验收通过，API 装配完成，SSE/Worker/页面端到端待补 |
| 开发 | `development/16-retrospective.md` | `knowledge-rag` 跨项目资产盘点已完成 |
| 开发 | `development/17-traceability-matrix.md` | REQ-004 的解析、对象存储和可恢复持久任务已实现；知识索引/发布待完成 |
| 开发 | `development/20-phase1-integration-acceptance.md` | 通过；记录真实 PG/Redis/MinIO 与四格式完整链路证据 |

其余文档由对应 skill 在首次需要时渐进创建，不因当前缺失视为异常。

## 下一步

1. 接入问答 SSE 流式与会话持久化、文档索引 Worker 接线，准备 Phase 2 端到端验收。Agent/Tickets API 集成测试已在真实 PostgreSQL 17 跑通。
2. 配置完整 Qwen Key，在现有 PostgreSQL/pgvector 与 Ollama Embedding 环境完成组合联调。
3. 模型运行时和 Python 传递依赖锁等待目标 Linux/硬件信息后确认。
