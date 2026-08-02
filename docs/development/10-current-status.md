# Current Status

本文档用于跨对话、跨开发者、跨 AI 助手接续项目。每次阶段性暂停、切换对话、完成重要功能、遇到阻塞或准备交接时，都必须更新。

## 1. 快照时间

```text
更新时间：2026-08-02
更新人/助手：Codex
当前分支：master
远程仓库：git@github.com:Kanna-02/knowAgent.git
当前环境：Python 3.11.11、Node.js 24.16.0；工程基线阶段
```

## 2. 当前阶段

```text
当前阶段：Phase 0 已完成，Phase 1 待启动
阶段目标：启动认证、系统管理和文档入库的首个纵向功能
当前任务：架构确认与 Python 3.11 工程基线同步
任务状态：已完成
```

## 3. 已完成

1. 初始化需求、路线图、前端设计、开发规则和追溯矩阵。
2. 完成 `knowledge-rag` 跨项目资产盘点。
3. 已确认 TD-001 至 TD-010，包括全 Python、PostgreSQL 混合检索、独立模型服务、Celery、双入口 Redis Session、格式专用解析、原生 Linux 部署、LangGraph 编排和应用框架版本基线。
4. 已同步双端登录、统一账号体系、用户批量导入、管理员后台新增和首次强制改密，并完成跨文档一致性检查。
5. 已确认四类文档解析器边界、统一 `SourceLocator`、结构化切分约束和扫描 PDF 显式失败策略。
6. 已确认 systemd + Nginx + 版本化发布目录，以及向后兼容数据库迁移和应用回滚边界。
7. 已确认 LangGraph 只负责编排、PostgreSQL 保持事实源，并区分知识缺口拒答与系统故障。
8. 已确认 FastAPI + SQLAlchemy + React/Ant Design 技术包，并按用户决定将后端运行时调整为 Python 3.11。
9. 模块化单体、Celery Worker、独立 model-service、类型化 API/Provider、数据模型、核心数据流、systemd/Nginx 拓扑和降级策略已通过架构确认。
10. 已补齐后端、模型服务和前端的依赖管理、类型检查、Lint、格式化和测试覆盖配置；npm 锁文件已生成。
11. 18 项需求已填充实现模块并从 `pending` 推进为 `skeleton`。

## 4. 正在进行

1. 等待启动 Phase 1 的首个 feature，建议从认证和业务系统基础能力开始。
2. 等待 DBA 验证 `pgvector` 与 `pg_trgm` 扩展。
3. 等待目标 Linux 服务器资源信息以确定模型推理后端、量化方式和 Python 传递依赖锁。

## 5. 未完成 / 下一步

1. 使用 `feature` 或 `goal` 启动 Phase 1 认证与系统管理纵向切片。
2. 在数据库功能落地前确认 PostgreSQL 扩展和版本。
3. 在类生产 Linux 环境验证 Python 3.11 完整安装、模型运行和发布回滚。

## 6. 阻塞点

| 问题 | 影响 | 需要谁处理 | 当前状态 |
| --- | --- | --- | --- |
| PostgreSQL 是否允许安装 `vector`、`pg_trgm` | 影响 TD-002 实施 | DBA | 待验证 |
| 模型服务器 CPU/内存/GPU 信息未知 | 影响 Embedding/Rerank 运行时和量化 | 运维/用户 | 待提供 |
| 公司 LLM、通知、对象存储协议未知 | 影响 provider 实现 | 用户/第三方 | 待提供 |

## 7. 最近改动文件

| 文件 | 改动说明 | 状态 |
| --- | --- | --- |
| `docs/product/01-requirements-clarification.md` | 同步双登录、账号来源、默认密码规则并清理框架待确认旧状态 | 已完成 |
| `docs/engineering/04-tech-decisions.md` | 记录正式架构决策并将运行时调整为 Python 3.11 | 已完成 |
| `docs/product/06-roadmap.md` | Phase 0 标记完成，Phase 1 待启动 | 已完成 |
| `docs/product/15-frontend-design.md` | 增加双登录流程和 TD-010 前端组件策略 | 已完成 |
| `docs/development/17-traceability-matrix.md` | 18 项需求映射实现模块并推进到 `skeleton` | 已完成 |
| `AI_DEVELOPMENT_RULES.md` | 更新本项目账号与会话规则 | 已完成 |
| `docs/README.md` | 修正需求和技术选型状态及下一步门禁 | 已完成 |
| `docs/development/16-retrospective.md` | 将来源项目认证迁移结论同步到 TD-006 | 已完成 |
| `docs/development/03-feature-changelog.md` | 记录架构确认和 Python 3.11 调整 | 已完成 |
| `docs/engineering/11-project-structure.md` | 完整架构方案通过确认 | 已完成 |
| `backend/pyproject.toml` | Python 3.11 后端依赖和质量工具配置 | 已完成 |
| `model-service/pyproject.toml` | Python 3.11 模型服务边界和质量工具配置 | 已完成；模型运行时待硬件门禁 |
| `frontend/package.json` 等 | TypeScript/Vite/ESLint/Vitest 配置和 npm 锁文件 | 已完成 |

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

## 9. 未运行验证与风险

1. 尚无业务代码和 `index.html`，未运行单元测试、前端构建或页面测试；本次无页面手测步骤。
2. 默认密码批量导入存在共享密码泄露风险，必须落实首次改密、限流和审计。
3. 核心、解析器和质量工具直接版本已固定；Python 传递依赖锁仍需在目标 Linux/Python 3.11 环境生成。
4. 模型运行时、目标 Linux 完整安装、前端实际应用构建均尚未验证。
5. 本轮曾按 Python 3.12 跨版本 dry-run；因本机 pip 对本地项目跨版本校验受限，且 PyMuPDF wheel 下载速度约 47 KB/s，用户已终止并明确改用 Python 3.11。
6. Python 3.11 本地无依赖 metadata dry-run 因当前环境缺少 `wheel` 的 `bdist_wheel` 命令未完成；配置约束已单独验证，未为此安装全局构建工具。

## 10. 继续开发建议

新对话或新开发者接手时，建议下一步：

1. 先阅读已确认 TD、REQ-001 认证边界和正式架构。
2. 使用 `feature` 实现 Phase 1 的认证与业务系统基础，或使用 `goal` 按路线图自主推进。

## 11. 接手时必须先读

```text
AI_DEVELOPMENT_RULES.md
docs/00_START_HERE.md
docs/development/10-current-status.md
docs/development/03-feature-changelog.md
docs/product/06-roadmap.md
docs/engineering/04-tech-decisions.md
```
