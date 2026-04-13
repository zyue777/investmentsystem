#!/bin/bash
# Agent Hub 统一启动脚本
# 用法: bash start.sh (前台) 或 nohup bash start.sh &

cd "$(dirname "$0")"

# ── 环境变量 ──
export FEISHU_INVEST_APP_ID=cli_a94b502990f95cef
export FEISHU_INVEST_APP_SECRET=mMREyz9A7h5kVFJFRRfMwbWKGumF52g6
export FEISHU_DS_APP_ID=cli_a94ba9fabaf9dcbd
export FEISHU_DS_APP_SECRET=FZYbOlgeIpkcLSFXP7fkfdNIUoUWky6q
export DEEPSEEK_API_KEY=sk-714dfdeaddcf40cfbb8c16584c56cf9c

# ── 激活 conda ──
eval "$($HOME/miniconda3/bin/conda shell.bash hook)"
conda activate investment_bot

echo "[start.sh] 启动 Agent Hub..."
python main.py
