from typing import Dict, Any


def windows_filter(windows: Dict[str, Any]):
    return [w for w in windows if ''.join(w['cmdline']).find('kittens.runner') < 0]
