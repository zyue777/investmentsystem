# Bot 工作流检查清单

修改任一 bot 后，逐项核对此清单。上次全面排查：2026-04-11。

---

## 一、格式对齐检查（最高优先级）

每次修改 prompt 或解析函数后必查。

### ClaudeBot — `_parse_record_output()`
解析格式：`FILE_PATH: [子目录]/[文件名].md`（首行，大小写不敏感）

- [ ] 所有调用 `call_claude_print()` 并期望写文件的地方，prompt 里都有 `FILE_PATH:` 格式指令
- [ ] `RECORDING_RULES` 中的格式要求与 `_parse_record_output()` 的正则匹配
- [ ] Phase prompt 文件（`00_Prompts_Library/`）中的 FILE_PATH 指令格式一致
- [ ] `handle_phase()` 的 `full_prompt` 末尾追加了 `FILE_PATH: {out_dir}/...` 提示

### DeepSeekBot — `parse_write_plan()`
解析格式：必须同时含 `===FILE_PATH===...===END_PATH===` 和 `===FILE_CONTENT===...===END_CONTENT===`

- [ ] URL feed 的 `_distill_msgs` system prompt 和 user prompt **都**要求 `===FILE_PATH===` 格式
- [ ] `录入`/`更新` 的 `build_messages()` 拼接了 `WRITE_FORMAT`（含 `===FILE_PATH===` 格式）
- [ ] `WRITE_FORMAT` 常量与 `parse_write_plan()` 的正则字符串一致（勿改任一而漏改另一）

---

## 二、写入路径检查

### ClaudeBot
- [ ] `handle_confirm()` 中三种 type 的路径拼接正确：
  - `'new'` → `Path(kb) / '04_Private_Knowledge' / pending['path']`
  - `'phase'` → `Path(kb) / pending['path']`（相对路径，须加 kb 前缀）
  - `'update'` → `Path(pending['path'])`（框架文件存的是绝对路径）
- [ ] `_parse_record_output()` 剥除重复 `04_Private_Knowledge/` 前缀（`.replace('04_Private_Knowledge/', '')`）
- [ ] 框架更新（焦点+/图谱+/论+）的 `pending['path']` 存的是完整绝对路径

### DeepSeekBot
- [ ] URL feed 写入 `_pending_writes` 前已补全 `04_Private_Knowledge/` 前缀
- [ ] `write_kb_file()` 拼接路径：`KB_PATH / clean`（`clean` 已包含 `04_Private_Knowledge/`）
- [ ] 路径穿越检测：`str(target).startswith(str(kb.resolve()))` 覆盖所有写入点

---

## 三、pending_writes 生命周期检查

### ClaudeBot
- [ ] `_clean_expired_pending()` 在 `handle_message_async()` 入口调用（每条消息都清理）
- [ ] 所有设置 `_pending_writes` 的地方都包含 `'ts': time.time()`：
  - `handle_record()` ✓
  - `handle_phase()` ✓
  - `handle_framework_update()` ✓
  - `初研` 代码块 ✓
- [ ] 所有设置 `_pending_writes` 的地方都包含 `'type'` 字段（`'new'` / `'phase'` / `'update'`）
- [ ] `handle_confirm()` 用 `pending.get('type', 'new')` 防御 KeyError

### DeepSeekBot
- [ ] `_clean_expired_pending()` 在 `handle_message_async()` 入口调用
- [ ] URL feed 写入 `_pending_writes` 时包含 `'ts': _time.time()`
- [ ] `录入`/`更新` 写入 `_pending_writes` 时包含 `'ts': _time.time()`

---

## 四、文件存在性检查

### ClaudeBot
- [ ] `焦点+`：写入前检查 `02_当下关注焦点.md` 存在（已有）
- [ ] `图谱+`：写入前检查 `03_行业核心指标图谱.md` 存在（已修复）
- [ ] `论+`：写入前检查匹配文件数 > 0（已有）
- [ ] `handle_phase()`：Phase prompt 文件不存在时有明确错误提示

---

## 五、禁止违规目录检查

以下目录**不得存在**于知识库根目录（违反 CLAUDE.md 操作原则）：

- [ ] `inbox/` — 不存在
- [ ] `draft/` — 不存在

检查命令：
```bash
ls ~/桌面/研究workflow优化/周期行业研究/ | grep -E "^inbox$|^draft$"
# 无输出 = 合规
```

临时文件只允许写入 `04_Private_Knowledge/_Raw_Inbox/`。

---

## 六、git 状态检查（用户手动）

