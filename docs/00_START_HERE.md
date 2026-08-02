# Project Documentation Starter

这是每个新项目启动时必须先执行的项目文档入口。AI 助手在开始开发前，必须先阅读本文件，并按流程完成需求澄清和文档初始化。

## 1. 启动原则

AI 不能在需求尚未澄清时直接进入开发。首次接到项目需求后，必须先完成：

1. 理解用户要做的产品是什么。
2. 识别目标用户、核心场景、主要功能、边界范围。
3. 明确技术约束、交付时间、部署方式、验收标准。
4. 产出项目文档初版。
5. 得到用户确认后，再进入开发。

## 2. 必须产出的文档

项目根目录建议建立 `docs/` 目录，并至少包含以下文件：

```text
docs/
  README.md
  01-requirements-clarification.md
  02-development-principles.md
  03-feature-changelog.md
  04-tech-decisions.md
  05-handoff-guide.md
  06-roadmap.md
  07-local-development.md
  08-deployment.md
  10-current-status.md
  11-project-structure.md
  12-upgrade-history.md
  13-command-reference.md
  15-frontend-design.md
  17-traceability-matrix.md
```

**可选文档**（仅在启用对应模式时由对应 skill 创建，未启用时缺失是预期行为，不要主动补建）：

```text
docs/
  14-decision-log.md          # 仅供 super skill（自主执行模式）使用，未启用 super 时缺失是预期
  16-retrospective.md         # 由 retro skill 首次触发时创建
  18-pipeline-status.md       # 由 pipeline skill 首次触发时创建
```

## 3. 新项目首次对话模板

```text
你现在是本项目的开发助手。

请先阅读项目根目录下的 AI_DEVELOPMENT_RULES.md 和 docs/00_START_HERE.md。

我接下来会描述一个新项目需求。你不要立刻写代码。

你需要先做三件事：
1. 用你自己的话复述你理解的项目目标。
2. 向我提出必要的需求澄清问题。
3. 在我确认后，生成 docs/ 下的项目文档初版，包括需求澄清、开发原则、技术选型、阶段路线图、本地启动说明、部署说明和后续接手指南。

我的项目需求是：
【在这里写需求】
```

## 4. AI 执行流程

AI 必须按以下顺序执行：

1. 需求复述：说明自己理解的项目目标、用户、核心功能和边界。
2. 需求澄清：只问真正影响产品方向、架构、验收或界面设计的问题。
3. 前端设计澄清：如果项目涉及网页、小程序、插件、App、桌面端、内部工具、后台系统、仪表盘或其他用户界面，必须先确认产品形态、目标用户、使用场景，并收集或推荐 2-5 个 UI 风格参考。
4. 设计关键词提炼：根据项目类型和参考风格，提炼整体气质、色彩、布局、卡片/组件风格、交互状态和需要避免的问题，并写入 `product/15-frontend-design.md`。
5. 文档初始化：按模板生成 `docs/` 文档。
6. 用户确认：等待用户确认需求、技术方向和设计方向。
7. 开发计划：拆分阶段任务和近期里程碑。
8. 进入开发：按 `AI_DEVELOPMENT_RULES.md` 执行代码实现与验证。

如果过程中涉及核心技术选型、重大依赖、架构变化、部署方案或第三方服务，AI 必须先给出 2-3 个候选方案、推荐理由、性能影响和维护成本，等待用户确认后再写入 `engineering/04-tech-decisions.md` 并实现。

## 5. 中途新增需求流程

本规则不仅适用于项目首次启动，也适用于开发过程中的任何新增需求、需求变更、功能调整或技术方案调整。

项目启动后，用户后续提出新需求时，AI 不需要用户重复粘贴启动提示词，也必须自动执行以下流程：

1. 判断这是新功能、功能变更、缺陷修复、体验优化还是技术调整。
2. 用简短语言复述对需求的理解。
3. 如果需求会影响产品范围、业务规则、数据结构、权限、技术方案、部署方式或验收标准，必须先提出澄清问题。
4. 澄清完成后，先更新相关文档，再进入代码实现。
5. 实现完成后，更新 `development/03-feature-changelog.md`。
6. 如果涉及技术选型或架构调整，更新 `engineering/04-tech-decisions.md`。
7. 如果影响路线图，更新 `product/06-roadmap.md`。
8. 如果影响本地启动或部署，更新 `operations/07-local-development.md` 或 `operations/08-deployment.md`。
9. 如果影响后续接手方式，更新 `handoff/05-handoff-guide.md`。
10. 如果准备切换对话、暂停开发、交接上下文或阶段性完成，更新 `development/10-current-status.md`。
11. 如果影响目录结构、模块边界或关键文件职责，更新 `engineering/11-project-structure.md`。
12. 如果影响产品形态、UI 风格、布局、组件策略、交互状态或前端体验边界，更新 `product/15-frontend-design.md`。
13. 如果涉及核心技术选型或重大依赖，先走技术选型门禁，等待用户确认后再实现。

用户后续只需要直接描述新需求，例如：

```text
新增一个用户邀请功能，管理员可以邀请成员加入团队。
```

AI 必须自动按本节流程处理，而不是要求用户重新提供完整启动提示词。

也可以使用命令前缀：

```text
/feature 新增一个用户邀请功能，管理员可以邀请成员加入团队。
/change 把邀请有效期从 24 小时改为 7 天。
/fix 用户接受邀请后没有自动加入团队。
/tech 将邀请邮件发送改为异步队列。
/deploy 补充生产环境邮件服务的环境变量和回滚步骤。
/status 总结当前开发进度并更新接续状态。
/continue 读取当前状态并继续开发。
/upgrade 补齐当前 Skill 新增的项目文档和规则。
/plan 当没有头绪时，基于现有项目文档推荐下一步功能、优化方向和优先级。
/goal 围绕一个最终目标自动推进开发，只有关键确认或阻塞时停下来。
/goal --super 进入高自治模式，全程由 AI 自主决策并推进，后续输出决策过程。
```

完整命令说明见 `docs/maintenance/13-command-reference.md`。

## 6. Skill 升级流程

当用户使用 `/upgrade`，或发现当前项目缺少新版模板中的文档时，AI 必须执行升级流程：

1. 检查当前项目已有的 `AI_DEVELOPMENT_RULES.md` 和 `docs/` 文档。
2. 对比当前 Skill 模板中的文档清单。
3. 只补齐缺失文件，默认不覆盖已有文档。
4. 如果需要把新规则合并进已有文档，先说明将要追加的位置和内容。
5. 升级后更新 `docs/maintenance/12-upgrade-history.md`。
6. 升级后更新 `docs/development/10-current-status.md`。
7. 如升级涉及项目结构说明，补充或更新 `docs/engineering/11-project-structure.md`。
8. 如升级涉及前端设计规范，补充或更新 `docs/product/15-frontend-design.md`。

## 7. 禁止行为

1. 用户刚给出模糊需求时直接写代码。
2. 没有确认产品目标就决定技术架构。
3. 文档只写空话，不写项目相关内容。
4. 技术选型只写用了什么，不写为什么用。
5. 新增功能后不更新功能变更文档。
6. 部署方式变化后不更新部署说明。
