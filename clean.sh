#!/bin/bash
# Agent Hub 一键清理脚本
# 清理内容：
#   1. Python __pycache__（字节码缓存）
#   2. logs/*.pid（进程ID残留文件）
#   3. executions.jsonl（调度执行历史，可选）
#   4. logs/*.log（运行日志，可选，默认仅清空而非删除）
#   5. sentiment_monitor/data/ 双空条目（无公告+无讨论，可选）
#
# 用法:
#   bash clean.sh              # 默认清理（缓存 + PID，保留日志和执行历史）
#   bash clean.sh --all        # 完整清理（同上 + 清空日志 + 清空执行历史 + 删除双空日记）
#   bash clean.sh --logs       # 同上 + 清空日志文件（不删除，保留文件本身）
#   bash clean.sh --executions # 同上 + 清空执行历史（executions.jsonl）
#   bash clean.sh --diary      # 同上 + 删除自选股日志中的双空条目
#   bash clean.sh --dry-run    # 预览模式（只显示会删除什么，不实际操作）

set -e
cd "$(dirname "$0")"

# ── 颜色定义 ──────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# ── 参数解析 ──────────────────────────────────────────────────────────────────
CLEAN_ALL=0
CLEAN_LOGS=0
CLEAN_EXECUTIONS=0
CLEAN_DIARY=0
DRY_RUN=0

for arg in "$@"; do
    case "$arg" in
        --all)        CLEAN_ALL=1; CLEAN_LOGS=1; CLEAN_EXECUTIONS=1; CLEAN_DIARY=1 ;;
        --logs)       CLEAN_LOGS=1 ;;
        --executions) CLEAN_EXECUTIONS=1 ;;
        --diary)      CLEAN_DIARY=1 ;;
        --dry-run)    DRY_RUN=1 ;;
        --help|-h)
            sed -n '2,16p' "$0" | sed 's/^# //'
            exit 0
            ;;
        *)
            echo "未知参数: $arg，使用 --help 查看用法"
            exit 1
            ;;
    esac
done

# ── 工具函数 ──────────────────────────────────────────────────────────────────
TOTAL_FREED=0

human_size() {
    # 将字节数转为可读格式
    local bytes="$1"
    if [ "$bytes" -ge 1048576 ]; then
        echo "$(( bytes / 1048576 )) MB"
    elif [ "$bytes" -ge 1024 ]; then
        echo "$(( bytes / 1024 )) KB"
    else
        echo "${bytes} B"
    fi
}

dir_size() {
    # 计算目录总大小（字节），目录不存在返回 0
    local path="$1"
    if [ -d "$path" ]; then
        du -sb "$path" 2>/dev/null | awk '{print $1}' || echo 0
    else
        echo 0
    fi
}

file_size() {
    local path="$1"
    if [ -f "$path" ]; then
        stat -c%s "$path" 2>/dev/null || echo 0
    else
        echo 0
    fi
}

do_action() {
    # do_action <描述> <预计释放字节数> <命令...>
    local desc="$1"
    local size="$2"
    shift 2
    if [ "$DRY_RUN" -eq 1 ]; then
        echo -e "  ${YELLOW}[dry-run]${NC} $desc $([ "$size" -gt 0 ] && echo "($(human_size "$size"))" || true)"
    else
        "$@"
        TOTAL_FREED=$(( TOTAL_FREED + size ))
        echo -e "  ${GREEN}✓${NC} $desc $([ "$size" -gt 0 ] && echo "(释放 $(human_size "$size"))" || true)"
    fi
}

# ── 开始清理 ──────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}   Agent Hub 缓存清理工具${NC}"
[ "$DRY_RUN" -eq 1 ] && echo -e "${YELLOW}   [预览模式，不会实际修改任何文件]${NC}"
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# ── 1. Python __pycache__ ─────────────────────────────────────────────────────
echo -e "${CYAN}[1/5] Python 字节码缓存 (__pycache__)${NC}"

PYCACHE_DIRS=$(find . -type d -name "__pycache__" 2>/dev/null | sort)
PYCACHE_COUNT=$(echo "$PYCACHE_DIRS" | grep -c . || true)
PYCACHE_SIZE=0

while IFS= read -r d; do
    [ -z "$d" ] && continue
    s=$(dir_size "$d")
    PYCACHE_SIZE=$(( PYCACHE_SIZE + s ))
done <<< "$PYCACHE_DIRS"

if [ "$PYCACHE_COUNT" -eq 0 ]; then
    echo -e "  ${GREEN}✓${NC} 无 __pycache__ 目录，跳过"
else
    if [ "$DRY_RUN" -eq 1 ]; then
        echo "$PYCACHE_DIRS" | while IFS= read -r d; do
            [ -z "$d" ] && continue
            s=$(dir_size "$d")
            echo -e "  ${YELLOW}[dry-run]${NC} 删除 $d ($(human_size "$s"))"
        done
        echo -e "  ${YELLOW}共 $PYCACHE_COUNT 个目录，合计 $(human_size "$PYCACHE_SIZE")${NC}"
    else
        echo "$PYCACHE_DIRS" | xargs rm -rf
        TOTAL_FREED=$(( TOTAL_FREED + PYCACHE_SIZE ))
        echo -e "  ${GREEN}✓${NC} 已删除 $PYCACHE_COUNT 个 __pycache__ 目录（释放 $(human_size "$PYCACHE_SIZE")）"
    fi
