# 追溯矩阵

需求阶段先建立需求到验收标准的映射；实现模块由架构阶段补充，代码文件由功能实现阶段补充。

## 矩阵

| 需求点 ID | 描述 | P 级 | AC 编号 | 实现模块 | 代码文件 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| REQ-001 | 双登录入口、统一认证、用户批量导入、管理员后台新增、首次改密、三角色 RBAC 和 SSO 适配边界 | P0 | AC-001, AC-010, AC-012 | `identity`, `audit`, `web` | `backend/src/knowagent/identity/`, `backend/src/knowagent/api/app.py`, `backend/migrations/versions/3f5d51a53981_create_phase1_identity_tables.py`, `frontend/src/api/client.ts`, `frontend/src/features/auth/`, `frontend/src/features/admin/`, `backend/tests/`, `frontend/src/**/*.test.ts(x)` | done |
| REQ-002 | 多业务系统管理、选择和知识隔离 | P0 | AC-002 | `systems`, `knowledge`, `retrieval`, `web` | `backend/src/knowagent/systems/`, `backend/migrations/versions/baaf88cba66a_create_business_systems_and_owner_roles.py`, `backend/tests/unit/test_system_service.py`, `backend/tests/integration/test_identity_api.py`, `frontend/src/api/client.ts`, `frontend/src/features/admin/SystemsPage.tsx`, `frontend/src/features/auth/UserHomePage.tsx`；`knowledge`/`retrieval` 待实现 | gap（系统管理与选择基础已完成；知识检索强隔离待实现） |
| REQ-003 | 用户端与管理后台 | P0 | AC-001, AC-009 | `web`, API 各业务模块 | `frontend/src/app/App.tsx`, `frontend/src/app/AppErrorBoundary.tsx`, `frontend/src/shared/WorkspaceShell.tsx`, `frontend/src/shared/FeedbackState.tsx`, `frontend/src/shared/uiError.ts`, `frontend/src/features/auth/UserShell.tsx`, `frontend/src/features/admin/AdminShell.tsx`, `frontend/src/features/auth/UserHomePage.tsx`, `frontend/src/features/admin/AccountsPage.tsx`, `frontend/src/features/admin/SystemsPage.tsx`, `frontend/src/**/*.test.ts(x)` | implementing（Phase 1 基础导航、状态和错误处理及评审修复已完成；问答、工单、知识和审计业务页面随对应模块实现） |
| REQ-004 | 四类文档结构化解析、精确定位和可恢复索引 | P0 | AC-003, AC-009 | `documents`, `knowledge`, `worker`, `model-service` | `backend/src/knowagent/documents/`, `backend/src/knowagent/platform/object_store.py`, `backend/src/knowagent/platform/settings.py`, `backend/src/knowagent/worker/`, `backend/migrations/versions/d1a97d2e451b_create_document_ingestion_tables.py`, `backend/.env.example`, `backend/tests/unit/test_source_locator.py`, `backend/tests/unit/test_document_parsers.py`, `backend/tests/unit/test_document_chunking.py`, `backend/tests/unit/test_document_configuration.py`, `backend/tests/unit/test_document_ingestion_service.py`, `backend/tests/unit/test_ingestion_job.py`, `backend/tests/unit/test_ingestion_processor.py`, `backend/tests/unit/test_ingestion_repository.py`, `backend/tests/unit/test_s3_object_store.py`, `backend/tests/unit/test_worker_tasks.py`, `backend/tests/integration/test_identity_api.py` | implementing（四类解析、结构化切分、精确定位、S3 兼容对象存储、持久任务、账号+系统幂等、租约 fencing、阶段进度、失败重试和重启恢复已完成；版本停在 `CHUNKED`，可检索知识索引与发布链路待实现） |
| REQ-005 | 基于证据回答、引用溯源与历史引用快照 | P0 | AC-004, AC-008 | `retrieval`, `agent`, `conversations`, `knowledge`, `web` | `backend/src/knowagent/documents/domain/models.py`, `backend/src/knowagent/documents/application/chunking.py`；回答引用与快照持久化待实现 | implementing（统一来源定位与 chunk locator 集合已完成；问答引用链待实现） |
| REQ-006 | 证据充分性判定、可靠拒答并创建内置工单 | P0 | AC-005, AC-008 | `retrieval`, `agent`, `tickets` | 待实现 | skeleton |
| REQ-007 | 工单处理、追加、关闭/重开和审核入库 | P0 | AC-006, AC-007 | `tickets`, `knowledge`, `documents`, `audit`, `web` | 待实现 | skeleton |
| REQ-008 | 多轮对话上下文 | P1 | AC-004, AC-005 | `conversations`, `agent` | 待实现 | skeleton |
| REQ-009 | 混合检索与 Rerank | P1 | AC-004, AC-008 | `retrieval`, `model-service`, `knowledge` | 待实现 | skeleton |
| REQ-010 | 公司通知 API | P1 | AC-008, AC-014 | `notifications`, `platform`, `worker` | 待实现 | skeleton |
| REQ-011 | 文档版本和生命周期 | P1 | AC-003, AC-007 | `documents`, `knowledge`, `worker` | 待实现 | skeleton |
| REQ-012 | 高频问题、知识缺口和使用分析 | P1 | AC-011 | `analytics`, `conversations`, `tickets`, `web` | 待实现 | skeleton |
| REQ-013 | 关键操作审计 | P1 | AC-006, AC-010 | `audit`, `identity`, `documents`, `tickets` | 待实现 | skeleton |
| REQ-014 | 检索参数和提示词版本 | P1 | AC-004, AC-008 | `retrieval`, `agent`, `platform` | 待实现 | skeleton |
| REQ-015 | 公司 SSO | P2 | AC-012 | `identity` SSO adapter | 待实现 | skeleton |
| REQ-016 | 细粒度系统可见性 | P2 | AC-001, AC-002 | `systems`, `identity` | 待实现 | skeleton |
| REQ-017 | 相似问题和重复工单处理 | P2 | AC-013 | `analytics`, `retrieval`, `tickets` | 待实现 | skeleton |
| REQ-018 | 离线评测和版本对比 | P2 | AC-004, AC-005, AC-008 | `analytics`, `retrieval`, `agent`, `web` | 待实现 | skeleton |

