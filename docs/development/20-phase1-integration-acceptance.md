# Phase 1 集成验收报告

## 1. 结论

验收结论：**通过，Phase 1 正式关闭**。

2026-08-04 已在本机 Python 3.11.11、PostgreSQL 17.10、Redis 8.10.0 和 MinIO 上完成 Phase 1 真实基础设施验收。真实 S3 兼容对象存储契约、PDF/DOCX/Markdown/XLSX 四格式完整持久化链路、双系统授权、上传幂等、v2 发布切换、跨系统知识零泄漏、Redis Session 和任务租约恢复均通过。

标准后端套件 248 项通过，live 验收用例在标准套件中按安全门禁跳过，总覆盖率 90.72%；显式执行 `./scripts/run-phase1-integration.sh` 后 live 用例通过。Phase 1 路线图要求的两个系统、四类文档、真实 PostgreSQL/Redis/S3 和任务恢复链路均已有可重复证据。

## 2. 概要

- 验收时间：2026-08-04
- 验收范围：Phase 1 多系统知识基础
- 环境：macOS、Python 3.11.11、PostgreSQL 17.10、Redis 8.10.0、MinIO `RELEASE.2025-10-15T17-29-55Z`、Node.js 24.16.0
- 固定隔离资源：PostgreSQL 数据库 `knowagent_integration`、Redis DB 15 + 每次运行唯一前缀、MinIO Bucket `knowagent-phase1-it`
- 总验证项：14
- 通过：13
- 失败：0
- 跳过：1（真实后端页面手测，非 Phase 1 关闭阻塞项）

## 3. 集成点

| 集成点 | 涉及模块 | 接口类型 | 优先级 |
| --- | --- | --- | --- |
| 登录、Session、CSRF、RBAC | `identity`、Redis、API | API/数据 | 高 |
| 系统管理与负责人授权 | `systems`、`identity`、PostgreSQL | API/数据 | 高 |
| 文档上传、幂等与 v2 | `documents`、PostgreSQL、S3 | API/数据 | 高 |
| 解析、切分与任务状态机 | `documents`、`worker`、PostgreSQL、S3 | 内部调用/数据 | 高 |
| 任务恢复与派发 | `worker`、PostgreSQL、Redis/Celery | 事件/数据 | 高 |
| 发布切换与知识隔离 | `knowledge`、`documents`、PostgreSQL | 内部调用/数据 | 高 |
| 四格式对象存储全链路 | MinIO S3、`documents`、`worker`、PostgreSQL | 外部/数据 | 高 |
| 双端页面连接真实后端 | `web`、API、PostgreSQL、Redis | UI/API | 中 |

## 4. 验证结果

| 验证项 | 方法 | 状态 | 实际结果 |
| --- | --- | --- | --- |
| Python 3.11 后端全量回归 | `pytest tests -q` | 通过 | 248 项通过，live 用例按门禁跳过，总覆盖率 90.72% |
| PDF/DOCX/Markdown/XLSX 解析 | live 用例运行时生成四种真实格式 | 通过 | 四格式均经 S3 上传、Worker 解析/切分、manifest 回读和 locator 精确校验 |
| PostgreSQL 迁移 | 固定 `knowagent_integration` 执行 `upgrade head` | 通过 | 首次升级至 `c1738febb896`，复跑无新增迁移 |
| ORM/Schema 一致性 | `alembic check` | 通过 | `No new upgrade operations detected` |
| Redis Session | 真实 Redis 登录/API 调用 | 通过 | 生成 4 个本次运行隔离 Session/账号索引 key，结束后恢复运行前 key 集合 |
| 双系统与越权拒绝 | 真实 PG/Redis/API 链路 | 通过 | 创建 A/B，仅授权负责人访问 A；向 B 上传返回 `403 SYSTEM_ACCESS_DENIED` |
| 上传幂等与 v2 | 真实 PostgreSQL/S3/API 链路 | 通过 | 同幂等键返回相同任务；指定原文档上传生成 `version_no=2` |
| v1→v2 发布切换 | 真实 PostgreSQL 发布事务 | 通过 | v2 成为当前发布版本，v1/source/chunk 原子退役 |
| 跨系统知识零泄漏 | 两系统发布不同同主题知识 | 通过 | A 只返回 `SYSTEM-A-V2-ONLY`，B 只返回 `SYSTEM-B-ONLY`，交叉泄漏为 0 |
| 任务重启恢复与 broker 派发 | 租约过期 + 真实 Redis/Celery broker | 通过 | 1 个过期 RUNNING 任务恢复为 QUEUED 并重新派发，未重复恢复历史任务 |
| S3 真实契约 | MinIO `put/get/delete` | 通过 | 签名访问、回读、删除、缺失对象错误映射均通过 |
| S3 multipart 与异常 | 超过 multipart 阈值、错误凭据、不可达端点 | 通过 | multipart ETag、权限拒绝非重试错误、端点不可达可重试错误均符合契约 |
| 四格式 S3→PG→Worker 全链路 | 显式 live pytest | 通过 | `.pdf`、`.docx`、`.md`、`.xlsx` 全部完成持久化组合链路 |
| 页面连接真实后端 | 浏览器手测 | 跳过 | 沿用既有响应式页面与 API 契约证据；当前文档链路以真实 API 验收，非关闭阻塞项 |

