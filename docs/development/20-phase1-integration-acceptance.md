# Phase 1 集成验收报告

## 1. 结论

验收结论：**有条件通过，Phase 1 暂不正式关闭**。

2026-08-03 已在本机 Python 3.11.11、PostgreSQL 16.14 和 Redis 7 上完成真实基础设施预验收。双系统授权、上传幂等、Markdown 持久入库、v2 发布切换、跨系统知识零泄漏、Redis Session 和任务租约恢复均通过。后端全量 129 项测试通过，总覆盖率 91.54%，四类运行时生成样本均通过解析、定位和异常回归。

本机没有可用的 S3 兼容服务或测试 Bucket，因此真实 S3 `put/get/delete`、四格式经 S3→PostgreSQL→Worker 的完整持久化链路和真实后端页面手测被跳过。Phase 1 路线图明确要求真实 PostgreSQL/Redis/S3 与四类文档全链路，故不能标记为全部通过。

## 2. 概要

- 验收时间：2026-08-03
- 验收范围：Phase 1 多系统知识基础
- 环境：macOS、Python 3.11.11、PostgreSQL 16.14、Redis 7、Node.js 24.16.0
- 隔离资源：PostgreSQL 数据库 `knowagent_it_20260803`、Redis DB 14 + `knowagent:it:20260803:<run_id>` 前缀
- 总验证项：14
- 通过：11
- 失败：0
- 跳过：3

## 3. 集成点

| 集成点 | 涉及模块 | 接口类型 | 优先级 |
| --- | --- | --- | --- |
| 登录、Session、CSRF、RBAC | `identity`、Redis、API | API/数据 | 高 |
| 系统管理与负责人授权 | `systems`、`identity`、PostgreSQL | API/数据 | 高 |
| 文档上传、幂等与 v2 | `documents`、PostgreSQL、对象存储端口 | API/数据 | 高 |
| 解析、切分与任务状态机 | `documents`、`worker`、PostgreSQL | 内部调用/数据 | 高 |
| 任务恢复与派发 | `worker`、PostgreSQL、Redis/Celery | 事件/数据 | 高 |
| 发布切换与知识隔离 | `knowledge`、`documents`、PostgreSQL | 内部调用/数据 | 高 |
| 四格式对象存储全链路 | S3、`documents`、`worker`、PostgreSQL | 外部/数据 | 高 |
| 双端页面连接真实后端 | `web`、API、PostgreSQL、Redis | UI/API | 中 |

## 4. 验证结果

| 验证项 | 方法 | 状态 | 实际结果 |
| --- | --- | --- | --- |
| Python 3.11 后端全量回归 | `pytest tests -v` | 通过 | 129/129，通过率 100%，总覆盖率 91.54% |
| PDF/DOCX/Markdown/XLSX 解析 | 运行时生成真实格式样本 | 通过 | 四格式解析、定位、损坏/加密/资源边界和幂等回归通过 |
| PostgreSQL 迁移 | 隔离数据库 `upgrade head` | 通过 | 4 个 Phase 1 迁移在 PostgreSQL 16.14 成功执行 |
| ORM/Schema 一致性 | `alembic check` | 通过 | `No new upgrade operations detected` |
| Redis Session | 真实 Redis 登录/API 调用 | 通过 | `PING=PONG`，生成 6 个隔离 Session/账号索引 key |
| 双系统与越权拒绝 | 真实 PG/Redis API 链路 | 通过 | 创建 A/B；负责人向未授权 B 上传返回 `403 SYSTEM_ACCESS_DENIED` |
| 上传幂等与 v2 | 真实 PostgreSQL API 链路 | 通过 | 同幂等键重放同一 job/version；后续上传生成 `version_no=2` |
| Markdown 持久入库 | 真实 PostgreSQL + 内存对象端口 | 通过 | Worker 处理至 `SUCCEEDED/CHUNKED`，manifest 和 locator 生成成功 |
| v1→v2 发布切换 | 真实 PostgreSQL 发布事务 | 通过 | v2 成为当前发布版本，v1 原子退役 |
| 跨系统知识零泄漏 | 真实 PostgreSQL 强过滤仓储 | 通过 | B 系统发布 chunk 为 0，跨系统 document/version 查询均为空 |
| 任务重启恢复与 broker 派发 | 真实 PostgreSQL 租约 + Redis/Celery | 通过 | 过期 RUNNING 任务恢复并派发 1 次，Redis `ingestion` 队列收到消息 |
| S3 真实契约 | S3 `put/get/delete` | 跳过 | 本机无 S3 兼容服务或测试 Bucket；仅 S3 适配器单测通过 |
| 四格式 S3→PG→Worker 全链路 | 外部/数据/Worker | 跳过 | 缺少 S3；四格式解析本身已通过，真实持久化组合尚未证明 |
| 页面连接真实后端 | 浏览器手测 | 跳过 | 本轮未重装前端依赖；沿用既有浏览器响应式和隔离 API 验证证据 |

