# 🏗️ Agent Hub — 施工验收对照单

> **使用方式**：每完成一个施工项，执行对应的验收测试，通过后打 ✅。
> **设计图纸**（代码细节）：见同目录 `implementation_plan_v4_blueprint.md`
> **阶段门禁**：每个阶段结束时必须 100% 通过才能进入下阶段。

---

## 〇、施工准备

- [ ] **P0.1** 备份现有项目
  - 执行：`cp -r /home/zy/investment_system /home/zy/investment_system_backup_$(date +%Y%m%d)`
  - 验收：备份目录存在且文件数量一致

- [ ] **P0.2** 确认 conda 环境
  - 执行：`conda activate investment_bot && python --version`
  - 验收：Python 3.10+

- [ ] **P0.3** 安装新增依赖
  - 执行：`pip install pyyaml`（lark-oapi 和 requests 应已存在）
  - 验收：`python -c "import yaml; print('ok')"`

- [ ] **P0.4** 设置环境变量
  - 执行：将飞书凭证写入 `~/.bashrc` 或 `.env`
  - 验收：`echo $FEISHU_INVEST_APP_ID` 有值

---

## 一、Phase 1 — 地基施工（7个工作日）

> 目标：框架核心就位，模板Bot通过飞书ping通
> 设计图纸参考：`implementation_plan_v4_blueprint.md` §2-§8

### 1A — 骨架创建

- [ ] **1A.1** 创建目录骨架
  - 产出：`core/`, `channels/`, `providers/`, `tools/`, `hooks/`, `bots/_template/`, `config/` 及所有 `__init__.py`
  - 验收：`find agent_hub -name "__init__.py" | wc -l` ≥ 10

### 1B — Core 层（框架心脏）

- [ ] **1B.1** `core/context.py` — 数据结构定义
  - 产出：Context, SkillManifest, ToolManifest, HookManifest, ChannelManifest, ProviderManifest, PhaseConfig, ExecutionRecord
  - 图纸：§2.1 完整代码
  - 验收：`python -c "from core.context import Context, SkillManifest; print('ok')"`

- [ ] **1B.2** `core/registry.py` — 自动发现注册表
  - 产出：Registry 类（discover, get, get_handler, match_by_trigger, to_ai_index）
  - 图纸：§5.1 完整代码
  - 验收：`python -c "from core.registry import Registry; r=Registry('test'); print(r.count())"`

- [ ] **1B.3** `core/middleware.py` — Hook 中间件管道
  - 产出：MiddlewarePipeline 类（register_hook, execute）
  - 图纸：§5.2 完整代码
  - 验收：`python -c "from core.middleware import MiddlewarePipeline; print('ok')"`

- [ ] **1B.4** `core/pending_store.py` — 待确认状态
  - 产出：PendingStore 类（set, get, pop, _clean）
  - 图纸：§5.3 完整代码
  - 验收：`python -c "from core.pending_store import PendingStore; ps=PendingStore('test'); ps.set('u1',{'a':1}); assert ps.get('u1')['a']==1; print('ok')"`

- [ ] **1B.5** `core/router.py` — 三层路由器
  - 产出：Router 类（route, _ai_match）
  - 图纸：§5.5 完整代码
  - 验收：`python -c "from core.router import Router; print('ok')"`

- [ ] **1B.6** `core/executor.py` — 执行引擎
  - 产出：execute_in_runtime(), get_ai_provider(), _resolve_provider_name()
  - 图纸：§5.4 完整代码
  - 验收：`python -c "from core.executor import execute_in_runtime; print('ok')"`

- [ ] **1B.7** `core/bot_runtime.py` — Bot运行时容器
  - 产出：BotConfig dataclass, BotRuntime 类
  - 图纸：§5.6 完整代码
  - 验收：`python -c "from core.bot_runtime import BotConfig, BotRuntime; print('ok')"`

