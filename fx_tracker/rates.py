"""汇率数据源：Frankfurter（法定货币）+ CoinGecko（虚拟货币）。"""

from __future__ import annotations

import asyncio

import httpx

from .config import config

FIAT = {
    "USD", "EUR", "CNY", "JPY", "GBP", "CHF", "AUD", "CAD", "SEK", "NOK",
    "DKK", "PLN", "CZK", "HUF", "RON", "BGN", "TRY", "ILS", "PHP", "SGD",
    "THB", "MYR", "IDR", "KRW", "INR", "BRL", "ZAR", "MXN", "NZD", "HKD",
    "TWD", "VND", "RUB", "AED", "SAR",
}

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
        return symbol, "USD"
    if len(parts) == 2:
        return parts[0], parts[1]
    raise RateError(f"币种对格式错误：{text}")


def format_rate(value: float) -> str:
    if value >= 1000:
        return f"{value:,.2f}"
    if value >= 1:
        return f"{value:,.4f}"
    return f"{value:.6f}"


async def _request(method: str, url: str, params: dict) -> dict:
    last_error: Exception | None = None
    for _ in range(max(1, config.request_retries)):
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(config.request_timeout),
                follow_redirects=True,
            ) as client:
                response = await client.request(method, url, params=params)
                response.raise_for_status()
                return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            last_error = exc
            await asyncio.sleep(0.5)
    raise RateError(f"汇率接口请求失败（{last_error}）")


async def fetch_rate(base: str, quote: str) -> float:
    """获取 base/quote 汇率（base 为 1 单位可兑换多少 quote）。"""
    base_kind, base_key = classify(base)
    quote_kind, quote_key = classify(quote)

    if base_kind == "fiat" and quote_kind == "fiat":
        data = await _request(
            "GET",
            "https://api.frankfurter.app/latest",
            {"from": base_key, "to": quote_key},
        )
        rates = data.get("rates") if isinstance(data, dict) else None
        if not rates or quote_key not in rates:
            raise RateError(f"Frankfurter 暂不支持该法定货币对：{base}/{quote}")
        return float(rates[quote_key])

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
