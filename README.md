# investment_system — 飞书机器人调度系统

## 目录结构

```
investment_system/
├── bot_claude/         # 基于 Claude CLI 的飞书机器人
│   ├── bot.py          # 主调度脚本（Flask webhook，端口 5000）
│   └── config.json     # AppID / Secret / 知识库路径等配置
├── bot_gemini/         # 基于 Gemini API 的飞书机器人
│   ├── bot.py          # 主调度脚本（Flask webhook，端口 5001）
│   └── config.json     # 同上，额外含 gemini_api_key
├── shared/
│   └── feishu_utils.py # 公共函数：获取 token、发送文本消息
├── logs/               # 运行日志与 PID 文件（自动创建）
└── start.sh            # 一键后台启动脚本
```

## 快速开始

1. **填写配置**：分别编辑 `bot_claude/config.json` 和 `bot_gemini/config.json`，填入飞书 App ID / App Secret（以及 Gemini Key）。
2. **安装依赖**：`pip install flask requests`
3. **启动服务**：`bash start.sh`
4. **配置飞书事件订阅**：在飞书开放平台将 Webhook 地址设为 `http://<你的
IP>:5000/webhook`（Claude）或 `:5001/webhook`（Gemini）。
5.
# 手动激活
conda activate investment_bot

# 启动两个机器人（已自动激活环境）
bash ~/investment_system/start.sh

# 日后补装依赖
conda activate investment_bot && pip install -r ~/investment_system/requirements.txt

## 支持的指令前缀

| 前缀 | 示例 | 行为 |
|------|------|------|
| `分析：` | `分析：茅台最新财报` | 读取知识库后给出分析 |
| `录入：` | `录入：今日调研记录...` | 整理并写入知识库 |
| `更新：` | `更新：修改某股票目标价` | 找到对应文件更新内容 |
| 无前缀 | `A股近期走势如何` | 直接基于知识库回答 |