- [ ] **1B.8** `core/bot_loader.py` — Bot加载器
  - 产出：BotLoader 类（discover_and_load, _load_config, _start_channel）
  - 图纸：§5.7 完整代码
  - 验收：`python -c "from core.bot_loader import BotLoader; print('ok')"`

### 1C — Channel 层

- [ ] **1C.1** `channels/base.py` — 抽象基类
  - 产出：ChannelBase（start, send_reply, build_context）
  - 图纸：§3.1
  - 验收：`python -c "from channels.base import ChannelBase; print('ok')"`

- [ ] **1C.2** `channels/feishu_ws.py` — 飞书实现
  - 产出：FeishuWSChannel, create_channel()
  - 图纸：§3.2
  - 验收：`python -c "from channels.feishu_ws import create_channel; ch=create_channel(); print(type(ch))"`

### 1D — Provider 层

- [ ] **1D.1** `providers/base.py` — 抽象基类（含重试）
  - 产出：ProviderBase（call, check_available, call_with_retry）
  - 图纸：§4.1
  - 验收：`python -c "from providers.base import ProviderBase; print('ok')"`

- [ ] **1D.2** `providers/claude_cli.py` — Claude
  - 产出：ClaudeCLIProvider, create_provider()
  - 图纸：§4.2
  - 验收：`python -c "from providers.claude_cli import create_provider; p=create_provider(); print(p.check_available())"`

### 1E — Tool 层（最小集）

- [ ] **1E.1** `tools/feishu_token.py`
  - 源码：`shared/feishu_utils.py` L9-26
  - 验收：`python -c "from tools.feishu_token import get_token; print('ok')"`

- [ ] **1E.2** `tools/feishu_message.py`
  - 源码：`shared/feishu_utils.py` L29-56
  - 验收：`python -c "from tools.feishu_message import send_text; print('ok')"`

- [ ] **1E.3** `tools/feishu_file.py`
  - 源码：`shared/feishu_utils.py` L59-128
  - 验收：`python -c "from tools.feishu_file import send_file; print('ok')"`

### 1F — Hook 层

- [ ] **1F.1** `hooks/dedup.py` — 消息去重
  - 验收：`python -c "from hooks.dedup import MANIFEST; print(MANIFEST.name, MANIFEST.phase)"`
  - 预期输出：`dedup before`

- [ ] **1F.2** `hooks/auth.py` — 用户鉴权
  - 验收同上模式，预期：`auth before`

- [ ] **1F.3** `hooks/timer.py` — 执行计时
  - 含 before + after 两个 handler
  - 验收：`python -c "from hooks.timer import MANIFEST; print(MANIFEST.name)"`

- [ ] **1F.4** `hooks/audit.py` — 操作审计
  - 写入 `bots/xxx/memory/store/executions.jsonl`
  - 验收：`python -c "from hooks.audit import MANIFEST; print(MANIFEST.name)"`

### 1G — Bot 模板 + 配置

- [ ] **1G.1** `bots/_template/` 完整模板
  - 产出：bot.yaml + skills/hello.py + hooks/__init__.py + prompts/registry.yaml + memory/store/
  - 图纸：§7-§8
  - 验收：`ls bots/_template/skills/hello.py && echo ok`

- [ ] **1G.2** `config/settings.py` — 全局配置
  - 验收：`python -c "from config.settings import load_global_config; print('ok')"`

- [ ] **1G.3** `config/global.yaml`
  - 验收：文件存在且可被 yaml.safe_load 解析

### 1H — 入口

- [ ] **1H.1** `main.py`
  - 图纸：§5.8
  - 验收：`python -c "import main; print('ok')"` （不启动，仅验证可导入）

- [ ] **1H.2** `requirements.txt`
  - 内容：lark-oapi, pyyaml, requests
  - 验收：文件存在

---

### 🚧 阶段门禁：Phase 1 验收

> 以下全部通过才能进入 Phase 2

