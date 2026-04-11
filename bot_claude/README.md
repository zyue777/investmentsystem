# ClaudeBot — 知识库主力机器人

**底层**：Claude CLI (`claude --print --dangerously-skip-permissions`)  
**接入**：飞书 WebSocket 长连接（无需公网端口）  
**职责**：Phase 调度、录入确认、URL 全自动入库、知识库搜索

> **无 git 提交**：写入后不自动 git commit，由用户手动管理。通过 `git status` / `git diff` 查看所有新增内容后再提交。

---

## 指令速查

```
[URL]               URL 投喂（全自动：抓取→Phase 7 蒸馏→直接落盘，无需确认）
投喂/蒸馏/存档 [URL] 同上

录 [内容]           生成情报卡 → 预览 → ok 确认 → git commit
ok / 确认           执行上一个待确认写入
改 [意见]           基于意见重新生成，替换待确认内容
/cancel             取消待确认写入
/redo               重新生成上一张情报卡

找 [关键词]         本地 grep 搜索知识库（零 Token）
问 [问题]           基于知识库回答
析 [行业] [问题]    调用论点卡底稿做行业深度分析
比 [行业A] [行业B]  横向对比两个行业底稿
总 [主题]           汇总主题下所有文件要点
初研 [行业]         生成行业初步研究底稿

p7 [内容]           Phase 7 — 私密纪要结构化蒸馏
p5                  Phase 5 — 周度高频雷达
p2a / p2b           Phase 2A/2B — 月度深研（成长/刚需）
p3                  Phase 3 — 反转排行打分
p6 / p6x            Phase 6/6X — 流程质检 / 矛盾检查

焦点+ [内容]        更新当下关注焦点
图谱+ [行业] [数据] 更新行业核心指标图谱
论+ [行业] [内容]   更新行业论点卡底稿

心法 / 焦点 / 图谱  查看对应认知框架文件
论 [行业]           查看行业论点卡
库                  查看当前激活的知识库
切 [名称]           切换知识库（多知识库支持）

memo [备忘]         零 Token 写入备忘录（08_Investment_Memos/）
备忘 [备忘]         同上

kk / 开始对话       进入连续对话模式（后续无需指令前缀）
jj / /clear         退出连续对话，清空历史
/stop               终止当前运行中的 Claude 任务
s / 状态            查看服务状态
d / 目录            查看知识库目录结构
h / 帮助            查看简短帮助
hh / 更多           查看完整帮助
```

---

## 三层消息路由

```
收到消息
│
├─ 第一层：零 Token 系统指令（状态/目录/帮助/ok/改/切换等）
│
├─ URL 投喂检测（豁免规则）
│   └─ 裸 URL 或 投喂/蒸馏/存档 前缀
│       → wechat_parser.py → _Raw_Inbox → Phase 7 → 直接落盘 → git commit
│
├─ 第二层：Phase 触发（p7/p5/p2a/p2b/p3/p6/p6x 及别名）
│   └─ 加载 prompt → Claude → _pending_writes → ok → 写入 → git commit
│
└─ 第三层：智能任务指令
    ├─ 找 → 本地 grep（无 Claude 调用）
    ├─ 录 → handle_record() → 生成情报卡 → 预览 → ok → 写入 → git commit
    ├─ 焦点+/图谱+/论+ → handle_framework_update() → 预览 → ok → 写入
    └─ 问/析/比/总/无前缀 → call_claude_print() → deliver_result()
```

---

## 录入确认流程（写入知识库）

```
用户发「录 [内容]」
  ↓
call_claude_print(NO_WRITE_PREFIX + RECORDING_RULES + 内容)
  ↓
_parse_record_output()  解析 FILE_PATH: 行 + 内容
  ↓
_pending_writes[open_id] = {path, content, ts, kb, type='new'}
  ↓
发预览（含目标路径）
  ↓
用户回复「ok」→ handle_confirm()
  ↓
Path(kb) / '知识库' / '行业' / path  → write_text()
  ↓
回复「✅ 已入库\n📁 路径」
```

`_pending_writes` 超时 30 分钟自动清除（`_clean_expired_pending()`，每条消息入口调用）。

---

## URL 投喂流程（豁免规则，无需确认）

```
收到裸 URL（或「投喂/蒸馏/存档 URL」）
  ↓
python3 _系统/tools/wechat_parser.py "[URL]"
  ↓
原文落入 _Inbox/YYYY-MM-DD_WechatRaw_标题.md
  ↓
加载 Phase 7 prompt → call_claude_print()
  ↓
_parse_record_output() 解析路径和内容
  ↓
直接写入 Path(kb) / '知识库' / '行业' / path（跳过预览和 ok）
  ↓
回复「✅ 已入库: 路径\n📎 原文存档: 文件名」
```

---

## Phase 输出目录映射

| Phase | 输出目录 |
|-------|---------|
| p5 | `研究/周报月报/周度雷达/` |
| p2a | `研究/周报月报/` |
| p2b | `研究/周报月报/` |
| p3 | `行业筛查/困境反转/` |
| p10 | `研究/_系统/碎片备忘/_Weekly_Digest/` |
| p7 / p6 / p6x | 由 Claude 输出 FILE_PATH 决定 |

---

## 文件写入路径规则

| `pending['type']` | 路径拼接 |
|-------------------|---------|
| `'new'`（录 指令） | `Path(kb) / '知识库' / '行业' / pending['path']` |
| `'phase'`（Phase） | `Path(kb) / pending['path']` |
| `'update'`（框架更新） | `Path(pending['path'])` （已存储绝对路径） |

---

## 临时文件约定

| 用途 | 路径 |
|------|------|
| 长回复溢出存档 | `_Inbox/latest_result.md` |
| Phase/初研长预览 | `_Inbox/_preview_{phase_key}.md` |

> **禁止**在知识库根目录创建 `inbox/`、`draft/` 等目录（见 CLAUDE.md 操作原则）。

---

## 配置项（config.json）

| 字段 | 说明 |
|------|------|
| `app_id` | 飞书应用 App ID |
| `app_secret` | 飞书应用 App Secret |
| `kb_roots` | 多知识库字典，如 `{"投研": "/home/zy/桌面/投研工作台"}` |
| `default_kb` | 默认激活的知识库名称 |

---

## 依赖

- Python 3.8+
- `lark-oapi`（飞书 SDK）
- `claude` CLI 已安装并可用（`claude --print` 可执行）
- conda 环境：`investment_bot`
