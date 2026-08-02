# KnowAgent 项目文档

KnowAgent 是面向公司内部人员的多系统智能客服产品。Phase 0 已完成；Phase 1 正在进行（2/6），账号认证、多业务系统管理、负责人配置和前台系统选择已实现。

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
| 产品 | `product/06-roadmap.md` | Phase 1 进行中（2/6） |
| 产品 | `product/15-frontend-design.md` | 已确认，双登录流程已同步 |
| 工程 | `engineering/02-development-principles.md` | 初版完成 |
| 工程 | `engineering/04-tech-decisions.md` | TD-001 至 TD-010 及核心版本基线已确认 |
| 工程 | `engineering/11-project-structure.md` | 架构已确认 |
| 开发 | `development/03-feature-changelog.md` | 已记录技术决策及 REQ-001/REQ-002 实现 |
| 开发 | `development/10-current-status.md` | Phase 1 进行中（2/6） |
| 开发 | `development/16-retrospective.md` | `knowledge-rag` 跨项目资产盘点已完成 |
| 开发 | `development/17-traceability-matrix.md` | REQ-001 已完成；REQ-002 基础切片完成、知识隔离仍有 gap |

其余文档由对应 skill 在首次需要时渐进创建，不因当前缺失视为异常。

## 下一步

1. 使用 `feature` 继续 Phase 1 用户端与管理后台基础导航、状态和错误处理。
2. 在数据库实现前由 DBA 验证 `vector` 和 `pg_trgm` 扩展。
3. 模型运行时和 Python 传递依赖锁等待目标 Linux/硬件信息后确认。
