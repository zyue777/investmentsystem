"""
本地 Claude 转发服务。
云端 Bot 把 AI 请求 POST 到此服务，由本地 claude CLI 执行后返回结果。
"""
import subprocess
import os
import sys
import requests as _requests
from pathlib import Path
from flask import Flask, request, jsonify

# 把 investment_system 加入路径，供 feishu 工具调用
_ROOT = str(Path(__file__).parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

app = Flask(__name__)
PORT = 5001
SECRET = os.environ.get("CLAUDE_RELAY_SECRET", "invest-relay-2026")


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/call", methods=["POST"])
def call_claude():
    data = request.get_json(force=True)

    # 简单鉴权
    if data.get("secret") != SECRET:
        return jsonify({"error": "unauthorized"}), 401

    prompt = data.get("prompt", "")
    timeout = int(data.get("timeout", 300))

    if not prompt:
        return jsonify({"error": "prompt is empty"}), 400

    try:
        env = os.environ.copy()
        env["IS_SANDBOX"] = "1"
        proc = subprocess.run(
            ["claude", "--print", "--dangerously-skip-permissions", prompt],
            capture_output=True, text=True, timeout=timeout,
            stdin=subprocess.DEVNULL, env=env
        )
        output = proc.stdout.strip()
        if not output and proc.stderr.strip():
            output = proc.stderr.strip()
        if not output:
            output = "（无输出）"
        return jsonify({"result": output})
    except subprocess.TimeoutExpired:
        return jsonify({"error": f"超时（{timeout}s）"}), 504
    except FileNotFoundError:
        return jsonify({"error": "❌ 未找到 claude 命令"}), 500
    except Exception as e:
        return jsonify({"error": f"❌ 异常: {e}"}), 500


def send_feishu_notify(relay_url: str):
    """向飞书发送 Claude Bot 上线通知（本地+云端全链路畅通的证明）。"""
    from dotenv import load_dotenv
    load_dotenv(Path(_ROOT) / '.env', override=True)
    app_id = os.environ.get("FEISHU_INVEST_APP_ID", "")
    app_secret = os.environ.get("FEISHU_INVEST_APP_SECRET", "")
    notify_users = ["ou_2525697c11679de48ab0d976267c0652"]

    if not app_id or not app_secret:
        print("[relay] ⚠️ 未找到飞书 App 凭证，跳过通知")
        return

    try:
        from tools.feishu_token import get_token
        from tools.feishu_message import send_text
        token = get_token(app_id, app_secret)
        if not token:
            print("[relay] ⚠️ 飞书 token 获取失败，跳过通知")
            return

        msg = (
            "🤖 投研Bot 已上线\n"
            "━━━━━━━━━━━━━━━━━\n"
            "📋 指令速查：\n"
            "• 研究 [主题] → 进入研究模式\n"
            "• 请联网研究 [主题] → 联网研究模式\n"
            "  ┗ 归档 → 保存为情报卡\n"
            "  ┗ clear → 清空退出\n"
            "• 录 [内容] → 录入情报\n"
            "• 问/析/比 → 知识库问答\n"
            "• 请联网回答 [问题] → 联网问答\n"
            "• 发送URL → 自动抓取入库\n"
            "• 发送文件 → 自动蒸馏入库\n"
            "• s → 系统状态"
        )
        for uid in notify_users:
            send_text(token, uid, msg)
        print("[relay] ✅ 飞书上线通知已发送")
    except Exception as e:
        print(f"[relay] ⚠️ 飞书通知发送失败: {e}")


if __name__ == "__main__":
    print(f"[relay] Claude 转发服务启动，端口 {PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
