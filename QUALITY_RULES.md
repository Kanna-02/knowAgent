# Quality Rules

本文件是项目开发的质量增强规则，补充 `AI_DEVELOPMENT_RULES.md` 的质量保障维度。
AI 助手必须在开发过程中自觉执行本文件，**减少而非增加人工确认**。

## 版本与阈值

- 规则版本：2.1.0
- 最后更新：2026-07-12

### 默认阈值（可在本文件顶部覆盖）

以下阈值是默认值，项目可按类型调整。如需覆盖，在本节下方添加"项目覆盖"小节。

| 阈值项 | 默认值 | 说明 |
|---|---|---|
| 测试用例数 | 每个公开方法 ≥ 3 | 纯 getter/setter 除外 |
| 测试覆盖率 | ≥ 80% | 核心模块 ≥ 90%，CLI/脚本类项目 ≥ 60% |
| 函数长度 | > 100 行需评估拆分 | 算法密集型函数除外，需注释说明 |
| 模块文件长度 | > 500 行需评估拆分 | 自动生成代码除外 |
| 嵌套深度 | > 4 层需重构 | |
| 静态检查错误暂停阈值 | > 30 | 可按模块规模调整 |
| 重试次数 | 3 次 | LLM 调用 / 测试失败重试 |

### 项目覆盖（可选）

```text
整体测试覆盖率：>= 80%
权限、系统隔离、检索过滤、拒答判断和工单状态机核心模块：>= 90%
集成测试环境：公司禁止 Docker，使用隔离测试 Schema、Bucket、Redis namespace 和测试服务端点
静态检查语言规则：技术栈确认前保留 Python 与 TypeScript 两套模板，确认后仅执行实际语言栈规则
```

## 0. 核心原则

1. **规则内化**：规则写进文件，Agent 自觉执行，不增加确认点
2. **自动化优先**：能自动做的不要问用户（静态检查、追溯维护、自检清单）
3. **只在硬约束停下**：真正的硬阻断才停下确认（技术选型冲突、安全风险、不可恢复操作）
4. **质量内建**：质量在过程中保障，不是事后审计

## 1. 自检清单（每个阶段产出前 Agent 内部自检，不问用户）

### 1.1 需求阶段自检

产出 `docs/product/01-requirements-clarification.md` 前，内部对照：

- [ ] 项目目标明确（要解决什么问题、为谁解决、解决到什么程度）
- [ ] 核心功能列表完整，每条标注 P0/P1/P2 优先级
- [ ] P0 项不超过功能总数的 40%
- [ ] 验收标准可验证（包含可观察的输出/状态/阈值，禁止"系统正常运行"等模糊表述）
- [ ] 用户角色枚举完整
- [ ] 至少 1 个端到端流程描述完整（输入→处理→输出）

**自检未通过**：Agent 自觉修正，不输出给用户。
**自检通过**：直接产出文档，进入下一阶段。

### 1.2 技术选型阶段自检

产出 `docs/engineering/04-tech-decisions.md` 前，内部对照：

- [ ] 所有依赖版本号真实存在（通过 `pip index versions` 或官方文档验证）
- [ ] 候选方案覆盖 2-3 个（强制门禁，必须用户确认）
- [ ] 依赖无版本冲突
- [ ] 框架与语言版本兼容
- [ ] 选型覆盖需求文档中的所有技术约束

**自检未通过**：Agent 自觉修正或调整方案。
**自检通过**：输出给用户确认（这是唯一需要确认的点，因为是技术选型门禁）。

### 1.3 架构设计阶段自检

产出架构方案前，内部对照：

- [ ] 接口定义包含完整类型标注（参数名/参数类型/返回类型/异常类型）
- [ ] 接口签名与依赖模块的输入输出一致
- [ ] 模块职责清晰，无 >30% 语义重叠
- [ ] 依赖关系无循环（A→B→A）
- [ ] ADR 完整（决策点/上下文/候选/决策/反例验证）
- [ ] 需求模块 → 实现模块映射表无遗漏

