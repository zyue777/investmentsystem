#!/usr/bin/env bash
# start.sh
# 一键后台启动 bot_claude 和 bot_gemini 两个飞书机器人服务
# PID 文件写入 logs/ 目录，日志也输出到 logs/ 目录
# 使用 conda 环境：investment_bot

# ── 获取脚本所在目录（兼容通过绝对/相对路径调用）────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGS_DIR="$SCRIPT_DIR/logs"

# ── 激活 conda 环境 ────────────────────────────────────────────────────────
CONDA_BASE="$(conda info --base 2>/dev/null || echo "$HOME/miniconda3")"
source "$CONDA_BASE/etc/profile.d/conda.sh"
conda activate investment_bot

# 使用 conda 环境里的 python
PYTHON="$(which python)"
echo "[start.sh] Python: $PYTHON"

# 确保 logs 目录存在
mkdir -p "$LOGS_DIR"

# ── 启动 bot_claude（长连接模式，无需端口）────────────────────────────────────
echo "[start.sh] 启动 bot_claude ..."
nohup bash -c "cd '$SCRIPT_DIR' && '$PYTHON' bot_claude/bot.py" \
    > "$LOGS_DIR/bot_claude.log" 2>&1 &
BOT_CLAUDE_PID=$!
echo "$BOT_CLAUDE_PID" > "$LOGS_DIR/bot_claude.pid"
echo "[start.sh] bot_claude 已启动，PID=$BOT_CLAUDE_PID，日志: $LOGS_DIR/bot_claude.log"

# ── 启动 bot_gemini（端口 5001）──────────────────────────────────────────────
echo "[start.sh] 启动 bot_gemini ..."
nohup bash -c "cd '$SCRIPT_DIR' && '$PYTHON' bot_gemini/bot.py" \
    > "$LOGS_DIR/bot_gemini.log" 2>&1 &
BOT_GEMINI_PID=$!
echo "$BOT_GEMINI_PID" > "$LOGS_DIR/bot_gemini.pid"
echo "[start.sh] bot_gemini 已启动，PID=$BOT_GEMINI_PID，日志: $LOGS_DIR/bot_gemini.log"

# ── 启动每日报告调度器（使用 dailyreport 环境，含 tushare/yfinance/akshare）──
echo "[start.sh] 启动 daily_reporter 调度器 ..."
CONDA_DAILYREPORT="$CONDA_BASE/envs/dailyreport/bin/python"
nohup "$CONDA_DAILYREPORT" "$SCRIPT_DIR/daily_reporter/scheduler.py" \
    > "$LOGS_DIR/daily_reporter.log" 2>&1 &
REPORTER_PID=$!
echo "$REPORTER_PID" > "$LOGS_DIR/daily_reporter.pid"
echo "[start.sh] daily_reporter 已启动，PID=$REPORTER_PID，日志: $LOGS_DIR/daily_reporter.log"

echo ""
echo "三个服务均已在后台运行。"
echo "查看日志：tail -f $LOGS_DIR/bot_claude.log"
echo "          tail -f $LOGS_DIR/bot_gemini.log"
echo "          tail -f $LOGS_DIR/daily_reporter.log"
echo "停止服务：kill \$(cat $LOGS_DIR/bot_claude.pid) \$(cat $LOGS_DIR/bot_gemini.pid) \$(cat $LOGS_DIR/daily_reporter.pid)"
