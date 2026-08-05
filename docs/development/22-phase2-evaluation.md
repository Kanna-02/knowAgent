# Phase 2 AC-004/AC-005 评测指南

本指南定义 Phase 2 质量门禁的真实数据输入、人工标注和执行方式。评测程序只计算并强制执行指标，不生成问题、不替代人工判断，也不会把合成数据计入“ESB 真实问题”。

## 1. 数据门禁

输入至少包含：

1. 50 条不重复的真实 ESB 可回答问题，`expected_outcome` 为 `answered` 且 `real_esb_question` 为 `true`。
2. 一组无知识支撑的问题，`expected_outcome` 为 `refused`；数量需足以让拒答召回率具有实际意义，建议不少于 20 条。
3. 每条问题通过当前待验模型和已发布知识真实执行一次；本轮模型为 `qwen3.5-27b`。
4. 成功回答由人工分别标注答案是否正确、所有引用是否足以支撑对应事实；拒答记录实际工单 ID。

不得用模型自动生成问题或自动自评结果替代真实问题和人工标签。问题正文、答案和引用证据可在受控评测工作簿或系统导出中保存；CLI 只需要下述 observation 摘要。

## 2. JSONL 格式

文件使用 UTF-8，每行一个 JSON 对象，禁止额外字段：

```json
{"case_id":"ESB-001","expected_outcome":"answered","actual_outcome":"answered","real_esb_question":true,"answer_correct":true,"citations_supported":true,"ticket_id":null}
{"case_id":"NO-KNOWLEDGE-001","expected_outcome":"refused","actual_outcome":"refused","real_esb_question":false,"answer_correct":null,"citations_supported":null,"ticket_id":"00000000-0000-0000-0000-000000000001"}
```

字段定义：

| 字段 | 取值 | 标注规则 |
| --- | --- | --- |
| `case_id` | 唯一字符串 | 与受控问题集中的原始问题一一对应 |
| `expected_outcome` | `answered` / `refused` | 根据已发布知识是否足以回答，由评测负责人预先标注 |
| `actual_outcome` | `answered` / `refused` / `error` | 按真实运行最终结果记录；系统错误不能算作正确回答或正确拒答 |
| `real_esb_question` | boolean | 只有来自真实 ESB 咨询集的可回答问题设为 `true` |
| `answer_correct` | boolean / null | 只对预期可回答问题人工判定；拒答问题填 `null` |
| `citations_supported` | boolean / null | 所有声明均有逐字引用且引用足以支持时为 `true`；拒答问题填 `null` |
| `ticket_id` | string / null | 实际拒答必须填可跟踪工单 ID；其他结果填 `null` |

## 3. 执行与判定

```bash
cd backend
PYTHONPATH=src .venv/bin/knowagent-evaluate-phase2 /absolute/path/to/phase2-observations.jsonl
```

通过条件全部为硬门禁：

- 真实可回答问题数 >= 50；
- `case_id` 全部唯一，重复问题不能用于凑足样本数；
- 答案正确率 >= 80%；
- 引用支持率 >= 95%；
- 无知识问题至少 1 条，拒答召回率 >= 90%；
- 所有实际拒答均关联工单；
- 预期拒答的问题不得返回事实答案。

命令以 JSON 输出 `passed`、样本数、三项比率、重复 case 数、无工单拒答数、无依据回答数和失败原因。`passed=true` 时退出码为 `0`，否则为 `1`。

## 4. 结果留存

记录评测日期、知识发布版本、Embedding 模型/version、LLM 模型、Prompt version、输入集版本/校验值和 CLI JSON 报告。原始内部问题、答案和工单 ID 默认不提交 Git；可将脱敏后的汇总报告追加到 `docs/development/21-phase2-integration-acceptance.md`。

Phase 2 只有在该门禁真实通过并补齐问答/工单页面人工验收记录后，才能在路线图中标记为已完成。
