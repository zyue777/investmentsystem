"""通用注册表，支持自动发现。"""
import importlib, pkgutil
from pathlib import Path
from typing import Any, Callable, Optional


class Registry:
    def __init__(self, name: str):
        self.name = name
        self._items: dict[str, dict] = {}

    def discover(self, package_path: str, package_name: str):
        pkg_dir = Path(package_path)
        if not pkg_dir.exists():
            return
        for info in pkgutil.iter_modules([str(pkg_dir)]):
            if info.name.startswith('_'):
                continue
            try:
                mod = importlib.import_module(f"{package_name}.{info.name}")
                manifest = getattr(mod, 'MANIFEST', None)
                handler = (getattr(mod, 'handle', None)
                          or getattr(mod, 'create_channel', None)
                          or getattr(mod, 'create_provider', None))
                if manifest:
                    self._items[manifest.name] = {
                        'manifest': manifest, 'handler': handler, 'module': mod}
            except Exception as e:
                print(f"[{self.name}] 跳过 {info.name}: {e}")
        print(f"[{self.name}] 已注册 {len(self._items)} 项")

    def get(self, name: str) -> Optional[dict]:
        return self._items.get(name)

    def get_handler(self, name: str) -> Optional[Callable]:
        item = self._items.get(name)
        return item['handler'] if item else None

    def get_instance(self, name: str) -> Any:
        handler = self.get_handler(name)
        return handler() if handler and callable(handler) else None

    def match_by_trigger(self, text: str) -> list[dict]:
        matches = []
        text_lower = text.lower()
        for name, item in self._items.items():
            for trigger in getattr(item['manifest'], 'triggers', []):
                tl = trigger.lower()
                # 匹配条件：文本完全等于或以触发词开头
                # 触发词自带格式约定：
                #   - 末尾带空格的（如 "录 "）→ startswith("录 ") 天然需要空格分隔
                #   - 末尾无空格的（如 "请联网研究"）→ startswith 直接前缀匹配
                #   - 完整词的（如 "s", "kk"）→ == 精确匹配
                if text_lower == tl or text_lower.startswith(tl):
                    matches.append({'name': name, 'manifest': item['manifest'],
                                    'handler': item['handler'], 'trigger': trigger})
                    break
        matches.sort(key=lambda m: getattr(m['manifest'], 'priority', 100))
        return matches

    def all_items(self) -> list[dict]:
        return list(self._items.values())

    def count(self) -> int:
        return len(self._items)

    def to_ai_index(self) -> str:
        lines = []
        for item in self._items.values():
            m = item['manifest']
            triggers = ', '.join(getattr(m, 'triggers', [])[:3])
            lines.append(f"- {m.name}: {m.description}" + (f" [触发:{triggers}]" if triggers else ""))
        return '\n'.join(lines)
