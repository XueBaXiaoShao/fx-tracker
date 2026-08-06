"""插件开关状态：默认关闭，仅管理员 enable 后启用（测试）。"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from .config import config

_lock = threading.Lock()


def _state_file() -> Path:
    return Path(config.data_dir) / "fx_state.json"


def is_enabled() -> bool:
    """读取开关状态；没有状态文件时按 FX_ENABLED 环境变量（默认关闭）。"""
    try:
        payload = json.loads(_state_file().read_text(encoding="utf-8"))
        if isinstance(payload, dict) and "enabled" in payload:
            return bool(payload["enabled"])
    except (OSError, json.JSONDecodeError):
        pass
    return config.enabled


def set_enabled(enabled: bool) -> None:
    path = _state_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps({"version": 1, "enabled": enabled}, ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
