"""管理员权限：读取与 x_admin/galgame-box 共用的 admin_ids.json。"""

from __future__ import annotations

import json
from pathlib import Path

from .config import config


def is_admin(user_id: int) -> bool:
    try:
        payload = json.loads(
            (Path(config.data_dir) / "admin_ids.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return False
    admins = payload.get("admins") if isinstance(payload, dict) else None
    if isinstance(admins, list):
        return user_id in {int(item) for item in admins if str(item).strip().isdigit()}
    return False
