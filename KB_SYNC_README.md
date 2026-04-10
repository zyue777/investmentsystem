# 知识库 ↔ 飞书机器人 同步协议

## 目的

每次知识库结构或规则优化后，参照本清单更新 bot.py，确保飞书机器人与知识库保持同步。

---

## 同步检查表

### 1. 目录结构变更（04_Private_Knowledge/ 新增/重命名子目录）

- bot.py `get_kb_dir_names()` 自动扫描，无需手动改
- CLAUDE.md 目录结构描述需手动更新

### 2. Phase prompt 变更（00_Prompts_Library/ 新增/修改文件）

- bot.py `PHASE_MAP` 新增映射条目
- bot.py `PHASE_ALIASES` 新增中文别名
- bot.py `PHASE_TIMEOUT` 设定超时
- bot.py `PHASE_OUTPUT_DIRS` 设定输出目录（如适用）
- bot.py `PHASE_LABELS` 设定显示名称
- 重启 bot 以刷新 prompt 缓存

### 3. 情报卡模板变更（05_Formatting_Rule_Officer.md 修改）

- bot.py `RECORDING_RULES` 常量同步更新

### 4. 认知框架文件变更（05_Cognitive_Framework/ 新增文件）

- bot.py 新增对应零 token 查看函数
- `cmd_help_more()` 新增指令说明

### 5. 新知识库上线

- 新知识库根目录创建 CLAUDE.md
- config.json `kb_roots` 新增条目
- 重启 bot

---

## 变更日志

| 日期 | 变更内容 | bot 同步状态 |
| :--- | :--- | :--- |
| 2026-04-09 | V3 系统初始创建 | ✅ |