- [ ] **G1.1** 复制 `_template` 为 `bots/test_bot`，修改 `bot.yaml` 中 name/label/app_id
- [ ] **G1.2** `python main.py` 启动成功，控制台输出 `agent_hub — 1 个Bot运行中`
- [ ] **G1.3** 飞书给 test_bot 发 `ping`，收到 `✅ test_bot Bot 运行正常！`
- [ ] **G1.4** 控制台可见 timer hook 输出耗时
- [ ] **G1.5** `bots/test_bot/memory/store/executions.jsonl` 出现审计记录
- [ ] **G1.6** 删除 `hooks/timer.py`，重启，其他功能仍正常（可拔插验证）
- [ ] **G1.7** 恢复 `hooks/timer.py`

---

## 二、Phase 2 — 投研Bot迁移（10个工作日）

> 目标：全部投研功能迁移到 `bots/investment/`，旧bot.py退役
> 设计图纸参考：`implementation_plan_v4_blueprint.md` §6, §10, §11

### 2A — 补全 Tool 层

- [ ] **2A.1** `tools/file_read.py` — 文件读取
  - 新建，统一 `Path.read_text` 封装 + 编码检测
  - 验收：`python -c "from tools.file_read import read_file; print('ok')"`

- [ ] **2A.2** `tools/file_write.py` — 文件写入 + git
  - 源码：`bot.py` L949-961 + `memo_handler.py` L40-55（合并去重）
  - 验收：`python -c "from tools.file_write import write_file, git_commit; print('ok')"`

- [ ] **2A.3** `tools/search_grep.py` — 知识库搜索
  - 源码：`bot.py` L398-433（返回结构化 list[dict] 而非格式化文本）
  - 验收：`python -c "from tools.search_grep import search; print('ok')"`

- [ ] **2A.4** `tools/wechat_fetch.py` — 微信文章抓取
  - 源码：`投研工作台/_系统/tools/wechat_parser.py`（迁移核心函数）
  - 验收：`python -c "from tools.wechat_fetch import fetch_article; print('ok')"`

- [ ] **2A.5** `providers/deepseek_api.py`
  - 图纸：§4.3
  - 验收：`python -c "from providers.deepseek_api import create_provider; print('ok')"`

### 2B — 投研Bot配置

- [ ] **2B.1** `bots/investment/bot.yaml`
  - 图纸：§7
  - 验收：`python -c "import yaml; d=yaml.safe_load(open('bots/investment/bot.yaml')); print(d['name'])"`
  - 预期：`investment`

- [ ] **2B.2** `bots/investment/prompts/registry.yaml`
  - 图纸：§6 完整示例（p7/p5/p2a/p2b/p4/p10/p11/p2pre共8个Phase）
  - 验收：`python -c "import yaml; d=yaml.safe_load(open('bots/investment/prompts/registry.yaml')); print(len(d['phases']))"`
  - 预期：`8`

- [ ] **2B.3** 复制 Phase prompt 文件到 `bots/investment/prompts/phases/`
  - 源目录：`投研工作台/研究/prompts/Phase*.md` + `投研工作台/行业筛查/prompts/Phase*.md`
  - 验收：`ls bots/investment/prompts/phases/*.md | wc -l` ≥ 8

- [ ] **2B.4** 提取 `prompts/system/recording_rules.md`
  - 源码：`bot.py` L41-77 `RECORDING_RULES` 字符串
  - 验收：文件存在且包含"录入"相关规范

- [ ] **2B.5** 提取 `prompts/system/classify_intent.md`
  - 源码：`bot.py` L449-453 classify_intent 的 prompt
  - 验收：文件存在且包含"p7"和"p11"

### 2C — Skill 迁移（按复杂度递增）

> 每个 skill 迁移后立即通过飞书测试验收

- [ ] **2C.1** `skills/system_status.py` — 零token指令集
  - 源码：`bot.py` L221-307（cmd_status/cmd_quota/cmd_directory/cmd_help/cmd_latest 等）
  - 触发词：`s`, `d`, `h`, `hh`, `e`, `z`, `库`
  - 飞书验收：发 `s` 收到状态信息 ✅ | 发 `d` 收到目录 ✅ | 发 `h` 收到帮助 ✅

