# bot_gemini

基于 **Gemini API** 的飞书机器人，监听端口 **5001**。

## 工作原理

1. 飞书将用户消息以 POST 请求推送到 `/webhook`
2. 解析指令前缀（`分析：` / `录入：` / `更新：` / 无前缀）
3. 先回复 `⏳ 处理中...`，再异步调用 Gemini REST API（`gemini-2.0-flash`）
4. 将 Gemini 的输出发回给用户

## 配置项（config.json）

| 字段 | 说明 |
|------|------|
| `app_id` | 飞书应用 App ID |
| `app_secret` | 飞书应用 App Secret |
| `gemini_api_key` | Google Gemini API Key |
| `kb_path` | 知识库根目录，默认 `~/kb` |
| `port` | 监听端口，默认 `5001` |

## 依赖

- Python 3.8+
- `flask`、`requests`（`urllib` 已内置，用于 Gemini 调用）
- 可访问 Google API（需要网络代理时请自行配置）