两个 bot 均**不自动 git commit**，写入后由用户自行管理版本。

- [ ] `.gitignore` 包含 `.obsidian/`
- [ ] 写入成功提示中**不含** `git:` 字样（两个 bot）

定期在知识库目录手动执行：
```bash
cd ~/桌面/研究workflow优化/周期行业研究/
git status        # 查看新增/修改的文件
git diff          # 查看具体改动
git add -A && git commit -m "入库: YYYY-MM-DD 批量提交"
```

---

## 七、URL 投喂链路端到端测试

### ClaudeBot（全自动，无需 ok）
```
1. 发送微信公众号 URL
2. 预期回复顺序：
   ⏳ 抓取文章中...
   ⏳ Phase 7 蒸馏中，预计 30-60 秒...
   ✅ 已入库: 04_Private_Knowledge/[子目录]/[文件名].md
   📎 原文存档: [WechatRaw 文件名]
3. 验证文件确实存在于知识库对应子目录
```

### DeepSeekBot（需 确认）
```
1. 发送微信公众号 URL
2. 预期回复顺序：
   ⏳ 正在抓取文章，请稍候...
   ⏳ 正在蒸馏，预计 20-40 秒...
   📋 蒸馏完成
   目标文件：04_Private_Knowledge/[子目录]/[文件名].md
   内容预览：...
   回复【确认】写入，回复【取消】放弃
3. 回复「确认」
4. 预期：✅ 已写入：/path/to/04_Private_Knowledge/[子目录]/[文件名].md
5. 验证文件确实存在（路径包含 04_Private_Knowledge/）
```

---

## 八、已知问题历史（修复记录）

| 日期 | 问题 | 原因 | 修复 |
|------|------|------|------|
| 2026-04-11 | DeepSeekBot URL 投喂写入从未执行 | 蒸馏 prompt 要求 `FILE_PATH: xxx` 格式，但 `parse_write_plan()` 只认 `===FILE_PATH===` 格式 | 统一 prompt 为 `===FILE_PATH===` 格式 |
| 2026-04-11 | DeepSeekBot 读取 `_Raw_Inbox` 旧文件并幻觉内容 | `list_kb_files()` 把临时文件路径暴露给 DeepSeek | 过滤 `_Raw_Inbox` 和 `inbox` 路径 |
| 2026-04-11 | 知识库根目录出现违规 `inbox/` | 两个 bot 把临时文件存入 `KB_ROOT/inbox/` | 改存 `04_Private_Knowledge/_Raw_Inbox/` |
| 2026-04-11 | ClaudeBot Phase 报告写入位置错误 | `handle_confirm()` 的 `'phase'` type 用了相对路径直接 `Path(path)`，CWD 不是 KB 根 | 拆出独立分支 `Path(kb) / pending['path']` |
| 2026-04-11 | `图谱+` 文件不存在时崩溃无提示 | 未检查文件存在就调用 `read_text()` | 补 `if not target.exists()` 检查 |
| 2026-04-11 | ClaudeBot `_pending_writes` 过期清理不全 | `_clean_expired_pending()` 只在 `handle_record()` 里调用 | 移至 `handle_message_async()` 入口 |
| 2026-04-11 | DeepSeekBot URL feed 情报卡写入知识库根目录散乱位置 | `_pending_writes['file_path']` 缺少 `04_Private_Knowledge/` 前缀 | 写入 pending 前自动补全前缀 |
| 2026-04-11 | DeepSeekBot `_pending_writes` 无超时机制 | 无 `ts` 字段，无清理函数 | 新增 `PENDING_TIMEOUT=1800`、`_clean_expired_pending()` |
| 2026-04-11 | ClaudeBot 自动 git commit（非预期） | 设计决策变更：两个 bot 均改为不自动提交，用户手动 git | 删除 `_git_commit()` 调用，去掉成功消息中的 `git: hash` |

---

## 九、新增功能时的 Checklist

增加任何写文件的新功能时，逐项确认：

- [ ] prompt 里的格式要求与解析函数匹配
- [ ] AI 输出被解析后才写入，不信任 AI 说"已保存"
- [ ] `_pending_writes` 设置时包含 `'ts'`、`'type'`、`'kb'` 字段
- [ ] 写入路径包含正确的前缀（`04_Private_Knowledge/` 或 `02_Reports/` 等）
- [ ] 临时文件只写入 `_Raw_Inbox/`，不新建根目录下的临时文件夹
- [ ] 错误情况有明确的用户提示（`❌ ...`），不静默失败