- [ ] **2C.2** `skills/memo_save.py` — 备忘录
  - 源码：`bot.py` L1071-1083 + `memo_handler.py`
  - 触发词：`memo`
  - 飞书验收：发 `memo 测试内容` 收到确认 ✅

- [ ] **2C.3** `skills/framework_view.py` — 认知框架查看
  - 源码：`bot.py` L313-355
  - 触发词：`心法`, `焦点`, `图谱`, `图谱 [行业]`, `论 [行业]`, `找 [关键词]`
  - 飞书验收：发 `心法` 收到内容 ✅ | 发 `论 铜` 收到底稿 ✅

- [ ] **2C.4** `skills/framework_update.py` — 认知框架更新
  - 源码：`bot.py` L673-723
  - 触发词：`焦点+`, `图谱+`, `论+`
  - 飞书验收：发 `焦点+ 测试` 收到AI更新结果 ✅

- [ ] **2C.5** `skills/kb_query.py` — 知识库问答
  - 源码：`bot.py` L839-898
  - 触发词：`问`, `析`, `比`, `总`
  - Token优化：知识库目录树按需裁剪注入（§10.1 第二级）
  - 飞书验收：发 `问 铜的库存走势` 收到AI回答 ✅

- [ ] **2C.6** `skills/dialog_mode.py` — 连续对话
  - 源码：`bot.py` L1057-1065 + L1189-1208
  - 触发词：`kk`, `jj`
  - Token优化：对话历史5轮后压缩（§10.1 第三级）
  - 飞书验收：发 `kk` → 连续问几个问题 → 发 `jj` 退出 ✅

- [ ] **2C.7** `skills/ingest_record.py` — 手动录入（含确认流程）
  - 源码：`bot.py` L521-667
  - 触发词：`录`
  - 控制指令：`ok`, `确认`, `改 [意见]`, `/cancel`, `/redo`
  - 使用 `pending_store` 管理待确认状态
  - 飞书验收：发 `录 某某公司...` → 收到预览 → 发 `ok` → 收到入库确认 ✅

- [ ] **2C.8** `skills/ingest_url.py` — URL投喂
  - 源码：`bot.py` L458-518
  - 触发：发送裸URL
  - AI输出改为 JSON schema（§10.2）
  - 飞书验收：发一个微信公众号URL → 收到蒸馏入库确认 ✅

- [ ] **2C.9** `skills/phase_execute.py` — 通用Phase执行器
  - 源码：`bot.py` L729-803
  - 触发词：所有Phase触发词（从 registry.yaml 读取）
  - 飞书验收：发 `蒸馏 + 一段纪要` → 收到处理结果 ✅

- [ ] **2C.10** `skills/crystallize.py` — 知识沉淀
  - 新建（§11.3 完整代码）
  - 触发词：`沉淀`, `统计`, `复盘`
  - 飞书验收：发 `统计` 收到7天执行统计 ✅

### 2D — 集成与切换

- [ ] **2D.1** 删除 `bots/test_bot/`（Phase 1 的测试Bot）

- [ ] **2D.2** 新旧并行测试
  - 新架构用测试飞书应用
  - 逐一对比30+指令的输入输出
  - 记录差异并修复

- [ ] **2D.3** 正式切换
  - 更新 `start.sh` 指向 `main.py`
  - 旧文件重命名：`bot_claude/bot.py` → `bot_claude/bot_legacy.py`

---

### 🚧 阶段门禁：Phase 2 验收

> 全部通过才能进入 Phase 3

- [ ] **G2.1** 以下指令全部正常工作：

