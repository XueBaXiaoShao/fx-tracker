"""汇率数据源：Frankfurter（法定货币）+ CoinGecko（虚拟货币）。"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

import httpx

from .config import config

FIAT = {
    "USD", "EUR", "CNY", "JPY", "GBP", "CHF", "AUD", "CAD", "SEK", "NOK",
    "DKK", "PLN", "CZK", "HUF", "RON", "BGN", "TRY", "ILS", "PHP", "SGD",
    "THB", "MYR", "IDR", "KRW", "INR", "BRL", "ZAR", "MXN", "NZD", "HKD",
    "TWD", "VND", "RUB", "AED", "SAR",
}

# Frankfurter 基于 ECB 汇率，仅覆盖以下币种；其余币种走 open.er-api 兜底
FRANKFURTER_URL = "https://api.frankfurter.dev/v1"
FRANKFURTER_CURRENCIES = {
    "AUD", "BRL", "CAD", "CHF", "CNY", "CZK", "DKK", "EUR", "GBP", "HKD",
    "HUF", "IDR", "ILS", "INR", "ISK", "JPY", "KRW", "MXN", "MYR", "NOK",
    "NZD", "PHP", "PLN", "RON", "SEK", "SGD", "THB", "TRY", "USD", "ZAR",
}
FIAT_FALLBACK_URL = "https://open.er-api.com/v6/latest"
CURRENCY_API_URL = "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api"

# 常用虚拟货币：币种符号 -> CoinGecko ID
CRYPTO = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "USDT": "tether",
    "USDC": "usd-coin",
    "BNB": "binancecoin",
    "SOL": "solana",
    "XRP": "ripple",
    "ADA": "cardano",
    "DOGE": "dogecoin",
    "TRX": "tron",
    "DOT": "polkadot",
    "LTC": "litecoin",
    "LINK": "chainlink",
    "AVAX": "avalanche-2",
    "TON": "the-open-network",
    "MATIC": "matic-network",
    "SHIB": "shiba-inu",
    "UNI": "uniswap",
    "BCH": "bitcoin-cash",
    "XLM": "stellar",
    "ATOM": "cosmos",
    "ETC": "ethereum-classic",
    "NEAR": "near",
    "APT": "aptos",
    "ARB": "arbitrum",
    "OP": "optimism",
    "SUI": "sui",
    "FIL": "filecoin",
    "ICP": "internet-computer",
    "AAVE": "aave",
    "MKR": "maker",
    "PEPE": "pepe",
    "XMR": "monero",
    "ZEC": "zcash",
    "DASH": "dash",
    "EOS": "eos",
    "NEO": "neo",
    "KSM": "kusama",
    "WIF": "dogwifcoin",
    "INJ": "injective-protocol",
    "RUNE": "thorchain",
    "FTM": "fantom",
    "GALA": "gala",
    "SAND": "the-sandbox",
    "MANA": "decentraland",
    "AXS": "axie-infinity",
    "GMT": "stepn",
    "MINA": "mina-protocol",
    "ALGO": "algorand",
    "VET": "vechain",
    "EGLD": "elrond-erd-2",
    "CRO": "crypto-com-chain",
    "OKB": "okb",
    "LDO": "lido-dao",
    "GRT": "the-graph",
    "HBAR": "hedera-hashgraph",
    "KAS": "kaspa",
    "STX": "stacks",
    "AR": "arweave",
    "IMX": "immutable-x",
    "BONK": "bonk",
    "NOT": "notcoin",
    "TAO": "bittensor",
    "ENA": "ethena",
    "ONDO": "ondo-finance",
    "FET": "fetch-ai",
    "RNDR": "render-token",
}


class RateError(RuntimeError):
    pass


def classify(symbol: str) -> tuple[str, str]:
    """返回（crypto/fiat, CoinGecko ID 或 ISO 代码）。"""
    symbol = symbol.upper()
    if symbol in CRYPTO:
        return "crypto", CRYPTO[symbol]
    if symbol in FIAT:
        return "fiat", symbol
    raise RateError(f"暂不支持的币种：{symbol}")


def parse_pair(text: str) -> tuple[str, str]:
    """把 BTC/USD、BTC-USD、btc usd 解析成（base, quote）；单币种默认兑 USD。"""
    cleaned = (text or "").strip().upper().replace("，", "/")
    if not cleaned:
        raise RateError("请输入币种对，例如：BTC/USD 或 CNY/JPY")
    parts = [part for part in cleaned.replace("-", "/").replace(" ", "/").split("/") if part]
    if len(parts) == 1:
        symbol = parts[0]
        # 兼容连续六位写法：JPYCNY -> JPY/CNY、BTCETH -> BTC/ETH
        if len(symbol) == 6:
            return symbol[:3], symbol[3:]
        return symbol, "CNY"
    if len(parts) == 2:
        return parts[0], parts[1]
    raise RateError(f"币种对格式错误：{text}")


def format_rate(value: float) -> str:
    if value >= 1000:
        return f"{value:,.2f}"
    if value >= 1:
        return f"{value:,.4f}"
    return f"{value:.6f}"


def format_amount(value: float) -> str:
    """金额换算结果的智能精度：大额保留两位，小额保留更多有效位。"""
    if value >= 100:
        return f"{value:,.2f}"
    if value >= 1:
        return f"{value:.4f}".rstrip("0").rstrip(".")
    if value >= 0.0001:
        return f"{value:.6f}".rstrip("0").rstrip(".")
    return f"{value:.8f}".rstrip("0").rstrip(".")


async def _request(method: str, url: str, params: dict) -> dict:
    last_error: Exception | None = None
    for attempt in range(max(1, config.request_retries)):
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(config.request_timeout),
                follow_redirects=True,
            ) as client:
                response = await client.request(method, url, params=params)
                if response.status_code == 429:
                    raise _RateLimited("接口限流（HTTP 429）")
                response.raise_for_status()
                return response.json()
        except _RateLimited as exc:
            last_error = exc
        except httpx.HTTPStatusError as exc:
            last_error = exc
            # 4xx 通常是币种不支持/参数错误，重试没有意义
            if 400 <= exc.response.status_code < 500:
                break
        except (httpx.HTTPError, ValueError) as exc:
            last_error = exc
        await asyncio.sleep(1.0 * (attempt + 1))
    detail = f"{type(last_error).__name__}: {last_error}" if last_error else "未知错误"
    raise RateError(f"汇率接口请求失败：{detail}（{url}）")


class _RateLimited(Exception):
    pass


async def fetch_rate(base: str, quote: str) -> float:
    """获取 base/quote 汇率（base 为 1 单位可兑换多少 quote）。"""
    base_kind, base_key = classify(base)
    quote_kind, quote_key = classify(quote)

    if base_kind == "fiat" and quote_kind == "fiat":
        if base_key == quote_key:
            return 1.0
        if (
            base_key in FRANKFURTER_CURRENCIES
            and quote_key in FRANKFURTER_CURRENCIES
        ):
            try:
                data = await _request(
                    "GET",
                    f"{FRANKFURTER_URL}/latest",
                    {"from": base_key, "to": quote_key},
                )
                rates = data.get("rates") if isinstance(data, dict) else None
                if rates and quote_key in rates:
                    return float(rates[quote_key])
            except RateError:
                # Frankfurter 不可用时继续走兜底数据源
                pass
        return await _fiat_rate_fallback(base_key, quote_key)

    if base_kind == "crypto" and quote_kind == "fiat":
        return await _crypto_price(base_key, quote_key)

    if base_kind == "fiat" and quote_kind == "crypto":
        price = await _crypto_price(quote_key, base_key)
        if price <= 0:
            raise RateError("汇率计算失败")
        return 1.0 / price

    # 虚拟货币对虚拟货币：经 USD 换算
    base_usd = await _crypto_price(base_key, "usd")
    quote_usd = await _crypto_price(quote_key, "usd")
    if quote_usd <= 0:
        raise RateError("汇率计算失败")
    return base_usd / quote_usd


async def _fiat_rate_fallback(base_key: str, quote_key: str) -> float:
    """Frankfurter 不支持的法定货币走 open.er-api（每日更新，无需密钥）。"""
    data = await _request(
        "GET", f"{FIAT_FALLBACK_URL}/{base_key}", {}
    )
    if not isinstance(data, dict) or data.get("result") != "success":
        detail = data.get("error-type") if isinstance(data, dict) else ""
        suffix = f"（{detail}）" if detail else ""
        raise RateError(
            f"汇率接口未返回 {base_key}/{quote_key}{suffix}"
        )
    rates_map = data.get("rates")
    value = rates_map.get(quote_key) if isinstance(rates_map, dict) else None
    if value is None:
        raise RateError(f"暂不支持该法定货币对：{base_key}/{quote_key}")
    try:
        return float(value)
    except (TypeError, ValueError):
        raise RateError(f"汇率数据格式异常：{base_key}/{quote_key}") from None


async def _fiat_history_fallback(
    base_key: str, quote_key: str, days: int
) -> tuple[list[str], list[float]]:
    """用 fawazahmed0/currency-api 按日拉取不支持 ECB 的币种走势。"""
    base_lower = base_key.lower()
    quote_lower = quote_key.lower()
    targets = [
        date.today() - timedelta(days=offset)
        for offset in range(days - 1, -1, -1)
    ]
    semaphore = asyncio.Semaphore(6)

    async def fetch_day(day: date) -> tuple[str, float]:
        async with semaphore:
            data = await _request(
                "GET",
                f"{CURRENCY_API_URL}@{day.isoformat()}"
                f"/v1/currencies/{base_lower}.json",
                {},
            )
        rates_map = data.get(base_lower) if isinstance(data, dict) else None
        value = rates_map.get(quote_lower) if isinstance(rates_map, dict) else None
        if value is None:
            raise ValueError("missing rate")
        return day.isoformat(), float(value)

    results = await asyncio.gather(
        *(fetch_day(day) for day in targets), return_exceptions=True
    )
    labels: list[str] = []
    values: list[float] = []
    for result in results:
        if isinstance(result, tuple):
            labels.append(result[0])
            values.append(result[1])
    if not values:
        raise RateError(
            f"暂不支持 {base_key}/{quote_key} 的走势数据"
        )
    return labels, values


async def _crypto_price(coin_id: str, fiat_code: str) -> float:
    data = await _request(
        "GET",
        "https://api.coingecko.com/api/v3/simple/price",
        {"ids": coin_id, "vs_currencies": fiat_code.lower()},
    )
    coin = data.get(coin_id) if isinstance(data, dict) else None
    if not coin or fiat_code.lower() not in coin:
        raise RateError("CoinGecko 未返回该币种价格")
    return float(coin[fiat_code.lower()])


async def fetch_history(
    base: str, quote: str, days: int = 30
) -> tuple[list[str], list[float]]:
    """获取近 N 天汇率走势，返回（日期标签, 数值列表）。"""
    days = max(1, min(days, 90))
    base_kind, base_key = classify(base)
    quote_kind, quote_key = classify(quote)

    if base_kind == "fiat" and quote_kind == "fiat":
        if base_key == quote_key:
            labels = [
                (date.today() - timedelta(days=offset)).isoformat()
                for offset in range(days - 1, -1, -1)
            ]
            return labels, [1.0] * days
        if (
            base_key in FRANKFURTER_CURRENCIES
            and quote_key in FRANKFURTER_CURRENCIES
        ):
            start = (date.today() - timedelta(days=days)).isoformat()
            try:
                data = await _request(
                    "GET",
                    f"{FRANKFURTER_URL}/{start}..",
                    {"from": base_key, "to": quote_key},
                )
                rates_map = (
                    data.get("rates") if isinstance(data, dict) else None
                )
                if isinstance(rates_map, dict) and rates_map:
                    labels = sorted(rates_map)
                    values = [
                        float(rates_map[label][quote_key])
                        for label in labels
                    ]
                    return labels, values
            except (RateError, KeyError, TypeError, ValueError):
                pass
        return await _fiat_history_fallback(base_key, quote_key, days)

    if base_kind == "crypto" and quote_kind == "fiat":
        prices = await _crypto_history(base_key, quote_key, days)
        return _crypto_labels(prices), prices

    if base_kind == "fiat" and quote_kind == "crypto":
        prices = await _crypto_history(quote_key, base_key, days)
        return _crypto_labels(prices), [1.0 / p for p in prices if p > 0]

    # 虚拟货币对虚拟货币：统一按 CNY 取两边再相除
    base_prices = await _crypto_history(base_key, "cny", days)
    quote_prices = await _crypto_history(quote_key, "cny", days)
    count = min(len(base_prices), len(quote_prices))
    values = [
        base / quote
        for base, quote in zip(base_prices[:count], quote_prices[:count])
        if quote > 0
    ]
    return _crypto_labels(base_prices[:count]), values


async def _crypto_history(coin_id: str, fiat_code: str, days: int) -> list[float]:
    data = await _request(
        "GET",
        f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart",
        {"vs_currency": fiat_code.lower(), "days": days},
    )
    prices = data.get("prices") if isinstance(data, dict) else None
    if not isinstance(prices, list) or not prices:
        raise RateError("CoinGecko 未返回走势数据")
    result: list[float] = []
    for item in prices:
        if isinstance(item, list) and len(item) >= 2:
            try:
                result.append(float(item[1]))
            except (TypeError, ValueError):
                continue
    if not result:
        raise RateError("CoinGecko 走势数据格式异常")
    return result


def _crypto_labels(prices: list[float]) -> list[str]:
    return [f"D{index + 1}" for index in range(len(prices))]