**自检未通过**：Agent 自觉修正。
**自检通过**：输出给用户确认（架构确认门禁）。

### 1.4 功能实现阶段自检

每个功能实现完成后，内部对照：

- [ ] 代码遵循项目已有风格与命名规范
- [ ] 函数职责单一，无过大函数（>100 行需拆分）
- [ ] 类型标注完整（Python: mypy strict / TypeScript: strict mode）
- [ ] 错误处理完整（不吞异常、不空 catch、不 `any` 绕过）
- [ ] 无硬编码（敏感信息、magic number、URL）
- [ ] 测试覆盖正常路径/边界条件/异常路径
- [ ] 每个公开方法测试用例数达到默认阈值（见"默认阈值"章节，纯 getter/setter 除外）
- [ ] 禁止 mock 被测模块本身（只能 mock 其依赖）
- [ ] 禁止仅用 `assert result is not None` 这类弱断言

**自检未通过**：Agent 自觉修正，不输出给用户。
**自检通过**：直接提交，进入验证门禁。

## 2. 静态检查强制规则（自动执行，不问用户）

### 2.1 Python 项目

每个功能实现完成后，Agent 必须自动执行（无需用户指示）：

```bash
# 1. 格式化（先格式化再检查，避免格式噪音）
black src/ --line-length 100
isort src/ --profile black

# 2. 类型检查
mypy src/ --strict

# 3. 代码规范
pylint src/ --disable=C0114,C0115,C0116  # 禁用模块/类/函数 docstring 强制

# 4. 安全扫描
bandit -r src/ -ll  # 只报告中高危问题

# 5. 测试（含覆盖率）
pytest tests/ -v --cov=src --cov-report=term-missing --cov-fail-under=80
```

**失败处理**（Agent 自觉执行）：
- 错误数 ≤ 10：Agent 直接 Edit 修复，不问用户
- 错误数 10-30：Agent 按模块分批修复，不问用户
- 错误数 > 30：暂停，告知用户"静态检查错误过多，建议回退到架构阶段重新审视"

**Python 依赖**（写入 pyproject.toml 的 dev 依赖）：

```text
[tool.black]
line-length = 100

[tool.isort]
profile = "black"

[tool.mypy]
strict = true

[tool.pylint."messages control"]
disable = ["C0114", "C0115", "C0116"]

[tool.pytest.ini_options]
addopts = "--cov=src --cov-report=term-missing --cov-fail-under=80"

[tool.bandit]
severity = "MEDIUM"
```

dev 依赖列表：black, isort, mypy, pylint, bandit, pytest, pytest-cov

### 2.2 TypeScript/JavaScript 项目

```bash
# 1. 格式化
prettier --write "src/**/*.{ts,tsx,js,jsx}"

# 2. Lint
eslint src/ --ext .ts,.tsx --max-warnings 0

# 3. 类型检查
tsc --noEmit

# 4. 安全扫描
npm audit --audit-level=moderate

# 5. 测试（含覆盖率）
npm test -- --coverage --coverageThreshold='{"global":{"branches":80,"functions":80,"lines":80,"statements":80}}'
```

**失败处理**同 Python。

**TypeScript 依赖**（写入 package.json 的 devDependencies）：

```text
eslint, @typescript-eslint/parser, @typescript-eslint/eslint-plugin
prettier, eslint-config-prettier, eslint-plugin-prettier
typescript
vitest 或 jest + @vitest/coverage-v8 或 jest --coverage
```

推荐配置 husky + lint-staged，在 commit 前自动执行检查。

### 2.3 通用规则

- 静态检查配置在项目初始化时写入（`pyproject.toml` / `.eslintrc` / `tsconfig.json`）
- 格式化与静态检查的 commit 单独提交：`style: format with black+isort`
- 不因"格式化后看起来整洁"放松测试覆盖要求

