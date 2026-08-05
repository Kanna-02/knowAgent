# Phase 2 集成验收报告

验收结论：**功能与真实服务集成范围通过，Phase 2 尚未正式关闭**。

2026-08-05 使用项目真实 `.env` 配置完成 PostgreSQL 17/pgvector/pg_trgm、Redis、Ollama bge-m3、`qwen3.5-27b`、文档 Worker、可靠问答、SSE、工单和审核回流组合验证。AC-003、AC-006、AC-007 的本轮实现范围已有自动化与真实服务证据；AC-004、AC-005 仍缺用户提供的真实标注评测集，问答/工单业务页仍需有账号和业务数据的人工浏览器记录。

## 1. 环境与资源

- Python 3.11.15
- PostgreSQL 17.10，`vector 0.8.6`，`pg_trgm 1.6`
- 固定数据库 `knowagent_integration`
- Redis DB 15，每次运行使用唯一 key prefix
- 本地 Ollama `bge-m3`，经 model-service `/v1/embeddings`
- Qwen OpenAI 兼容端点，模型 `qwen3.5-27b`

运行器不会按每次执行创建或删除数据库。固定数据库首次缺失时才创建；成功后精确清理本轮记录，失败时保留现场供诊断。API key 仅来自忽略的 `backend/.env`，报告不记录密钥。

## 2. 本轮通过范围

| 集成点 | 结果 | 证据 |
| --- | --- | --- |
| PostgreSQL 迁移和扩展 | 通过 | `alembic upgrade head`、`alembic check`，无 schema 漂移 |
| Worker 文档索引 | 通过 | 真实 manifest/chunk 经 Ollama bge-m3 生成 1024 维向量并写入 pgvector |
| Worker 故障恢复 | 通过 | Embedding 不可用进入持久重试状态 `EMBEDDING_UNAVAILABLE`，成功后才进入 `SUCCEEDED/READY_DRAFT` |
| Qwen 增量回答 | 通过 | `qwen3.5-27b` 在 Provider 完成前产生至少一个已验证 `answer_delta`，最终回答引用逐字受证据约束 |
| SSE token 安全 | 通过 | token 绑定账号、单次消费；其他账号消费和同账号重放均失败 |
| 问答 API | 通过 | 鉴权、CSRF、系统访问、输入校验、回答、拒答与 SSE 端点 |
| 系统隔离检索 | 通过 | 两个系统同主题不同标记，关键词/向量结果零交叉 |
| 答案和历史引用 | 通过 | 来源退役后仍能读取原始引用快照 |
| 可靠拒答和工单 | 通过 | 同系统同问题拒答按时间窗合并，工单发生次数可追踪 |
| 工单工作流 | 通过 | 分派、开始、回复、解决、关闭、重开完整往返 |
| 审核发布和回流 | 通过 | 工单答案生成 Embedding、发布为 `TICKET` 来源并在 5 分钟内可检索 |
| 跨系统工单知识隔离 | 通过 | 另一系统不能检索已发布的工单知识 |

完整命令结果：

```text
./scripts/run-phase2-integration.sh --with-llm
23 passed, 6 warnings in 36.69s
```

警告均来自 SWIG 类型和 Starlette TestClient/httpx 的依赖弃用提示，不影响本轮断言。

## 3. 本轮补齐的缺陷

1. 流式端点原先只能在 Provider 完成后发送最终文本；现按完整 claim 边界增量解析，并在发送前执行引用白名单、逐字引用和声明支撑校验，原始 JSON 与未验证事实不下发。
2. SSE token 原先未绑定消费账号；现 Redis key 和 token payload 均绑定 `account_id`，并使用单次消费语义。
3. Worker 原先可能在 Embedding 失败时仍完成任务；现索引是任务完成条件，Provider 故障进入持久重试状态，重试复用已保存的解析结果。
4. 默认前端测试在当前机器并行执行时偶发 Worker 崩溃；Vitest 关闭文件并行后，默认命令 47/47 稳定通过。
5. AC-004/AC-005 原先没有可执行质量门禁；现提供 `knowagent-evaluate-phase2`，但不伪造真实问题或人工标签。

## 4. 执行方式

```bash
# 不调用 Qwen，验证其余真实服务链路
./scripts/run-phase2-integration.sh

# 完整验收，使用 backend/.env 的真实 Qwen 配置
./scripts/run-phase2-integration.sh --with-llm
```

质量评测另行执行：

```bash
cd backend
PYTHONPATH=src .venv/bin/knowagent-evaluate-phase2 /absolute/path/to/phase2-observations.jsonl
```

输入和人工标注规则见 `docs/development/22-phase2-evaluation.md`。

## 5. 阶段关闭门禁

| 门禁 | 当前状态 | 关闭条件 |
| --- | --- | --- |
| AC-003 四格式解析、索引和定位 | 自动化/真实基础设施通过 | 页面诊断信息可随业务页人工验收复核 |
| AC-004 答案质量和引用支持 | 阻塞 | 至少 50 条真实标注 ESB 可回答问题；正确率 >=80%，引用支持率 >=95% |
| AC-005 拒答质量 | 阻塞 | 真实无知识问题集；拒答召回率 >=90%，每次拒答有工单，零无依据回答 |
| AC-006 工单闭环 | API/真实数据库通过 | 有账号的浏览器人工验证列表、详情、回复和状态流转 |
| AC-007 审核回流 | API/真实服务通过 | 有账号的浏览器人工验证答案提交、审核结果和来源展示 |

本地开发库在本轮浏览器检查时为空，没有账号。已验证登录页通过真实 Vite→API 代理加载，但未为了截图注入长期测试账号或伪造工单/知识数据。因此 Phase 2 保持“进行中”，下一步首先需要真实评测集，其次由用户使用实际账号完成页面人工验收记录。