## 5. 核心链路结果

1. 管理员创建系统 A/B，并将系统负责人只分配给系统 A。
2. 负责人在系统 A 上传四种格式，相同 Markdown 幂等请求不产生新版本；向系统 B 上传被服务端拒绝。
3. 四种对象均由真实 MinIO 回读，经 Worker 处理为 `SUCCEEDED/CHUNKED`，并验证各格式 locator。
4. Markdown v1 发布后上传并发布 v2，当前指针切换到 v2，v1 自动退役。
5. 系统 A/B 发布同主题但不同标记的知识，查询结果严格按 `system_id + PUBLISHED` 隔离。
6. 模拟 Worker 持有租约后退出；租约过期后恢复扫描只重新派发目标任务 1 次。
7. 验收复跑复用固定数据库和 Bucket；成功后数据库验收记录、Redis key/队列和 Bucket 对象均恢复到运行前状态。

## 6. 遗留风险

| 风险 | 影响 | 阻塞程度 | 处理方向 |
| --- | --- | --- | --- |
| 本次 MinIO 使用本地 HTTP，未覆盖公司对象存储 TLS/内部 CA | 目标环境证书链和厂商差异仍需部署验证 | 不阻塞 Phase 1 | staging 使用真实 CA 和测试 Bucket 复验 |
| 未由真实服务端制造 5xx/限流响应 | live 用例覆盖端点不可达；5xx/限流映射仍主要由单测覆盖 | 不阻塞 Phase 1 | staging 故障注入时补充 |
| 本轮未重做页面连接真实后端手测 | 页面与真实会话的最终人工证据未刷新 | 不阻塞 Phase 1 | 后续问答/工单页面端到端验收一并执行 |
| 尚未在目标 Linux 环境执行完整安装 | 本地结果不等同发布证明 | 不阻塞 Phase 1 | Phase 4 staging 发布门禁验证 |

## 7. 可重复执行

```bash
./scripts/run-phase1-integration.sh
```

运行器固定复用 `knowagent_integration`、Redis DB 15 和 `knowagent-phase1-it`。数据库和 Bucket 只在首次缺失时创建；每次运行使用唯一业务数据和 Redis 前缀，成功后仅清理本次验收记录、对象和队列消息，不创建或删除阶段数据库，不执行 `flushdb`。

## 8. 页面手动测试步骤

本轮未新增页面功能。可选复验步骤：

1. 打开用户端和管理端登录页，使用隔离管理员与系统负责人账号。
2. 管理员创建系统 A/B，仅为负责人分配系统 A。
3. 确认负责人可选择启用系统，且系统管理、加载失败和重试状态符合既有页面测试证据。
4. 文档上传、四格式处理、版本发布和越权拒绝由本报告的真实 API/live 用例验证。
