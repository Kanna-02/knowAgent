# KnowAgent 项目文档

KnowAgent 是面向公司内部人员的多系统智能客服产品。Phase 0、Phase 1 已正式关闭；Phase 2 和 Phase 3 的功能范围均已完成，但阶段验收仍等待真实 ESB 标注评测集、真实公司通知 API、完整业务角色数据和目标 Linux 资源。账号认证、多系统知识隔离、问答/SSE/工单闭环、混合检索/Rerank、多轮配置、通知、文档生命周期、分析和审计均已实现。

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
| 产品 | `product/06-roadmap.md` | Phase 1 已关闭；Phase 2/3 功能范围完成，外部验收门禁待补 |
| 产品 | `product/15-frontend-design.md` | 已确认，双登录流程已同步 |
| 工程 | `engineering/02-development-principles.md` | 初版完成 |
| 工程 | `engineering/04-tech-decisions.md` | TD-001 至 TD-012 及核心版本基线已确认 |
| 工程 | `engineering/11-project-structure.md` | 架构已确认 |
| 运维 | `operations/09-runtime-resource-inventory.md` | 已记录系统资源基线、本机/Docker 资源、本地 Rerank 真实推理和目标 Linux 缺口 |
| 开发 | `development/03-feature-changelog.md` | 已记录 Phase 1-3 实现、评审修复与验收证据 |
| 开发 | `development/10-current-status.md` | Phase 2/3 功能范围完成；真实评测、公司通知 API 与目标 Linux 门禁待补 |
| 开发 | `development/16-retrospective.md` | `knowledge-rag` 跨项目资产盘点已完成 |
| 开发 | `development/17-traceability-matrix.md` | 需求到代码、测试和当前验收状态已同步 |
| 开发 | `development/20-phase1-integration-acceptance.md` | 通过；记录真实 PG/Redis/MinIO 与四格式完整链路证据 |
| 开发 | `development/21-phase2-integration-acceptance.md` | 功能/真实服务集成通过；真实质量与完整业务页门禁待补 |
| 开发 | `development/22-phase2-evaluation.md` | 真实 ESB/无知识问题评测输入、阈值和留存规范 |
| 开发 | `development/23-phase3-integration-acceptance.md` | 功能范围、本地 Rerank、运营页与外部门禁汇总 |

其余文档由对应 skill 在首次需要时渐进创建，不因当前缺失视为异常。

## 下一步

1. 提供至少 50 条真实标注 ESB 可回答问题和真实无知识问题集，执行 Phase 2 质量门禁及基础 RRF/Rerank 对比。
2. 提供真实公司通知 API 契约与测试端点，完成 AC-014 staging 联调。
3. 提供目标 Linux CPU/内存/GPU 信息与完整业务角色数据，完成生产推理容量和带引用回答/工单审核页面验收。
