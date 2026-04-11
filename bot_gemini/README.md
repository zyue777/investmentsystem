# DeepSeekBot — 快速问答 & 报告机器人

**底层**：DeepSeek API (`deepseek-chat`)  
**接入**：飞书 WebSocket 长连接（无需公网端口）  
**职责**：URL 蒸馏确认入库、按需财经报告、知识库问答

> **无 git 提交**：DeepSeekBot 写入文件后不自动 git commit，由用户手动管理。
> 方便通过 `git status` / `git diff` 一次性查看所有新增内容再提交。

---

## 指令速查

```
[URL]               URL 投喂（抓取→DeepSeek 蒸馏→确认写入）
投喂/蒸馏/存档 [URL] 同上

晨报                生成股票晨报（美股/港股/A股盘前）
商品报              生成大宗商品晨报（能源/金属/农产品/黑色系）
自选股              生成自选股日报（7只股票涨跌+公告+AI动态）
复盘                生成当日复盘（A股+港股+板块+北向）

分析：[问题]         读取知识库相关文件做分析（知识库文件列表传入）
录入：[内容]         整理内容后写入知识库（需确认）
更新：[目标] [内容]  找到对应文件并更新（需确认）
查找：[关键词]       全文搜索知识库，返回摘要
总结：[主题/公司]    汇总主题下所有文件要点
[无前缀]            自由提问，AI 主动判断是否引用知识库

确认 / yes          执行待写入操作
取消 / no           放弃待写入操作

memo [备忘]         零 Token 写入备忘录（08_Investment_Memos/）
备忘 [备忘]         同上

状态                查看服务状态（知识库路径/文件数/模型）
目录                查看知识库文件树
帮助                查看本帮助
```

---

## 消息处理流程

```
收到消息
│
├─ 系统指令（状态/目录/帮助）→ 直接回复
│
├─ 确认/取消 → 执行或放弃 _pending_writes
│
├─ 备忘 / memo → 直接写文件（零 Token）
│
├─ 按需报告（晨报/商品报/自选股/复盘）
│   └─ 调用 daily_reporter 数据抓取 + DeepSeek 生成 → 发送
│
├─ URL 投喂（裸 URL 或 投喂/蒸馏/存档 前缀）
│   └─ wechat_parser.py 抓取原文 → _Raw_Inbox
│       → DeepSeek 蒸馏（===FILE_PATH=== 格式）
│       → parse_write_plan() 解析路径和内容
│       → _pending_writes（含 04_Private_Knowledge/ 前缀）
│       → 发预览（确认/取消）
│       → 确认 → write_kb_file() → 写入知识库
│
└─ 知识库任务（分析/录入/更新/查找/总结/无前缀）
    └─ build_messages() 拼接 KB 文件列表 + 指令
        → call_deepseek() → parse_write_plan() / 直接回复
```

---

## URL 投喂流程详解

```
用户发 URL（或「投喂/蒸馏/存档 URL」）
  ↓
⏳ 正在抓取文章...
python3 tools/wechat_parser.py "[URL]"
  ↓
原文存入 04_Private_Knowledge/_Raw_Inbox/YYYY-MM-DD_WechatRaw_标题.md
  ↓
⏳ 正在蒸馏（20-40 秒）...
DeepSeek system prompt 要求输出：
  ===FILE_PATH===
  04_Private_Knowledge/[子目录]/[文件名].md
  ===END_PATH===
  ===FILE_CONTENT===
  [情报卡三段式 Markdown]
  ===END_CONTENT===
  ↓
parse_write_plan() 解析路径和内容
  ↓
自动补全 04_Private_Knowledge/ 前缀（若缺失）
  ↓
_pending_writes[open_id] = {file_path, content, ts}
  ↓
发预览（「📋 蒸馏完成」+ 目标文件 + 内容预览）
  ↓
用户回复「确认」→ write_kb_file() → ✅ 已写入
```

---

## 写入确认流程（录入/更新）

```
用户发「录入：[内容]」
  ↓
build_messages('录入', 内容) 拼接：
  知识库文件列表 + 内容 + WRITE_FORMAT 格式要求
  ↓
call_deepseek() → parse_write_plan() 解析
  ↓
_pending_writes[open_id] = {file_path, content, ts}
  ↓
发预览（目标文件 + 内容前 400 字）
  ↓
用户回复「确认」→ write_kb_file() → ✅ 已写入
```

`_pending_writes` 超时 30 分钟自动清除。

---

## 知识库文件列表传递规则

`list_kb_files()` 递归遍历知识库，但**过滤掉以下目录**，不暴露给 DeepSeek：
- `04_Private_Knowledge/_Raw_Inbox/`（临时原文，未蒸馏）
- 任何名为 `inbox` 的路径

目的：防止 DeepSeek 看到临时文件名后幻觉出其内容（DeepSeek 只收到路径字符串，无法真正读取文件）。

---

## 文件写入路径规则

`write_kb_file(relative_path, content)` 直接拼接：`KB_PATH / relative_path`

URL feed 流程会在设置 `_pending_writes` 时自动补全 `04_Private_Knowledge/` 前缀；
`录入`/`更新` 指令由 DeepSeek 在 prompt 中自行决定路径（用户应在 prompt 中说明目标目录）。

---

## 临时文件约定

| 用途 | 路径 |
|------|------|
| 长回复溢出存档 | `04_Private_Knowledge/_Raw_Inbox/latest_result_deepseek.md` |

> **禁止**在知识库根目录创建 `inbox/`、`draft/` 等目录（见知识库 CLAUDE.md）。

---

## 配置项（config.json）

| 字段 | 说明 |
|------|------|
| `app_id` | 飞书应用 App ID |
| `app_secret` | 飞书应用 App Secret |
| `deepseek_api_key` | DeepSeek API Key |
| `kb_path` | 知识库根目录路径 |

---

## 依赖

- Python 3.8+
- `lark-oapi`（飞书 SDK）
- conda 环境：`investment_bot`
- 网络可访问 `api.deepseek.com`