fi
echo ""

# ── 2. PID 残留文件 ───────────────────────────────────────────────────────────
echo -e "${CYAN}[2/5] PID 残留文件 (logs/*.pid)${NC}"

PID_FILES=$(find logs/ -maxdepth 1 -name "*.pid" 2>/dev/null | sort)
PID_COUNT=$(echo "$PID_FILES" | grep -c . || true)
PID_SIZE=0

if [ "$PID_COUNT" -eq 0 ]; then
    echo -e "  ${GREEN}✓${NC} 无残留 PID 文件，跳过"
else
    while IFS= read -r f; do
        [ -z "$f" ] && continue
        s=$(file_size "$f")
        PID_SIZE=$(( PID_SIZE + s ))
    done <<< "$PID_FILES"

    if [ "$DRY_RUN" -eq 1 ]; then
        echo "$PID_FILES" | while IFS= read -r f; do
            [ -z "$f" ] && continue
            echo -e "  ${YELLOW}[dry-run]${NC} 删除 $f"
        done
    else
        echo "$PID_FILES" | xargs rm -f
        TOTAL_FREED=$(( TOTAL_FREED + PID_SIZE ))
        echo -e "  ${GREEN}✓${NC} 已删除 $PID_COUNT 个 PID 文件"
    fi
fi
echo ""

# ── 3. 执行历史 (executions.jsonl) ───────────────────────────────────────────
echo -e "${CYAN}[3/5] 调度执行历史 (executions.jsonl)${NC}"

EXEC_FILES=(
    "bots/daily_report/executions.jsonl"
    "bots/investment/memory/store/executions.jsonl"
    "bots/investment_ds/memory/store/executions.jsonl"
)

if [ "$CLEAN_EXECUTIONS" -eq 1 ]; then
    for f in "${EXEC_FILES[@]}"; do
        if [ -f "$f" ]; then
            s=$(file_size "$f")
            lines=$(wc -l < "$f" 2>/dev/null || echo 0)
            do_action "清空 $f（${lines} 条记录）" "$s" truncate -s 0 "$f"
        else
            echo -e "  ${GREEN}✓${NC} $f 不存在，跳过"
        fi
    done
else
    for f in "${EXEC_FILES[@]}"; do
        if [ -f "$f" ]; then
            s=$(file_size "$f")
            lines=$(wc -l < "$f" 2>/dev/null || echo 0)
            echo -e "  ${YELLOW}⏭${NC}  跳过 $f（${lines} 条记录，$(human_size "$s")，使用 --executions 或 --all 清空）"
        fi
    done
fi
echo ""

# ── 4. 日志文件 (logs/*.log) ──────────────────────────────────────────────────
echo -e "${CYAN}[4/5] 运行日志 (logs/*.log)${NC}"

LOG_FILES=$(find logs/ -maxdepth 1 -name "*.log" 2>/dev/null | sort)
LOG_COUNT=$(echo "$LOG_FILES" | grep -c . || true)
LOG_SIZE=0

while IFS= read -r f; do
    [ -z "$f" ] && continue
    s=$(file_size "$f")
    LOG_SIZE=$(( LOG_SIZE + s ))
done <<< "$LOG_FILES"

if [ "$CLEAN_LOGS" -eq 1 ] && [ "$LOG_COUNT" -gt 0 ]; then
    if [ "$DRY_RUN" -eq 1 ]; then
        echo "$LOG_FILES" | while IFS= read -r f; do
            [ -z "$f" ] && continue
            s=$(file_size "$f")
            echo -e "  ${YELLOW}[dry-run]${NC} 清空 $f ($(human_size "$s"))"
        done
        echo -e "  ${YELLOW}共 $LOG_COUNT 个日志，合计 $(human_size "$LOG_SIZE")${NC}"
    else
        echo "$LOG_FILES" | xargs truncate -s 0
        TOTAL_FREED=$(( TOTAL_FREED + LOG_SIZE ))
        echo -e "  ${GREEN}✓${NC} 已清空 $LOG_COUNT 个日志文件（释放 $(human_size "$LOG_SIZE")）"
        echo -e "  ${GREEN}ℹ${NC}  文件保留，仅内容清空（进程不断）"
    fi
elif [ "$LOG_COUNT" -gt 0 ]; then
    echo -e "  ${YELLOW}⏭${NC}  跳过日志文件（合计 $(human_size "$LOG_SIZE")，使用 --logs 或 --all 清空）"
else
    echo -e "  ${GREEN}✓${NC} 无日志文件，跳过"
fi
echo ""

# ── 5. 自选股日志双空条目 ────────────────────────────────────────────────────
echo -e "${CYAN}[5/5] 自选股日志双空条目 (sentiment_monitor/data/)${NC}"