| 类别 | 指令 | 通过 |
|------|------|------|
| 状态 | `s` | [ ] |
| 目录 | `d` | [ ] |
| 帮助 | `h` | [ ] |
| 更多帮助 | `hh` | [ ] |
| 额度 | `e` | [ ] |
| 最新 | `z` | [ ] |
| 当前库 | `库` | [ ] |
| 心法 | `心法` | [ ] |
| 焦点 | `焦点` | [ ] |
| 图谱 | `图谱` | [ ] |
| 图谱查行业 | `图谱 铜` | [ ] |
| 论点卡 | `论 原奶` | [ ] |
| 搜索 | `找 开工率` | [ ] |
| 备忘 | `memo 测试` | [ ] |
| 录入 | `录 xxxxx` → `ok` | [ ] |
| 修改 | `录 xxx` → `改 换个标题` → `ok` | [ ] |
| 取消 | `录 xxx` → `/cancel` | [ ] |
| 重做 | `录 xxx` → `/redo` | [ ] |
| 问答 | `问 铜的库存` | [ ] |
| 分析 | `析 原奶 当前价格` | [ ] |
| 对比 | `比 铜 铝` | [ ] |
| 汇总 | `总 化工行业` | [ ] |
| 焦点更新 | `焦点+ xxxxx` | [ ] |
| 图谱更新 | `图谱+ 铜 价格` | [ ] |
| 论点更新 | `论+ 原奶 产能` | [ ] |
| 对话开 | `kk` | [ ] |
| 对话关 | `jj` | [ ] |
| 停止 | `/stop` | [ ] |
| 清除 | `/clear` | [ ] |
| 切换KB | `切 xxx` | [ ] |
| URL投喂 | 发送裸URL | [ ] |
| Phase蒸馏 | `蒸馏 xxx` | [ ] |
| Phase周报 | `周报` | [ ] |
| 统计 | `统计` | [ ] |
| 沉淀 | `沉淀` | [ ] |

- [ ] **G2.2** `executions.jsonl` 有完整的执行记录
- [ ] **G2.3** 旧 `bot.py` 已停用，`start.sh` 指向新入口
- [ ] **G2.4** 每个 skill 文件行数 < 300（无万能文件）
- [ ] **G2.5** 可拔插测试：删除 `skills/memo_save.py`，其他功能正常，发 `memo` 返回"未注册"

---

## 三、Phase 3 — 扩展验收（5个工作日）

### 3A — 新Bot迁入

- [ ] **3A.1** `bots/gemini/` — DeepSeek Bot
  - 源码：`bot_gemini/bot.py`
  - `bot.yaml` 中 `ai_provider: deepseek_api`
  - 飞书验收：给gemini Bot发消息收到DeepSeek回复 ✅

- [ ] **3A.2** `bots/daily_report/` — 日报Bot
  - 源码：`daily_reporter/`
  - 使用 scheduler channel 适配器
  - 验收：定时任务正常触发

- [ ] **3A.3** `bots/health/` — 健康Bot占位
  - `bot.yaml` 中 `enabled: false`
  - 验收：`main.py` 启动时跳过，控制台显示"跳过 健康管家（disabled）"

### 3B — 扩展能力

- [ ] **3B.1** `channels/cli.py` — 调试渠道
  - 验收：`python -c "from channels.cli import create_channel; print('ok')"`

- [ ] **3B.2** README.md — 新Bot创建指南
  - 包含：5步创建流程、目录说明、示例代码

### 3C — 清理

- [ ] **3C.1** 删除 `bot_claude/bot_legacy.py`（确认一周无问题后）
- [ ] **3C.2** 删除 `shared/`（确认所有功能已迁移）
- [ ] **3C.3** 考虑目录重命名 `investment_system` → `agent_hub`

---

### 🚧 最终验收

- [ ] **F.1** `python main.py` 启动 ≥ 2 个 Bot
- [ ] **F.2** 每个 Bot 独立工作，互不影响
- [ ] **F.3** 新建一个空Bot（复制_template），5分钟内飞书ping通
- [ ] **F.4** 删除任意一个 skill/hook/provider，其他模块不受影响
- [ ] **F.5** `统计` 命令展示正确的执行数据
- [ ] **F.6** 全部代码没有硬编码的 API Token 或密钥
- [ ] **F.7** 飞书凭证全部从环境变量读取
