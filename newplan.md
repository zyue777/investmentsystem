# 🏗️ AI+飞书机器人项目架构改造计划制定

你是一位资深系统架构师，精通 Hermes Agent、LangChain、AutoGPT 等主流 Agent 框架的设计哲学。
请基于以下目标和体检结果，为我的项目制定一份**周全、可落地的架构改造计划**。

---

## 我的项目背景

- VSCode 开发环境，AI + 飞书机器人，执行本地项目任务
- 当前问题：新增功能时改动复杂、功能间互相影响、流程逻辑重复、无法积累沉淀
- 目标：像 Hermes Agent 一样，能持续迭代积累 tools、skills、hooks，
  AI 识别需求后自动复用，低 token 消耗，各模块完全独立互不影响

---

## 核心设计目标（必须全部满足）

### G1 — 独立性

每个 skill / tool / hook 是独立文件，互不 import，通过注册表松耦合。
新增功能 = 新建文件 + 一行注册，**零修改**现有代码。

### G2 — 可复用性

所有流程片段封装为 skill，skill 可组合调用。
tool 是原子操作，skill 是 tool 的编排。
任何 skill 可被任意入口（飞书消息、定时任务、API）触发。

### G3 — 可沉淀进化

每次成功执行自动沉淀为 skill 模板。
skill 有版本号，可以灰度替换。
执行历史可被 AI 检索，用于下次复用判断。

### G4 — Token 友好

Router 用轻量 embedding 或关键词向量匹配，不每次全量传 prompt。
Skill 描述保持 ≤50 字，AI 一次 pass 识别。
Context 对象按需裁剪，只传当前 skill 需要的字段。

### G5 — AI 友好

统一 Context 对象格式，AI 输出固定 JSON schema。
Skill registry 可以被 AI 直接读取和索引。
错误信息结构化，AI 能自动重试或降级。

---

## 请参考以下成熟框架的最佳实践

### 来自 Hermes Agent 的借鉴点

- **Function Registry**：所有工具集中注册，AI 按 schema 调用，无需修改路由
- **Structured Output**：每次 AI 输出严格 JSON，避免解析失败
- **Tool Composition**：复杂任务 = 多个原子 tool 的有序组合
- **Memory Layer**：短期记忆（对话上下文）+ 长期记忆（skill 库）分层管理

### 来自 LangChain 的借鉴点

- **Chain 模式**：skill = 一条可复用的 chain，输入输出标准化
- **Middleware**：hooks 用 middleware 模式实现，可叠加不互相影响
- **Callback System**：on_start / on_end / on_error 统一回调，横切关注点集中管理

### 来自插件系统的借鉴点

- **Plugin Manifest**：每个 skill/tool 有元数据文件（名称、描述、输入输出 schema、版本）
- **Lazy Loading**：skill 按需加载，不全量初始化
- **Isolation**：skill 运行在独立作用域，崩溃不传播

---

## 请制定的改造计划内容

### Part 1：目标架构设计

请输出完整的目录结构（精确到文件名），并说明每个文件/目录的职责。

目标架构应包含以下分层：
L0 — 入口层（飞书 webhook、定时触发、手动触发）
L1 — Router 层（意图识别、skill 匹配、context 组装）
L2 — Skill 层（可复用流程，每个 skill 独立文件）
L2 — Tool 层（原子操作，每个 tool 独立文件）
L2 — Hook 层（before/after/onError/onSuccess，可叠加）
L3 — Executor 层（实际执行，调用飞书 API/本地脚本）
L4 — Memory 层（执行历史、skill 注册表、成功模式沉淀）

### Part 2：核心数据结构定义

请定义以下核心对象的完整 schema（用 TypeScript interface 或 Python dataclass）：

- `Context`：贯穿所有层的统一数据对象
- `SkillManifest`：skill 的元数据描述
- `ToolManifest`：tool 的元数据描述
- `HookDefinition`：hook 的注册格式
- `ExecutionRecord`：执行历史记录格式（用于沉淀）

### Part 3：注册表机制设计

请设计 SkillRegistry、ToolRegistry、HookRegistry 的实现方案：

- 如何注册（文件发现 vs 显式注册）
- 如何被 Router 检索（关键词 / embedding / tag）
- 如何支持版本管理
- 如何让 AI 读取 registry 并做决策

### Part 4：分阶段改造路线图

请制定 3 个阶段，每阶段：

- 目标（用一句话描述达到的状态）
- 具体任务清单（可直接执行的步骤）
- 需要新建的文件
- 需要改造的现有文件
- 验收标准（如何证明这个阶段完成了）
- 预计工作量

阶段划分建议：

- **Phase 1（地基）**：统一 Context、建立 Registry、实现 4 个核心 Hook
- **Phase 2（插件化）**：现有功能迁移为独立 skill/tool 文件，Router 改注册表模式
- **Phase 3（进化）**：执行历史沉淀、skill 自动提炼、AI 索引 registry 复用

### Part 5：关键实现代码示例

请为以下关键机制提供可直接使用的代码示例：

1. Skill 文件模板（一个完整的 skill 文件长什么样）
2. SkillRegistry 注册与检索的核心实现
3. Hook 中间件的叠加机制
4. Router 如何根据用户消息匹配 skill（含 AI 辅助匹配的 prompt）
5. Context 对象在各层之间的流转示例

### Part 6：风险与注意事项

- 改造过程中如何保证现有功能不中断（渐进式迁移策略）
- 哪些地方容易踩坑，如何避免
- 性能瓶颈预判（Registry 检索、Hook 叠加的开销）
- 当 skill 数量增长到 50+/100+ 时，架构是否还成立

---

## 输出要求

- 语言：中文
- 格式：结构化文档，有清晰的标题层级
- 代码：根据我的项目语言（请先确认我用的是 Python 还是 Node.js/TypeScript）给出对应示例
- 深度：每个设计决策说明"为什么这样设计"，不只给结论
- 实用性：所有建议必须可以在我现有项目上渐进式落地，不是推倒重来

---

## 在开始前，请先确认

1. 我的项目使用什么语言/框架？（请我提供 package.json 或 requirements.txt）
2. 当前飞书 webhook 的处理入口文件是哪个？
3. 现有功能大概有几个？最复杂的是哪个？
4. 是否已有任何形式的数据库或持久化存储？

确认以上信息后，开始制定改造计划。

请结合我们的体检报告。

其次我想先让你知道。我这个investmentsystem项目独立于投研工作台之外，是一个辅助型待开发完善的项目，但是投研工作台主要是用于我日常投研的，我认为任何bot或者我的agent都能流畅预览这个工作台，而不是专门为bot设计的，bot的工作内容和流程，不应该出现在我的投研工作台以内。都应该在他自己的文件夹里面规范好。
