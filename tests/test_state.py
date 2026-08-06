"""插件开关状态测试：默认关闭。"""

from __future__ import annotations

from fx_tracker import state


def test_disabled_by_default(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(state.config, "data_dir", str(tmp_path))
    monkeypatch.setattr(state.config, "enabled", False)

    assert state.is_enabled() is False


def test_enable_persists(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(state.config, "data_dir", str(tmp_path))
    monkeypatch.setattr(state.config, "enabled", False)

    state.set_enabled(True)
    assert state.is_enabled() is True

    state.set_enabled(False)
    assert state.is_enabled() is False
