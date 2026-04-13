# bots/investment_ds — DeepSeek 投研 Bot

> AI Provider：`deepseek_api` | 进程类型：子进程（`run_single_bot.py` 启动）

## ⚠️ Skills 同步规则

`skills/` 目录与 `bots/investment/skills/` **内容必须保持一致**（两份 Copy，非 symlink）。

修改任意 Skill 文件后，执行：
```bash
diff bots/investment_ds/skills/<file> bots/investment/skills/<file>
# 确认 diff 输出为空（完全一致）后才算完成
```

## 目录结构

```
investment_ds/
├── bot.yaml        # Bot 配置（channel / ai_provider / workspace）
├── skills/         # 业务 Skill（与 investment 保持同步）
├── hooks/          # Bot 专属 Hook（如有）
├── prompts/        # Phase prompt 文件 + registry.yaml
└── memory/         # 内存/状态文件（运行时生成）
```

## Skill 流程速查

| Skill | 触发 | 流程 |
|-------|------|------|
| `ingest_file` | 发送文件 | 单步直接入库（无确认） |
| `ingest_url` | 发送裸URL | 单步直接入库（无确认） |
| `ingest_record` | `录 [内容]` | 两步：预览 → ok 确认 |
| `kb_query` | 任意问题（兜底） | 单步问答 |
| `phase_execute` | registry.yaml 触发词 | 由 `needs_confirm` 字段控制 |
