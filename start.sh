#!/bin/bash
# Agent Hub 统一启动脚本 v2
# 管理三个服务：
#   1. main.py          — Agent Hub 主进程（investment Claude Bot + investment_ds DeepSeek Bot）
#   2. scheduler_runner — daily_report 定时报告Bot（DeepSeek驱动）
#
# 用法:
#   bash start.sh           # 启动全部（前台，适合调试）
#   bash start.sh --daemon  # 后台启动全部（nohup）
#   bash start.sh --status  # 查看运行状态
#   bash start.sh --stop    # 停止全部

set -e
cd "$(dirname "$0")"

# ── 环境变量 ──────────────────────────────────────────────────────────────────
export FEISHU_INVEST_APP_ID=cli_a94b502990f95cef
export FEISHU_INVEST_APP_SECRET=mMREyz9A7h5kVFJFRRfMwbWKGumF52g6
export FEISHU_DS_APP_ID=cli_a94ba9fabaf9dcbd
export FEISHU_DS_APP_SECRET=FZYbOlgeIpkcLSFXP7fkfdNIUoUWky6q
export DEEPSEEK_API_KEY=sk-714dfdeaddcf40cfbb8c16584c56cf9c

# ── conda Python 路径 ─────────────────────────────────────────────────────────
PYTHON="$HOME/miniconda3/envs/investment_bot/bin/python"

if [ ! -f "$PYTHON" ]; then
    echo "❌ 未找到 investment_bot conda 环境: $PYTHON"
    exit 1
fi

# ── 工具函数 ──────────────────────────────────────────────────────────────────
LOG_DIR="logs"
mkdir -p "$LOG_DIR"

pid_of() {
    # 用完整 python 路径精确匹配，避免误伤系统进程
    pgrep -f "${PYTHON}.*$1" 2>/dev/null | head -1
}

show_status() {
    echo "=== Agent Hub 进程状态 ==="
    local pid1; pid1=$(pid_of "main\.py" || true)
    local pid2; pid2=$(pid_of "scheduler_runner\.py" || true)
    [ -n "$pid1" ] && echo "  ✅ main.py (PID $pid1)" || echo "  ❌ main.py 未运行"
    [ -n "$pid2" ] && echo "  ✅ scheduler_runner.py (PID $pid2)" || echo "  ❌ scheduler_runner.py 未运行"
}

stop_all() {
    echo "[stop] 停止所有 Agent Hub 进程..."
    pkill -f "${PYTHON}.*main\.py" 2>/dev/null && echo "  stopped: main.py" || echo "  main.py 未运行"
    pkill -f "${PYTHON}.*scheduler_runner\.py" 2>/dev/null && echo "  stopped: scheduler_runner.py" || echo "  scheduler_runner.py 未运行"
    echo "[stop] 完成"
}

# ── 命令行参数处理 ─────────────────────────────────────────────────────────────
case "${1:-}" in
    --status)
        show_status
        exit 0
        ;;
    --stop)
        stop_all
        exit 0
        ;;
    --daemon)
        DAEMON=1
        ;;
    *)
        DAEMON=0
        ;;
esac

# ── 防止重复启动 ──────────────────────────────────────────────────────────────
EXISTING=$(pid_of "main\.py" || true)
if [ -n "$EXISTING" ]; then
    echo "⚠️  main.py 已在运行 (PID $EXISTING)，先执行 bash start.sh --stop 再重启"
    show_status
    exit 1
fi

# ── 启动 ──────────────────────────────────────────────────────────────────────
echo "[start.sh] Agent Hub 启动..."
echo "[start.sh] Python: $PYTHON"
echo ""

if [ "$DAEMON" -eq 1 ]; then
    # 后台模式
    nohup "$PYTHON" main.py \
        >> "$LOG_DIR/main.log" 2>&1 &
    echo "  ✅ main.py 后台启动 (PID $!)"

    sleep 2  # 等主进程稳定后再启动调度器

    nohup "$PYTHON" bots/daily_report/scheduler_runner.py \
        >> "$LOG_DIR/daily_report.log" 2>&1 &
    echo "  ✅ scheduler_runner.py 后台启动 (PID $!)"

    echo ""
    echo "[start.sh] 所有服务已在后台启动"
    echo "  日志: tail -f $LOG_DIR/main.log"
    echo "       tail -f $LOG_DIR/daily_report.log"
    echo "  状态: bash start.sh --status"
    echo "  停止: bash start.sh --stop"
else
    # 前台模式（调试用）：主进程前台运行，调度器后台运行
    echo "[start.sh] 前台模式：main.py 前台运行，调度器后台运行"
    nohup "$PYTHON" bots/daily_report/scheduler_runner.py \
        >> "$LOG_DIR/daily_report.log" 2>&1 &
    echo "  ✅ scheduler_runner.py 后台启动 (PID $!)"
    echo ""
    "$PYTHON" main.py
fi