# 双空条目匹配模式：## 日期 + 无重大公告 + 暂无 + ---
# Python 脚本内联处理（bash 难以可靠地多行匹配）
DIARY_DIR="sentiment_monitor/data"
PYTHON="$HOME/miniconda3/envs/investment_bot/bin/python"

if [ "$CLEAN_DIARY" -eq 1 ]; then
    if [ ! -d "$DIARY_DIR" ]; then
        echo -e "  ${GREEN}✓${NC} 目录不存在，跳过"
    else
        DIARY_PY=""
read -r -d '' DIARY_PY << 'PYEOF' || true
import os, re, sys

EMPTY_ANN  = {'[无重大公告]', '无重大公告', '无', '暂无', 'N/A', 'n/a', ''}
EMPTY_SENT = {'暂无', '暂无。', '无', '无。', 'N/A', 'n/a', ''}

dry_run = '--dry-run' in sys.argv
data_dir = sys.argv[1]

# 匹配一个日记块：## YYYY-MM-DD ... ---
BLOCK_RE = re.compile(
    r'(## \d{4}-\d{2}-\d{2}\n\n'
    r'\*\*重大公告：\*\*\n(.+?)\n\n'
    r'\*\*社区讨论要点：\*\*\n(.+?)\n\n'
    r'---\n\n)',
    re.DOTALL
)

total_removed = 0

for root, dirs, files in os.walk(data_dir):
    for fname in files:
        if not fname.endswith('.md'):
            continue
        fpath = os.path.join(root, fname)
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()

        removed = []
        def replace_block(m):
            ann  = m.group(2).strip()
            sent = m.group(3).strip()
            if ann in EMPTY_ANN and sent in EMPTY_SENT:
                removed.append(m.group(1)[:30].replace('\n', ' '))
                return ''
            return m.group(0)

        new_content = BLOCK_RE.sub(replace_block, content)

        if removed:
            rel = os.path.relpath(fpath, data_dir)
            if dry_run:
                for r in removed:
                    print(f'[dry-run] {rel}: 删除双空条目 {r}...')
            else:
                with open(fpath, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                print(f'✓ {rel}: 删除 {len(removed)} 个双空条目')
            total_removed += len(removed)

if total_removed == 0:
    print('✓ 无双空条目，跳过')
elif not dry_run:
    print(f'共删除 {total_removed} 个双空条目')
PYEOF

        if [ "$DRY_RUN" -eq 1 ]; then
            "$PYTHON" -c "$DIARY_PY" "$DIARY_DIR" --dry-run 2>/dev/null | while IFS= read -r line; do
                echo -e "  ${YELLOW}$line${NC}"
            done
        else
            "$PYTHON" -c "$DIARY_PY" "$DIARY_DIR" 2>/dev/null | while IFS= read -r line; do
                echo -e "  ${GREEN}$line${NC}"
            done
        fi
    fi
else
    # 统计现有双空条目数量供参考
    if [ -d "$DIARY_DIR" ] && command -v "$PYTHON" &>/dev/null; then
        COUNT=$("$PYTHON" -c "
import os, re
EMPTY_ANN  = {'[无重大公告]', '无重大公告', '无', '暂无', 'N/A', 'n/a', ''}
EMPTY_SENT = {'暂无', '暂无。', '无', '无。', 'N/A', 'n/a', ''}
BLOCK_RE = re.compile(r'## \\d{4}-\\d{2}-\\d{2}\\n\\n\\*\\*重大公告：\\*\\*\\n(.+?)\\n\\n\\*\\*社区讨论要点：\\*\\*\\n(.+?)\\n\\n---\\n\\n', re.DOTALL)
n = 0
for root, dirs, files in os.walk('$DIARY_DIR'):
    for f in files:
        if not f.endswith('.md'): continue
        txt = open(os.path.join(root,f),encoding='utf-8').read()
        for m in BLOCK_RE.finditer(txt):
            if m.group(1).strip() in EMPTY_ANN and m.group(2).strip() in EMPTY_SENT: n+=1
print(n)
" 2>/dev/null || echo 0)
        if [ "$COUNT" -gt 0 ]; then
            echo -e "  ${YELLOW}⏭${NC}  跳过（发现 ${COUNT} 个双空条目，使用 --diary 或 --all 清理）"
        else
            echo -e "  ${GREEN}✓${NC} 无双空条目"
        fi
    else
        echo -e "  ${YELLOW}⏭${NC}  跳过（使用 --diary 或 --all 清理）"
    fi
fi
echo ""

# ── 结果摘要 ──────────────────────────────────────────────────────────────────
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
if [ "$DRY_RUN" -eq 1 ]; then
    echo -e "${YELLOW}   预览完成。运行时去掉 --dry-run 执行实际清理。${NC}"
else
    echo -e "${GREEN}${BOLD}   清理完成！共释放约 $(human_size "$TOTAL_FREED")${NC}"
    echo ""
    echo -e "   提示："
    echo -e "   • 清理后首次启动 Python 会重建 __pycache__，属正常现象"
    echo -e "   • 日志文件已清空但未删除，进程继续写入不受影响"
    echo -e "   • 如需完整清理，使用: ${BOLD}bash clean.sh --all${NC}"
fi
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
