"""五层路由器：pending-confirm → Session拦截 → 精确触发词 → Phase触发词 → AI fallback。
📝 文档引用：CLAUDE.md「消息路由速查」/ docs/00_架构总览.md「消息流转路径」
⚠️ 修改本文件后，必须同步更新上述两处文档。
"""
import re
from core.context import Context, ContextStatus

# ok/确认/改.../cancel 都属于流程控制指令，由 pending_store 判断归属
_CONFIRM_RE = re.compile(r'^(ok|确认|cancel|取消|改\s+.+)$', re.IGNORECASE)
# 有 pending 记录时，这些 skill 拥有 confirm 处理权（ingest_file 已改为直接入库，无需在此注册）
_PENDING_SKILLS = ['ingest_record']


class Router:
    def __init__(self, skill_registry, phase_configs: dict, pending_store=None):
        self._skill_reg = skill_registry
        self._phase_configs = phase_configs
        self._pending_store = pending_store  # 用于 pending-confirm 优先路由
        self._url_re = re.compile(r'https?://\S+')

    def route(self, ctx: Context) -> Context:
        text = ctx.raw_text.strip()

        # ── 第0层：pending-confirm 优先路由 ─────────────────────────────────
        # 当用户发送 ok/确认/改.../cancel 且 pending_store 有记录时，
        # 直接路由回拥有 pending 的 skill，避免进入 AI fallback 产生幻觉。
        if _CONFIRM_RE.match(text) and self._pending_store:
            pending = self._pending_store.get(ctx.user_id)
            if pending:
                # pending 里存有发起 skill 名称（由各 skill 写入时设置），直接路由回去
                skill_name = pending.get('_skill', '')
                if not skill_name:
                    # 兜底：遍历已知 pending skill
                    skill_name = _PENDING_SKILLS[0]
                ctx.matched_skill = skill_name
                ctx.match_confidence = 1.0
                ctx.status = ContextStatus.ROUTED
                return ctx

        # ── 第0.5层：Session 模式拦截 ──────────────────────────────────────
        # 如果用户有活跃 Session（研究模式等），所有消息路由到 session 对应的 skill。
        # 退出指令（归档/clear/jj）也路由到同一 skill，由它内部处理退出流程。
        # 注意：「研究 xxx」开启指令会穿过此层（无 session 时不拦截），
        #       由下方第1层 Skill 触发词匹配到 research_session。
        try:
            from tools.session_memory import get_active_session
            session = get_active_session(ctx.user_id)
            if session:
                ctx.matched_skill = session['target_skill']
                ctx.parsed_args = {
                    'session_action': 'continue',
                    'topic': session.get('topic', ''),
                }
                ctx.match_confidence = 1.0
                ctx.status = ContextStatus.ROUTED
                return ctx
        except ImportError:
            pass  # session_memory 模块不存在时降级（可拔插）

        # URL 投喂检测
        url_m = self._url_re.search(text)
        if url_m and text.strip() == url_m.group(0):
            ctx.matched_skill = 'ingest_url'
            ctx.parsed_args = {'url': url_m.group(0)}
            ctx.match_confidence = 1.0
            ctx.status = ContextStatus.ROUTED
            return ctx

        # 第1层：Skill 触发词
        matches = self._skill_reg.match_by_trigger(text)
        if matches:
            best = matches[0]
            ctx.matched_skill = best['name']
            ctx.match_confidence = 1.0
            remainder = text[len(best['trigger']):].strip()
            ctx.parsed_args = {'content': remainder} if remainder else {}
            ctx.status = ContextStatus.ROUTED
            return ctx

        # 第2层：Phase 触发词
        for key, cfg in self._phase_configs.items():
            for trigger in cfg.get('triggers', []):
                tl = trigger.lower()
                if text.lower() == tl or text.lower().startswith(tl + ' '):
                    ctx.matched_skill = 'phase_execute'
                    ctx.phase_key = cfg['key']
                    ctx.parsed_args = {'phase_key': cfg['key'],
                                       'extra': text[len(trigger):].strip()}
                    ctx.match_confidence = 1.0
                    ctx.status = ContextStatus.ROUTED
                    return ctx

        # 第2.5层：长文本会议纪要自动检测
        # 用户直接粘贴会议纪要/调研记录时，无需手动加"录 "前缀，自动路由到 ingest_record
        _NOTE_KEYWORDS = {'会议纪要', '纪要', '调研', '专家会议', '草根调研', '路演', '会议要点', '电话会', '专家电话'}
        if len(text) > 300 and any(kw in text for kw in _NOTE_KEYWORDS):
            ctx.matched_skill = 'ingest_record'
            ctx.parsed_args = {'content': text}
            ctx.match_confidence = 0.9
            ctx.status = ContextStatus.ROUTED
            return ctx

        # 第3层：AI fallback（消耗 token）
        ai_result = self._ai_match(text, ctx)
        if ai_result:
            ctx.matched_skill = ai_result
            ctx.match_confidence = 0.7
            ctx.status = ContextStatus.ROUTED
            return ctx

        # Fallback → 通用问答
        ctx.matched_skill = 'kb_query'
        ctx.match_confidence = 0.5
        ctx.parsed_args = {'question': text}
        ctx.status = ContextStatus.ROUTED
        return ctx

    def _ai_match(self, text, ctx):
        index = self._skill_reg.to_ai_index()
        if not index:
            return None
        from core.executor import get_ai_provider
        provider = get_ai_provider(ctx)
        if not provider:
            return None
        prompt = ("意图分类器。只输出JSON: {\"skill\":\"名称或null\"}\n"
                  f"可用技能:\n{index}\n\n用户消息: {text[:300]}")
        try:
            import json
            result = provider.call(prompt, timeout=30, cwd=ctx.workspace)
            return json.loads(result).get('skill')
        except: return None