## 3. 代码质量标准（自动遵循，不问用户）

### 3.1 类型标注

**Python**：
- 所有函数参数与返回值必须有类型标注
- 禁止使用 `Any`（除非有明确注释说明为什么不能用具体类型）
- 优先使用 `from __future__ import annotations` 启用 PEP 604 语法（`X | None` 而非 `Optional[X]`）

**TypeScript**：
- 启用 `strict: true`
- 禁止使用 `any`（用 `unknown` 替代并做类型 narrowing）
- 所有函数参数与返回值显式标注

### 3.2 错误处理

- 不吞异常（`except: pass` 或 `catch {}` 禁止）
- 不空 catch（必须记录日志或返回错误）
- 业务异常与系统异常分离（业务异常有明确错误码）
- 错误信息对用户友好（不暴露技术细节）

### 3.3 函数与模块

- 函数职责单一（单一职责原则）
- 函数长度超过默认阈值需评估拆分（算法密集型函数除外，需注释说明原因）
- 模块文件长度超过默认阈值需评估拆分（自动生成代码除外）
- 嵌套深度超过默认阈值需重构

### 3.4 命名规范

- 遵循项目已有命名风格（不创造新风格）
- 函数/变量用动词或名词，不用缩写（除非是通用缩写如 URL/HTTP）
- 类名用名词，不包含 Manager/Helper 等无意义后缀
- 常量全大写下划线分隔

## 4. 测试质量标准（自动遵循，不问用户）

### 4.1 测试覆盖

- 每个公开方法测试用例数达到默认阈值（见"默认阈值"章节，纯 getter/setter 除外）：覆盖正常路径 / 边界条件 / 异常路径
- 测试覆盖率达到默认阈值（核心模块用核心标准，CLI/脚本类项目可放宽）
- 禁止仅用 `assert result is not None` 这类弱断言
- 禁止 mock 被测模块本身（只能 mock 其依赖）

### 4.2 测试组织

- 单元测试：`tests/unit/test_{module_name}.py`
- 集成测试：`tests/integration/test_{feature_name}.py`
- 测试文件与被测文件一一对应

### 4.3 测试命名

- 测试函数：`test_{method_name}_{scenario}_{expected_result}`
- 例：`test_search_with_empty_query_returns_empty_list`

## 5. 自动确认规则（什么时候 Agent 可以自主推进）

**核心原则**：低风险实现细节 Agent 自主决策，高风险决策才停下确认。

### 5.1 Agent 可以自主推进（不问用户）

- 代码实现细节（函数实现、变量命名、内部结构）
- 静态检查错误修复（错误数 ≤ 30）
- 测试编写与修复
- 文档更新（changelog、status、project-structure）
- 格式化与代码风格统一
- 自检清单通过后的产出提交
- Bug 修复（复现 → 定位 → 修复 → 验证）
- 重构（在测试保护下）

### 5.2 Agent 必须停下确认

- 技术选型（tech skill 的门禁）
- 架构方案确认（architect skill 的门禁）
- 新增依赖（影响包大小/性能/成本/安全）
- 数据库 schema 变更
- 破坏性 API 变更（删除/重命名公开接口）
- 部署与环境变更
- 安全/权限/数据删除/合规相关
- 付费服务/外部服务接入
- 静态检查错误数 > 30（暗示架构问题）

### 5.3 模糊地带的处理

当不确定是否应该停下确认时：
- **默认推进**：Agent 自主决策并记录在 `docs/development/14-decision-log.md`
- **事后告知**：在完成说明中告知用户做了什么决策
- **风险标注**：如果决策有风险，明确标注剩余风险

## 6. 追溯矩阵（自动维护，不问用户）

### 6.1 维护规则

每个阶段产出后，Agent 自动更新 `docs/development/17-traceability-matrix.md`：

| 需求点 id | 描述 | P 级 | AC 编号 | 实现模块 | 代码文件 | 状态 |
|---|---|---|---|---|---|---|