## 来源项目迁移输入映射

| 迁移输入 | 影响需求 | 架构阶段必须验证 | 当前结论 |
| --- | --- | --- | --- |
| `parser/chunker` 缺少 Excel 与结构定位 | REQ-004, REQ-005 | `SourceLocator` 能覆盖四类格式，切分不丢失定位 | 已按 TD-007 重写并完成评审修复：严格联合定位、四类格式适配、精确源行、硬 token 预算和结构感知切分测试通过 |
| `owner_id/kb_id` 与 1024 维硬编码 | REQ-002, REQ-009 | `system_id` 强过滤，向量维度由模型契约唯一配置 | 重构后迁移 |
| 进程内 `@Async` 入库 | REQ-004, REQ-011 | 任务持久化、租约、幂等、重试和重启恢复 | 已以 PostgreSQL 任务事实、Celery 仅派发、账号+系统幂等、owner/attempt 租约 fencing 和恢复状态机重写，不直接迁移 |
| SSE 阶段事件与前端流式状态机 | REQ-003, REQ-005, REQ-008 | 事件协议、取消、错误优先级和历史消息刷新 | 重构后迁移 |
| Citation snippet 持久化 | REQ-005, REQ-011 | 历史引用快照不随文档新版本漂移 | 继承设计 |
| 仅向量召回且无可靠拒答 | REQ-006, REQ-008, REQ-009 | 混合召回、证据充分性、拒答原因和工单触发 | 重做编排；TD-009 已确认 LangGraph + 自定义领域服务 |
| Docker/Compose 部署与容器监控 | REQ-003, REQ-013 | 非 Docker Linux 的进程、日志、监控、备份和回滚 | 不迁移实现；TD-008 已确认 systemd + Nginx + 版本化发布 |

## 状态说明

- `pending`：需求已记录，未开始实现
- `skeleton`：架构模块已划分，骨架已生成
- `implementing`：正在实现
- `done`：实现完成且验证通过
- `gap`：检测到遗漏，需补充
- `user_override`：用户显式跳过，风险留痕
- `failed`：实现失败，待用户介入

## 技术基线覆盖

| 技术决策 | 影响需求 | 架构阶段必须验证 | 当前状态 |
| --- | --- | --- | --- |
| TD-010 应用框架与核心版本 | REQ-001 至 REQ-018 | API/领域/ORM 边界、双端路由、服务端分页、流式协议、异步任务和版本兼容 | 架构已确认；Python 3.11/TypeScript 最小依赖与静态检查基线已建立 |

## 失败统计

| 模块名 | 失败类别 | 重试次数 | 最终处理 | 备注 |
| --- | --- | --- | --- | --- |

## 用户覆盖记录

| 需求点 ID | 覆盖原因 | 覆盖时间 | 风险说明 |
| --- | --- | --- | --- |
| REQ-001 | 用户明确将账号来源调整为“用户 SQL 批量导入、管理员后台新增”，同时保留双方登录 | 2026-08-02 | 默认密码增加泄露和横向尝试风险；通过 Argon2id 哈希、首次强制改密、入口角色校验、限流和审计降低风险 |
