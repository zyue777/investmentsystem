"""三层路由器：精确触发词 → Phase触发词 → AI fallback。"""
import re
from core.context import Context, ContextStatus


class Router:
    def __init__(self, skill_registry, phase_configs: dict):
        self._skill_reg = skill_registry
        self._phase_configs = phase_configs
        self._url_re = re.compile(r'https?://\S+')

    def route(self, ctx: Context) -> Context:
        text = ctx.raw_text.strip()

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
