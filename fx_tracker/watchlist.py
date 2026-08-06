"""个人汇率关注列表。"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from .config import config

_lock = threading.Lock()


def _watch_file() -> Path:
    return Path(config.data_dir) / "fx_watchlist.json"


def _load() -> dict:
    try:
        payload = json.loads(_watch_file().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _save(payload: dict) -> None:
    path = _watch_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def list_pairs(user_id: int) -> list[tuple[str, str]]:
    payload = _load()
    users = payload.get("users", {})
    pairs = users.get(str(user_id), [])
    if not isinstance(pairs, list):
        return []
    result: list[tuple[str, str]] = []
    for pair in pairs:
        if isinstance(pair, list) and len(pair) == 2:
            result.append((str(pair[0]).upper(), str(pair[1]).upper()))
    return result


def add_pair(user_id: int, base: str, quote: str) -> bool:
    """添加关注；已存在返回 False。"""
    base, quote = base.upper(), quote.upper()
    with _lock:
        payload = _load()
        users = payload.setdefault("users", {})
        pairs = users.setdefault(str(user_id), [])
        if [base, quote] in pairs:
            return False
        pairs.append([base, quote])
        _save(payload)
        return True


def remove_pair(user_id: int, base: str, quote: str) -> bool:
    base, quote = base.upper(), quote.upper()
    with _lock:
        payload = _load()
        users = payload.get("users", {})
        pairs = users.get(str(user_id), [])
        if [base, quote] not in pairs:
            return False
        pairs.remove([base, quote])
        _save(payload)
        return True
