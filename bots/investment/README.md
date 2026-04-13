# bots/investment — Claude 投研 Bot

> AI Provider：`claude_cli` | 进程类型：主进程（`main.py` 直接加载）

## Skills 来源

- 共享 Skills 来自 `bots/_shared/skills/`（所有 Bot 共用）
- 如需覆盖某个 Skill，在本目录 `skills/` 下放同名文件即可

## 目录结构

```
investment/
├── bot.yaml        # Bot 配置（channel / ai_provider / workspace）
├── skills/         # Bot 专属 Skill 覆盖（目前为空，共享 Skills 已够用）
├── hooks/          # Bot 专属 Hook（如有）
├── prompts/        # Phase prompt 文件 + registry.yaml
└── memory/         # 内存/状态文件（运行时生成）
```
