"""汇率插件配置：默认关闭，仅管理员 enable 后启用（测试）。"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_str(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass
class Config:
    """插件运行配置。"""

    # 默认关闭；FX_ENABLED=true 可强制启用（便于测试）
    enabled: bool = False
    # 请求超时（秒）与重试次数
    request_timeout: int = 15
    request_retries: int = 2
    # 状态与关注列表数据目录
    data_dir: str = "data"

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            enabled=_env_bool("FX_ENABLED"),
            request_timeout=_env_int("FX_REQUEST_TIMEOUT", 15),
            request_retries=_env_int("FX_REQUEST_RETRIES", 2),
            data_dir=(
                _env_str("FX_DATA_DIR")
                or _env_str("LOCALSTORE_DATA_DIR")
                or "data"
            ),
        )


config = Config.from_env()
