# Deployment

本文档记录 KnowAgent 在公司内网 Linux 环境的发布基线。当前尚未执行真实部署；正式 systemd/Nginx 模板与发布脚本在 Phase 4 完成。

## 1. 环境与发布边界

| 环境 | 用途 | 数据隔离 | 部署方式 |
| --- | --- | --- | --- |
| integration | PostgreSQL/Redis/S3/模型真实契约验证 | 独立 Schema、Redis namespace、Bucket | 手工受控发布 |
| staging | 类生产安装、升级、回滚和容量验证 | 独立实例或命名空间 | systemd + Nginx + 版本目录 |
| production | 内网正式服务 | 最小权限账号、正式备份 | systemd + Nginx + 版本目录 |

禁止使用 Docker 作为运行前提。配置位于 release 目录外，权限为 `0600`；密钥不进入仓库、命令历史或日志。

## 2. 构建与部署前检查

```bash
cd backend
python -m pytest tests -v
python -m mypy src/knowagent --strict
python -m bandit -r src/knowagent -ll

cd ../frontend
npm ci
npm run test:coverage
npm run typecheck
npm run build
```

发布前还必须确认：目标 Python 3.11 依赖锁可安装、PostgreSQL 备份可恢复、Redis/S3 配置有效、迁移已在 staging 演练，且没有把未通过的检查记为成功。

## 3. 数据库迁移

```bash
cd /opt/knowagent/releases/<release-id>/backend
alembic upgrade head
alembic check
```

迁移 `3ba86a4c3d35` 的执行顺序是：

1. 为文档和版本增加当前发布指针、`system_id` 与发布状态列，并为入库任务增加原始 nullable `requested_document_id`。
2. 从 `documents.system_id` 回填已有版本，再收紧 `NOT NULL`、版本隔离外键以及当前指针的版本+文档+系统复合外键。
3. 创建 `knowledge_sources`、`knowledge_chunks` 及 `system_id + publish_status` 索引。

迁移前必须备份目标 Schema。禁止手工跳过回填或复合外键；这会破坏知识隔离保证。

## 4. 发布与验证

1. 解压构建产物到新的 `/opt/knowagent/releases/<release-id>`。
2. 以迁移专用账号执行 `alembic upgrade head`，确认 `alembic check` 无差异。
3. 切换 `current` 软链接并依次重启 API、交互 Worker、批处理 Worker 和 Beat。
4. 验证 `/health/live`、登录、文档上传、v2 上传和任务状态查询。
5. 在两个业务系统分别发布同名知识，验证跨系统 chunk 查询结果为 0。

## 5. 回滚

应用回滚通过 `current` 软链接切回上一 release。数据库默认不自动 downgrade；仅在确认没有新版本写入、完成备份且 downgrade 已在 staging 演练后，才可执行：

```bash
alembic downgrade d1a97d2e451b
```

`3ba86a4c3d35` downgrade 会删除知识来源/片段及发布状态列，属于数据丢失操作，生产环境必须单独审批。常规回滚应保持向后兼容 Schema，仅回退应用代码。

## 6. 未完成项

- 尚未在目标 Linux/Python 3.11 环境执行安装和发布。
- 尚未在真实 PostgreSQL 验证迁移锁时长、查询计划和复合外键行为。
- systemd unit、Nginx 配置、备份恢复演练和监控告警在 Phase 4 补齐。
