"""汇率解析与数据源测试。"""

from __future__ import annotations

import pytest

from fx_tracker import rates


def test_parse_pair_variants() -> None:
    assert rates.parse_pair("BTC/USD") == ("BTC", "USD")
    assert rates.parse_pair("btc-usd") == ("BTC", "USD")
    assert rates.parse_pair("cny jpy") == ("CNY", "JPY")
    assert rates.parse_pair("btc") == ("BTC", "USD")
    with pytest.raises(rates.RateError):
        rates.parse_pair("")


def test_classify() -> None:
    assert rates.classify("btc") == ("crypto", "bitcoin")
    assert rates.classify("usdt") == ("crypto", "tether")
    assert rates.classify("cny") == ("fiat", "CNY")
    with pytest.raises(rates.RateError):
        rates.classify("XXX")


def test_format_rate() -> None:
    assert rates.format_rate(1500.5) == "1,500.50"
    assert rates.format_rate(7.12345) == "7.1235"
    assert rates.format_rate(0.00001234) == "0.000012"


async def test_fetch_fiat_pair(monkeypatch) -> None:
    async def fake_request(method, url, params):
        assert url == "https://api.frankfurter.app/latest"
        assert params == {"from": "USD", "to": "CNY"}
        return {"rates": {"CNY": 7.12}}

    monkeypatch.setattr(rates, "_request", fake_request)
    assert await rates.fetch_rate("USD", "CNY") == 7.12


async def test_fetch_crypto_to_fiat(monkeypatch) -> None:
    async def fake_request(method, url, params):
        assert params == {"ids": "bitcoin", "vs_currencies": "usd"}
        return {"bitcoin": {"usd": 60000.5}}

    monkeypatch.setattr(rates, "_request", fake_request)
    assert await rates.fetch_rate("BTC", "USD") == 60000.5


async def test_fetch_fiat_to_crypto(monkeypatch) -> None:
    async def fake_request(method, url, params):
        assert params["ids"] == "bitcoin"
        return {"bitcoin": {"usd": 50000}}

    monkeypatch.setattr(rates, "_request", fake_request)
    assert await rates.fetch_rate("USD", "BTC") == pytest.approx(0.00002)


async def test_fetch_crypto_pair_via_usd(monkeypatch) -> None:
    async def fake_request(method, url, params):
        if params["ids"] == "bitcoin":
            return {"bitcoin": {"usd": 60000}}
        return {"ethereum": {"usd": 3000}}

    monkeypatch.setattr(rates, "_request", fake_request)
    assert await rates.fetch_rate("BTC", "ETH") == 20.0
