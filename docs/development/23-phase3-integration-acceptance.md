# Phase 3 集成验收报告

验收结论：**4/4 功能范围、当前环境可执行的自动化、本地真实 Rerank 和运营页浏览器验收通过；Phase 3 尚未正式关闭**。

截至 2026-08-08，混合检索/Rerank/显式降级、多轮上下文与配置版本、通知投递与重试、文档生命周期/分析/审计均已实现。剩余门禁依赖仓库外输入：真实 ESB 标注评测集、真实公司通知 API 测试端点和目标 Linux 资源。不得用合成问题、本地 Stub 或 macOS 结果替代这些验收。

## 1. 已通过范围

| 范围 | 结果 | 证据 |
| --- | --- | --- |
| 混合检索与降级 | 通过 | 加权 RRF、有限候选 Rerank、向量/Rerank 两级显式降级；真实 PostgreSQL/Redis/API/SSE 浏览器验证向量降级拒答仍创建工单 |
| 本地 Rerank 运行时 | 通过 | 对外模型 ID 与本地路径解耦；`FlagEmbedding==1.4.0` + `transformers==4.57.6` 复用已有原生权重 |
| 本地 Rerank 真实推理 | 通过 | 相关候选约 `4.82495`，无关候选约 `-11.01469`；真实 HTTP 集成 1 passed（17.67 秒），进程级请求约 10.37 秒 |
| 多轮与配置版本 | 通过 | 意图识别、查询重写、上下文限流、prompt/retrieval profile list/get/save/activate、持久化版本、审计和前端配置页 |
| 通知代码与本地契约 | 通过（非正式外部验收） | 事务 Outbox、独立队列、自动/人工重试、attempt fencing、配置/记录页面；MockTransport 与本地 FastAPI Stub 4 项通过 |
| 文档生命周期与运营页 | 通过 | 文档版本/发布/退役、概览/高频问题/知识缺口、全局审计 API 与页面完成；桌面/移动真实登录/API 验收通过 |
| 横向质量门禁 | 通过 | 后端 401 passed、25 skipped，覆盖率 85.55%；model-service 51 passed、2 skipped，覆盖率 86.76%；前端 93/93，四维覆盖率均超过 80% |

## 2. 浏览器验收

在 `1440x900` 和 `390x844` 下使用真实 PostgreSQL、Redis、API 和登录会话验证：

1. 文档页面加载系统与版本数据，表格、抽屉和发布状态在桌面/移动视口内可用。
2. 分析页面加载概览、高频问题和知识缺口；移动端整页 `scrollWidth` 从 538 修复为 390，表格内部保持可滚动。
3. 审计页面加载筛选、分页和详情；长操作标签使用省略和 Tooltip，不再覆盖相邻结果列。
4. 临时管理员、Redis Session 和本轮测试审计记录已清理；没有把临时账号或业务数据写入迁移/种子。

## 3. 自动化与静态检查

```text
Phase 2/3 真实 PostgreSQL/Redis/Ollama/Qwen/Worker/API/SSE：23 passed，6 warnings
Phase 3 PostgreSQL live：1 passed
通知 API + 本地 FastAPI Stub：4 passed
本地 Rerank HTTP integration：1 passed
Backend：401 passed，25 skipped，coverage 85.55%
Model-service：51 passed，2 skipped，coverage 86.76%
Frontend：93 passed，coverage 90.52% / 82.43% / 85.51% / 91.82%
```

Backend Black/isort、171 个源文件 mypy strict 和 Bandit 中高危门禁通过。Model-service 本次变更文件 Black、8 个源文件 mypy strict、相关 Pylint 10.00/10 和 Bandit 中高危门禁通过；未改动的 `ollama.py` 仍有既有 Black 格式差异。前端 TypeScript、ESLint、Prettier、Vite build 和 `npm audit` 通过，漏洞 0。

当前机器 UI 渲染负载较高时，前端默认 5 秒测试超时两次均为 80/93；不改断言、仅将本次运行超时放宽到 20 秒后 93/93 通过。该现象记录为测试稳定性风险，不作为业务断言失败。

## 4. 阶段关闭门禁

| 门禁 | 当前状态 | 关闭条件 |
| --- | --- | --- |
| AC-004/AC-005 真实质量与 Rerank 收益 | 阻塞 | 至少 50 条真实标注 ESB 可回答问题及真实无知识问题集；执行基础 RRF/Rerank 对比并达到既定阈值 |
| AC-014 公司通知 | 阻塞 | 使用真实公司测试端点验证鉴权、限流、幂等接收、回执和 staging 故障重试；本地 Stub 不计入 |
| 目标 Linux 推理与容量 | 阻塞 | 提供目标 CPU/内存/GPU，生成生产依赖锁并验证 Rerank 延迟、内存、并发与降级 |
| 带引用回答和工单处理页面 | 待业务数据 | 提供已发布知识和对应负责人角色数据，完成回答引用、处理、答案提交、审核与来源展示 |

因此 Phase 3 在路线图中保持“进行中（功能范围完成）”。外部输入到位前，代码侧没有可继续伪造完成的工作。

## 5. 复验命令

```bash
./scripts/run-phase2-integration.sh --with-llm

cd model-service
export KNOWAGENT_TEST_RERANK_MODEL_PATH=/absolute/path/to/knowledge-rag/deploy/models/bge-reranker-v2-m3
PYTHONPATH=src .venv/bin/pytest --no-cov tests/integration/test_live_rerank.py -m integration -v

cd ../frontend
npm exec -- vitest run --coverage --testTimeout=20000
npm run typecheck
npm run lint
npm run format:check
npm run build
npm run audit
```
