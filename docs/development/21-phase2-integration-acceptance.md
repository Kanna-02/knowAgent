# Phase 2 核心服务集成验收报告

验收结论：**核心服务范围通过，Phase 2 尚未正式关闭**。

2026-08-04 已使用项目真实 `.env` 配置，在固定 integration 资源上完成 PostgreSQL 17/pgvector/pg_trgm、Ollama bge-m3、Qwen、可靠问答、工单和知识审核回流的组合验证。问答 API/SSE、工单 API、文档索引 Worker 接线及页面端到端流程不在当前可执行链路内，仍是阶段关闭门禁。

## 1. 环境与资源

- Python 3.11.11
- PostgreSQL 17.10，`vector 0.8.6`，`pg_trgm 1.6`
- 固定数据库 `knowagent_integration`
- Redis DB 15，每次运行使用唯一 key prefix
- 本地 Ollama `bge-m3`，经 model-service `/v1/embeddings`
- `backend/.env` 配置的 Qwen OpenAI 兼容端点、模型和 API key

运行器不会为每次测试新建或删除数据库。仅在固定数据库首次不存在时创建一次；成功后只精确清理本轮业务记录，失败时保留现场供诊断。

## 2. 已通过范围

| 集成点 | 结果 | 证据 |
| --- | --- | --- |
| PostgreSQL 迁移和扩展 | 通过 | `upgrade head`、`alembic check`，vector/pg_trgm 可用 |
| Ollama Embedding | 通过 | bge-m3 返回 1024 维归一化向量并写入 pgvector |
| Qwen 回答契约 | 通过 | 真实流式回答含受证据约束的逐字引用 |
| 系统隔离检索 | 通过 | 两个系统同主题不同标记，关键词/向量结果零交叉 |
| 答案和历史引用 | 通过 | 来源退役后仍能读取原始引用快照 |
| 可靠拒答和工单 | 通过 | 两次同问题拒答合并到同一工单，发生次数为 2 |
| 工单工作流 | 通过 | 分派、开始、回复、解决、关闭、重开完整往返 |
| 审核发布和回流 | 通过 | 工单答案生成 Embedding、发布为 TICKET 来源并在 5 分钟内可检索 |
| 跨系统工单知识隔离 | 通过 | 另一系统不能检索到已发布的工单知识 |

## 3. 缺陷与修复

首次 PostgreSQL 运行暴露两个父子 INSERT 顺序缺陷。SQLAlchemy unit-of-work 只从 mapper relationship 建立 ORM 依赖；答案/引用模型只有表级复合外键，因此同一次 flush 按 mapper 顺序先写引用。拒答链路则由应用显式先调用 occurrence 仓储并立即 flush，早于其依赖的 evidence decision。

修复后顺序为：

1. `evidence_decisions -> answers -> answer_citations`
2. `tickets -> evidence_decisions -> ticket_occurrences`

事务边界和幂等语义未变化。

## 4. 执行方式

```bash
# 核心链路，不调用 Qwen 合约用例
./scripts/run-phase2-integration.sh

# 完整验收，包含 backend/.env 中配置的真实 Qwen
./scripts/run-phase2-integration.sh --with-llm
```

最终结果：2 项 live 用例通过，耗时 36.85 秒；Alembic 未检测到 schema 漂移。标准后端套件 250 项通过、3 项 live 门禁跳过，总覆盖率 90.72%；Black/isort、mypy strict、本次范围 Pylint 10.00/10、Bandit 中高危 0 和 Bash 语法检查通过。

## 5. 阶段关闭缺口

1. 问答 API/SSE 和会话持久化尚未装配。
2. 工单 API 路由尚未装配。
3. 文档入库 Worker 尚未调用 Phase 2 Embedding 索引服务。
4. 用户端与管理端尚无可执行的真实页面端到端闭环。

以上缺口完成并验收前，Phase 2 保持进行中。
