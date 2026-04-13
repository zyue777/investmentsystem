"""全局配置加载。"""
import yaml
from pathlib import Path


def load_global_config(config_dir: Path = None) -> dict:
    """加载 config/global.yaml，返回配置字典。"""
    if config_dir is None:
        config_dir = Path(__file__).parent
    config_file = config_dir / 'global.yaml'
    if not config_file.exists():
        return {}
    with open(config_file, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}