- **需求阶段**：写入需求点 id、描述、P 级、AC 编号
- **架构阶段**：填充实现模块列
- **功能实现**：填充代码文件列
- **集成测试**：标记状态为 ok / gap / user_override

### 6.2 校验规则

- 任何需求点的"实现模块"列为空 → 标记 gap，Agent 自觉补充
- 任何需求点的"代码文件"列为空且非 user_override → Agent 自觉补充
- 用户显式跳过某项 → 标注 `user_override`，不消除风险痕迹

### 6.3 失败统计

模块生成失败时，Agent 自动记录到追溯矩阵的"失败统计"章节：

| 模块名 | 失败类别 | 重试次数 | 最终处理 | 备注 |

失败类别：
- `ast_contract_violation`：实现与接口定义不一致
- `dependency_failure`：依赖缺失或冲突
- `static_check_critical`：静态检查致命错误
- `test_persistent_failure`：测试持续失败
- `review_persistent_failure`：代码审查持续不通过

## 7. 失败处理规则（自动执行，不问用户）

### 7.1 重试策略

| 失败类型 | 重试次数 | 处理方式 |
|---|---|---|
| LLM 调用失败（可重试） | 3 次 | 指数退避（1s/2s/4s） |
| 单元测试失败（≤20% 用例） | 3 次 | Edit 定向修复 |
| 单元测试失败（20%-50%） | 3 次 | 整模块重生成 |
| 单元测试失败（>50%） | 0 次 | 标记 failed，告知用户 |
| 静态检查错误（≤30） | 自动 | Agent 直接修复 |
| 静态检查错误（>30） | 0 次 | 暂停，告知用户 |

### 7.2 3 次重试失败后

- 模块状态标记为 failed
- 暂停当前批次推进
- 告知用户介入，提供选项：
  - A：手动编辑代码 → 标记 done
  - B：降低标准重生（放宽测试覆盖，仅保证接口正确）
  - C：锁定跳过（locked，下游按"接口可用"假设继续）

### 7.3 失败率监控

- 当前批次 failed 模块数 / 总模块数 > 20% → 暂停，建议回退到架构阶段
- 避免下游模块基于多个错误假设生成

## 8. 评审规则自优化（元规则）

### 8.1 触发条件

- 每完成 3 个项目，或
- 用户主动说"回顾评审规则"，或
- 失败率统计显示某类失败占比 > 30%

### 8.2 执行步骤

1. Agent 读取 `docs/development/17-traceability-matrix.md` 的失败统计
2. 对每条规则统计：
   - 触发率 = 触发次数 / 项目数
   - 用户采纳率 = 用户因此修改的次数 / 触发次数
   - 盲区率 = 评审 pass 但下游失败的次数 / 评审 pass 总数
3. 生成 `docs/development/18-review-rule-effectiveness.md`
4. 应用调整规则：
   - 触发率 < 5% 且采纳率 < 30% → 标记"建议下线"
   - 触发率 > 50% 且采纳率 < 30% → 标记"疑似误报，调整表述"
   - 采纳率 > 70% → 标记"高价值规则，可加强"
   - 盲区率 > 20% → 标记"规则有漏洞，补充检查维度"
5. 用户确认后，更新本文件的规则（git commit 留痕）

## 9. 与 AI_DEVELOPMENT_RULES.md 的关系

本文件是 `AI_DEVELOPMENT_RULES.md` 的质量增强补充：

| 维度 | AI_DEVELOPMENT_RULES.md | QUALITY_RULES.md |
|---|---|---|
| 定位 | 通用开发规范 | 质量增强规则 |
| 重点 | 行为准则、禁止事项 | 自检清单、自动执行规则 |
| 确认点 | 多处需要确认 | 减少确认，自动化优先 |
| 适用 | 所有项目 | 所有项目（可按需裁剪） |

**冲突时以 AI_DEVELOPMENT_RULES.md 为准**，本文件只做增强。