## 5. 核心链路结果

1. 管理员登录后创建两个启用系统，并将负责人仅分配给系统 A。
2. 负责人可选择启用系统，但向未授权系统 B 上传文档被服务端拒绝。
3. 系统 A 首次上传与相同幂等请求重放返回同一任务和版本。
4. 首版经解析、切分后生成 manifest；指定原文档再次上传生成 v2。
5. v1 发布后再发布 v2，当前指针切换到 v2，v1/source/chunk 同步退役。
6. 系统 B 的发布查询和按 ID 查询均返回空结果。
7. 模拟 Worker 在持有租约时退出；租约过期后恢复扫描重新入队并写回 task ID。

## 6. 遗留风险与阻塞程度

| 风险 | 影响 | 阻塞程度 | 处理方向 |
| --- | --- | --- | --- |
| 未验证真实 S3 签名、TLS、Bucket 权限、multipart 与错误映射 | 对象存储契约可能与实现假设不一致 | 阻塞 Phase 1 正式关闭 | 提供隔离 S3 端点/Bucket 后补跑 |
| 未完成四格式 S3→PG→Worker 组合链路 | 无法证明四格式在真实对象存储下均可恢复入库 | 阻塞 Phase 1 正式关闭 | 使用 4 个样本走相同上传、处理、恢复步骤 |
| 前端未连接本轮真实 PG/Redis 后端手测 | 页面与真实会话/数据契约仍缺最终人工证据 | 不阻塞后端预验收 | S3 环境补齐时一并执行页面步骤 |
| 复用环境的 FastAPI/Redis/pytest 小版本低于锁定版本 | 本轮结果不等同完整锁文件安装证明 | 不阻塞预验收 | 目标 Linux 按锁定依赖安装后再跑发布门禁 |

## 7. S3 环境补齐后的复验计划

1. 配置独立 endpoint、Bucket、凭据、CA 和 Redis namespace。
2. 分别上传文本 PDF、DOCX、Markdown、XLSX，确认对象 key、任务状态和 locator。
3. 在解析中途终止 Worker，等待租约过期并由恢复任务重新派发。
4. 对同一文档上传 v2，完成 v1→v2 发布切换并验证旧版本不可见。
5. 用系统 B 的账号和查询条件重复所有读取，预期返回 403 或空结果。
6. 执行 S3 权限拒绝、超时和临时 5xx，确认稳定错误码、重试与对象补偿。

## 8. 页面手动测试步骤

当前因缺少完整 S3 后端未执行。复验时：

1. 打开用户端和管理端登录页，使用隔离管理员/系统负责人账号。
2. 管理员创建系统 A/B，仅为负责人分配系统 A。
3. 负责人在系统 A 上传四种格式并观察任务状态；相同幂等请求不得产生新版本。
4. 指定原文档上传 v2 并发布，页面应显示 v2 为当前版本、v1 已退役。
5. 尝试在系统 B 管理/上传系统 A 文档，页面应显示无权限且不得出现 A 的知识内容。
6. 停止并恢复 Worker 后刷新任务页，任务应继续推进且不产生重复版本。
