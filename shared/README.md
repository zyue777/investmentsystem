# shared

存放两个机器人共用的飞书工具函数。

## feishu_utils.py

| 函数 | 说明 |
|------|------|
| `get_tenant_access_token(app_id, app_secret)` | 调用飞书内部应用鉴权接口，返回 `tenant_access_token` |
| `send_text_message(token, open_id, text)` | 向指定 `open_id` 用户发送一条文本消息 |

两个函数均使用 `requests` 库，超时设为 10 秒，出错时打印日志并返回空字符串 / `False`。
