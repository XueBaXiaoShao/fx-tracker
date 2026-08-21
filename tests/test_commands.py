"""命令入口测试：默认关闭、管理员开启、增删查。"""

from __future__ import annotations

import json

import pytest
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
    await _run(commands.handle_fx(_FakeEvent(1), matcher, Message("fx price btc")))

    assert "未启用" in str(matcher.sent[-1])


async def test_enable_requires_admin(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(state.config, "data_dir", str(tmp_path))
    _write_admin(tmp_path, 999)

    matcher = _FakeMatcher()
    await _run(commands.handle_fx(_FakeEvent(100), matcher, Message("fx enable")))

    assert "只有管理员" in str(matcher.sent[-1])
    assert state.is_enabled() is False


async def test_admin_enable_then_usage(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(state.config, "data_dir", str(tmp_path))
    monkeypatch.setattr(watchlist.config, "data_dir", str(tmp_path))
    _write_admin(tmp_path, 999)

    matcher = _FakeMatcher()
    await _run(commands.handle_fx(_FakeEvent(999), matcher, Message("fx enable")))
    assert "已开启" in str(matcher.sent[-1])
    assert state.is_enabled() is True

    await _run(commands.handle_fx(_FakeEvent(1), matcher, Message("fx add btc-usd")))
    assert watchlist.list_pairs(1) == [("BTC", "USD")]


async def test_price_uses_rates(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(state.config, "data_dir", str(tmp_path))
    state.set_enabled(True)

    async def fake_fetch(base, quote):
        return 7.1234

    monkeypatch.setattr(rates, "fetch_rate", fake_fetch)
    matcher = _FakeMatcher()
    await _run(commands.handle_fx(_FakeEvent(1), matcher, Message("fx price usd cny")))

    assert "1 USD = 7.1234 CNY" in str(matcher.sent[-1])


async def test_group_switch_disables_fx(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(state.config, "data_dir", str(tmp_path))
    state.set_enabled(True)
    (tmp_path / "plugin_switches.json").write_text(
        json.dumps(
            {
                "version": 1,
                "defaults": {},
                "groups": {"912875556": {"fx_tracker": False}},
            }
        ),
        encoding="utf-8",
    )

    class GroupEvent(_FakeEvent):
        def __init__(self, user_id: int, group_id: int) -> None:
            super().__init__(user_id)
            self.group_id = group_id

    matcher = _FakeMatcher()
    await _run(
        commands.handle_fx(
            GroupEvent(1, 912875556), matcher, Message("fx price btc")
        )
    )

    assert "该群已禁用汇率功能" in str(matcher.sent[-1])


async def test_fx_prefix_stripped_before_dispatch(monkeypatch, tmp_path) -> None:
    """真实 CommandArg 带 fx 前缀（如 fx price JPY/CNY），不能落入帮助。"""
    monkeypatch.setattr(state.config, "data_dir", str(tmp_path))
    state.set_enabled(True)

    async def fake_fetch(base, quote):
        return 0.04283

    monkeypatch.setattr(rates, "fetch_rate", fake_fetch)
    matcher = _FakeMatcher()
    await _run(
        commands.handle_fx(_FakeEvent(1), matcher, Message("fx price JPY/CNY"))
    )

    assert "1 JPY = 0.042830 CNY" in str(matcher.sent[-1])


async def test_calc_direct_conversion(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(state.config, "data_dir", str(tmp_path))
    state.set_enabled(True)

    async def fake_fetch(base, quote):
        return 7.1234

    monkeypatch.setattr(rates, "fetch_rate", fake_fetch)
    matcher = _FakeMatcher()
    await _run(commands.handle_fx(_FakeEvent(1), matcher, Message("fx calc 100 usd")))

    assert "100 USD = 712.34 CNY" in str(matcher.sent[-1])


async def test_calc_compact_amount(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(state.config, "data_dir", str(tmp_path))
    state.set_enabled(True)

    async def fake_fetch(base, quote):
        return 60000.0

    monkeypatch.setattr(rates, "fetch_rate", fake_fetch)
    matcher = _FakeMatcher()
    await _run(commands.handle_fx(_FakeEvent(1), matcher, Message("fx calc 0.5btc")))

    assert "0.5 BTC = 30,000.00 CNY" in str(matcher.sent[-1])


async def test_calc_convert_alias(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(state.config, "data_dir", str(tmp_path))
    state.set_enabled(True)

    async def fake_fetch(base, quote):
        return 7.1234

    monkeypatch.setattr(rates, "fetch_rate", fake_fetch)
    matcher = _FakeMatcher()
    await _run(
        commands.handle_fx(_FakeEvent(1), matcher, Message("fx convert 100 usd/cny"))
    )

    assert "100 USD = 712.34 CNY" in str(matcher.sent[-1])


async def test_calc_bad_amount(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(state.config, "data_dir", str(tmp_path))
    state.set_enabled(True)

    matcher = _FakeMatcher()
    await _run(commands.handle_fx(_FakeEvent(1), matcher, Message("fx calc abc")))

    assert "金额格式不正确" in str(matcher.sent[-1])


def test_split_amount_variants() -> None:
    assert commands._split_amount("100 USD") == (100.0, "100", "USD")
    assert commands._split_amount("100USD") == (100.0, "100", "USD")
    assert commands._split_amount("0.5 BTC/USD") == (0.5, "0.5", "BTC/USD")
    assert commands._split_amount("100 USD/CNY") == (100.0, "100", "USD/CNY")
    assert commands._split_amount("100 usd cny") == (100.0, "100", "usd cny")
    with pytest.raises(rates.RateError):
        commands._split_amount("")
    with pytest.raises(rates.RateError):
        commands._split_amount("abc")


def test_parse_xr_amount() -> None:
    assert commands._parse_xr_amount("1000") == (1000.0, "1000")
    assert commands._parse_xr_amount("100.5円") == (100.5, "100.5")
    assert commands._parse_xr_amount(" 50 ") == (50.0, "50")
    assert commands._parse_xr_amount("abc") is None
    assert commands._parse_xr_amount("0") is None
    assert commands._parse_xr_amount("") is None


async def test_xr_calculator(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(state.config, "data_dir", str(tmp_path))
    state.set_enabled(True)

    matcher = _FakeMatcher()
    await _run(commands.handle_xr(_FakeEvent(1), matcher, Message("1000")))

    sent = str(matcher.sent[-1])
    assert "闲人＠因幡めぐる大好き的代购计算器" in sent
    assert "1000 × 0.055 = 55" in sent


async def test_xr_requires_amount(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(state.config, "data_dir", str(tmp_path))
    state.set_enabled(True)

    matcher = _FakeMatcher()
    await _run(commands.handle_xr(_FakeEvent(1), matcher, Message("abc")))

    assert "用法：/xr <金额>" in str(matcher.sent[-1])


async def test_xr_disabled_blocks(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(state.config, "data_dir", str(tmp_path))
    state.set_enabled(False)

    matcher = _FakeMatcher()
    await _run(commands.handle_xr(_FakeEvent(1), matcher, Message("1000")))

    assert "未启用" in str(matcher.sent[-1])


async def test_chart_sends_image(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(state.config, "data_dir", str(tmp_path))
    state.set_enabled(True)

    async def fake_history(base, quote, days):
        return (["08-01", "08-02"], [7.1, 7.2])

    monkeypatch.setattr(rates, "fetch_history", fake_history)
    monkeypatch.setattr(
        commands.chart,
        "render_chart",
        lambda title, labels, values: b"\x89PNG-fake-data",
    )

    matcher = _FakeMatcher()
    await _run(
        commands.handle_fx(_FakeEvent(1), matcher, Message("fx chart usd-cny 7"))
    )

    message = matcher.sent[-1]
    assert message[0].type == "image"
    assert "走势" in str(message[1])
