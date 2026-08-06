"""命令入口测试：默认关闭、管理员开启、增删查。"""

from __future__ import annotations

import json

from nonebot.adapters.onebot.v11 import Message

from fx_tracker import commands, rates, state, watchlist


class _FakeEvent:
    def __init__(self, user_id: int) -> None:
        self.user_id = user_id

    def get_plaintext(self) -> str:
        return "/shou fx"


class _FakeMatcher:
    def __init__(self) -> None:
        self.sent: list = []

    async def send(self, message) -> None:
        self.sent.append(message)

    async def finish(self, message=None) -> None:
        if message is not None:
            self.sent.append(message)
        raise _Stop()


class _Stop(Exception):
    pass


async def _run(coro) -> None:
    try:
        await coro
    except _Stop:
        pass


def _write_admin(tmp_path, user_id: int) -> None:
    (tmp_path / "admin_ids.json").write_text(
        json.dumps({"version": 2, "admins": [user_id]}), encoding="utf-8"
    )


def test_is_fx_event_rule() -> None:
    class Ev:
        def __init__(self, text: str) -> None:
            self._text = text

        def get_plaintext(self) -> str:
            return self._text

    assert commands._is_fx_event(Ev("/shou fx price btc")) is True
    assert commands._is_fx_event(Ev("/shou gal")) is False
    assert commands._is_fx_event(Ev("/shou list")) is False


async def test_disabled_blocks_usage(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(state.config, "data_dir", str(tmp_path))
    monkeypatch.setattr(state.config, "enabled", False)

    matcher = _FakeMatcher()
    await _run(commands.handle_fx(_FakeEvent(1), matcher, Message("price btc")))

    assert "未启用" in str(matcher.sent[-1])


async def test_enable_requires_admin(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(state.config, "data_dir", str(tmp_path))
    _write_admin(tmp_path, 999)

    matcher = _FakeMatcher()
    await _run(commands.handle_fx(_FakeEvent(100), matcher, Message("enable")))

    assert "只有管理员" in str(matcher.sent[-1])
    assert state.is_enabled() is False


async def test_admin_enable_then_usage(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(state.config, "data_dir", str(tmp_path))
    monkeypatch.setattr(watchlist.config, "data_dir", str(tmp_path))
    _write_admin(tmp_path, 999)

    matcher = _FakeMatcher()
    await _run(commands.handle_fx(_FakeEvent(999), matcher, Message("enable")))
    assert "已开启" in str(matcher.sent[-1])
    assert state.is_enabled() is True

    await _run(commands.handle_fx(_FakeEvent(1), matcher, Message("add btc-usd")))
    assert watchlist.list_pairs(1) == [("BTC", "USD")]


async def test_price_uses_rates(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(state.config, "data_dir", str(tmp_path))
    state.set_enabled(True)

    async def fake_fetch(base, quote):
        return 7.1234

    monkeypatch.setattr(rates, "fetch_rate", fake_fetch)
    matcher = _FakeMatcher()
    await _run(commands.handle_fx(_FakeEvent(1), matcher, Message("price usd cny")))

    assert "1 USD = 7.1234 CNY" in str(matcher.sent[-1])
