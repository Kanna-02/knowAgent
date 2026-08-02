# Current Status

本文档用于跨对话、跨开发者、跨 AI 助手接续项目。每次阶段性暂停、切换对话、完成重要功能、遇到阻塞或准备交接时，都必须更新。

## 1. 快照时间

```text
更新时间：2026-08-02
更新人/助手：Codex
当前分支：master
远程仓库：git@github.com:Kanna-02/knowAgent.git
当前环境：目标 Python 3.11；本轮测试使用内置 Python 3.12.13；Node.js 24.16.0
```

## 2. 当前阶段

```text
当前阶段：Phase 1 进行中（2/6）
阶段目标：认证、系统管理、双端基础界面和四类文档可恢复入库
当前任务：REQ-002 多业务系统管理、负责人配置和前台系统选择基础切片
任务状态：基础切片已完成；知识/检索强隔离仍为 gap
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
12. REQ-001 已完成：双登录入口、统一账号认证、用户批量导入、管理员后台新增、首次改密、三角色 RBAC 和 SSO 禁用适配边界均已落地。
13. Alembic 账号/审计迁移、Redis Session/CSRF、会话撤销、登录限流、最后管理员保护和只追加审计已实现并通过自动化测试。
14. 用户/管理员登录、首次改密、用户成功页和管理员账号页已构建；管理路由已拆包。
15. 已修复认证切片评审发现的并发管理员保护、失败限流、CLI/摘要校验、请求 ID、前端认证竞态和覆盖率门禁问题。
16. REQ-002 的系统管理与选择基础切片已完成：业务系统创建、编辑、启停、负责人替换/追加语义和可见系统查询已实现，系统标识统一规范化并保持唯一；知识/检索强隔离待后续模块实现后完成 AC-002 验收。
17. `business_systems` 与 `account_system_roles` ORM/迁移已落地；负责人账号必须为有效 `SYSTEM_OWNER`，当前用户响应返回类型化系统角色映射。
18. 管理后台已新增业务系统表格、编辑/启停和负责人配置抽屉；用户问答首页要求显式选择启用中的业务系统。
19. 已修复系统切片评审问题：负责人映射变更撤销旧 Session，管理员系统列表服务端分页，负责人候选支持搜索和独立重试，普通用户不接收负责人详情，编辑表单不复用旧说明。

## 4. 正在进行

1. Phase 1 下一项为用户端与管理后台基础导航、状态和错误处理。
2. 等待 DBA 验证 `pgvector` 与 `pg_trgm` 扩展。
3. 等待目标 Linux 服务器资源信息以确定模型推理后端、量化方式和 Python 传递依赖锁。

## 5. 未完成 / 下一步

1. 使用 `feature` 完成 Phase 1 双端基础导航、状态和错误处理。
2. 在数据库功能落地前确认 PostgreSQL 扩展和版本。
3. 在类生产 Linux 环境验证 Python 3.11 完整安装、模型运行和发布回滚。
4. 在 `knowledge` 与 `retrieval` 模块落地后完成 REQ-002 的系统级强隔离和 AC-002 零跨系统泄漏验收。

## 6. 阻塞点

| 问题 | 影响 | 需要谁处理 | 当前状态 |
| --- | --- | --- | --- |
| PostgreSQL 是否允许安装 `vector`、`pg_trgm` | 影响 TD-002 实施 | DBA | 待验证 |
| 模型服务器 CPU/内存/GPU 信息未知 | 影响 Embedding/Rerank 运行时和量化 | 运维/用户 | 待提供 |
| 公司 LLM、通知、对象存储协议未知 | 影响 provider 实现 | 用户/第三方 | 待提供 |
| 本机无 Python 3.11、未连接 PostgreSQL/Redis 测试实例 | 影响目标运行时和真实基础设施验证 | 开发/DBA | 待在集成环境验证 |

## 7. 最近改动文件

| 文件 | 改动说明 | 状态 |
| --- | --- | --- |
| `docs/product/01-requirements-clarification.md` | 同步双登录、账号来源、默认密码规则并清理框架待确认旧状态 | 已完成 |
| `docs/engineering/04-tech-decisions.md` | 记录正式架构决策并将运行时调整为 Python 3.11 | 已完成 |
| `docs/product/06-roadmap.md` | Phase 1 推进为进行中（2/6） | 已完成 |
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

## 9. 未运行验证与风险

1. 尚未完成业务系统页面的桌面/移动端真实浏览器截图和交互检查；需启动 PostgreSQL、Redis、API 与前端后补充。
2. 默认密码批量导入仍有共享密码泄露风险；实现已强制摘要、首次改密、限流、会话撤销和审计，凭据分发流程仍需组织侧控制。
3. 核心、解析器和质量工具直接版本已固定；Python 传递依赖锁仍需在目标 Linux/Python 3.11 环境生成。
4. 模型运行时和目标 Linux 完整安装尚未验证；本轮前端生产构建已通过。
5. 本轮曾按 Python 3.12 跨版本 dry-run；因本机 pip 对本地项目跨版本校验受限，且 PyMuPDF wheel 下载速度约 47 KB/s，用户已终止并明确改用 Python 3.11。
6. Python 3.11 本地无依赖 metadata dry-run 因当前环境缺少 `wheel` 的 `bdist_wheel` 命令未完成；配置约束已单独验证，未为此安装全局构建工具。
7. Python 静态工具安装审批服务再次返回 503，因此当前虚拟环境仍未执行 Black/isort/mypy/Pylint/Bandit；测试、覆盖率和 Python 编译导入已通过。
8. `npm audit` 的公告接口访问审批同样返回 503；`npm ci` 报告现有锁文件有 2 个 high 漏洞，未在未评估 breaking change 的情况下执行自动升级。
9. 本轮静态工具安装和 `npm audit` 外部执行审批均再次返回 503，因此未取得 Black/isort/mypy/Pylint/Bandit 与最新 npm 公告结果。

## 10. 继续开发建议

新对话或新开发者接手时，建议下一步：

1. 先阅读 REQ-001 实现、TD-006 和本地开发文档。
2. 使用 `feature` 完成 Phase 1 用户端与管理后台基础导航、状态和错误处理。

## 11. 接手时必须先读

```text
AI_DEVELOPMENT_RULES.md
docs/00_START_HERE.md
docs/development/10-current-status.md
docs/development/03-feature-changelog.md
docs/product/06-roadmap.md
docs/engineering/04-tech-decisions.md
```
