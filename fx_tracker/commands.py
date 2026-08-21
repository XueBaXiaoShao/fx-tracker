"""/shou fx 命令入口：汇率关注（默认关闭，管理员 enable 后启用）。"""

from __future__ import annotations

import base64
import re
import json
from pathlib import Path

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Message, MessageEvent, MessageSegment
from nonebot.matcher import Matcher
from nonebot.params import CommandArg

from . import chart, permissions, rates, state, watchlist
from .config import config


def _is_fx_event(event: MessageEvent) -> bool:
    text = (event.get_plaintext() or "").lstrip()
    return re.match(r"^/?shou\s*fx(?:\s|$)", text, re.IGNORECASE) is not None


fx_cmd = on_command("shou", rule=_is_fx_event, priority=1, block=True)


# 闲人＠因幡めぐる大好き的代购计算器（集成在 fx 插件，命令单独）
# R18 固定按 0.055 倍换算；全年龄按当日日元兑人民币汇率换算。
XR_RATE = 0.055
XR_NOTE = "闲人＠因幡めぐる大好き的代购计算器"

# 模式关键字 -> (显示名, 汇率来源: fixed=固定0.055 / live=当日JPY->CNY)
_XR_MODES = {
    "r18": ("R18", "fixed"),
    "r-18": ("R18", "fixed"),
    "18": ("R18", "fixed"),
    "全年龄": ("全年龄", "live"),
    "全": ("全年龄", "live"),
    "sfw": ("全年龄", "live"),
    "allage": ("全年龄", "live"),
    "allages": ("全年龄", "live"),
    "normal": ("全年龄", "live"),
}


def _is_xr_event(event: MessageEvent) -> bool:
    text = (event.get_plaintext() or "").lstrip()
    return re.match(r"^/?xr(?:\s|$)", text, re.IGNORECASE) is not None


xr_cmd = on_command("xr", rule=_is_xr_event, priority=1, block=True)


def _parse_xr_amount(value: str) -> tuple[float, str] | None:
    """提取开头金额数字，返回（金额, 原样文本）；非法或非正数返回 None。"""
    text = (value or "").strip()
    match = re.match(r"^(\d+(?:\.\d+)?)", text)
    if not match:
        return None
    amount = float(match.group(1))
    if amount <= 0:
        return None
    return amount, match.group(1)


def _parse_xr_input(value: str) -> tuple[str, tuple[float, str]]:
    """解析 /xr 参数：返回（模式显示名, （金额, 原样文本））；无模式时默认 R18。"""
    text = (value or "").strip()
    parts = text.split(maxsplit=1)
    mode = "R18"
    rest = text
    if parts and parts[0].lower() in _XR_MODES:
        mode, _kind = _XR_MODES[parts[0].lower()]
        rest = parts[1].strip() if len(parts) > 1 else ""
    parsed = _parse_xr_amount(rest)
    if parsed is None:
        raise rates.RateError(
            "用法：/xr [r18|全年龄] <金额>，例如 /xr r18 12000、/xr 全年龄 5000"
        )
    return mode, parsed


def _plugin_switch_enabled(event: MessageEvent) -> bool:
    """该群是否启用 fx_tracker（读取与 x_admin 共用的 plugin_switches.json）。"""
    group_id = getattr(event, "group_id", None)
    if group_id is None:
        return True
    try:
        payload = json.loads(
            (Path(config.data_dir) / "plugin_switches.json").read_text(
                encoding="utf-8"
            )
        )
    except (OSError, json.JSONDecodeError):
        return True
    if not isinstance(payload, dict):
        return True
    groups = payload.get("groups")
    if isinstance(groups, dict):
        entry = groups.get(str(group_id))
        if isinstance(entry, dict) and "fx_tracker" in entry:
            return bool(entry["fx_tracker"])
    defaults = payload.get("defaults")
    if isinstance(defaults, dict) and "fx_tracker" in defaults:
        return bool(defaults["fx_tracker"])
    return True


def _help_text() -> str:
    return """【汇率插件】（测试，默认关闭）
- /shou fx price <币种对> —— 查询汇率，如 BTC/USD、CNY/JPY
- /shou fx calc <金额> <币种对> —— 直接换算，如 calc 100 USD 或 calc 0.5 BTC/USD
- /xr [r18|全年龄] <金额> —— 闲人＠因幡めぐる大好き的代购计算器（R18×0.055，全年龄按当日日元汇率）
- /shou fx chart <币种对> [天数] —— 查看近 N 天汇率走势图（默认 30 天）
- /shou fx add <币种对> —— 加入我的关注列表
- /shou fx del <币种对> —— 移出我的关注列表
- /shou fx list —— 查看我的关注列表及最新汇率
- /shou fx enable|disable —— 开启/关闭插件（仅管理员）

支持法定货币（USD/CNY/JPY/EUR...）与虚拟货币（BTC/ETH/USDT...）；
币种对可用 /、- 或空格分隔，单币种默认兑 CNY。"""


@fx_cmd.handle()
async def handle_fx(
    event: MessageEvent,
    matcher: Matcher,
    arg: Message = CommandArg(),
) -> None:
    text = (arg.extract_plain_text() or "").strip()
    # CommandArg 包含命令后的全部内容，如 "fx price JPY/CNY"；先剥掉 fx 前缀
    tokens = text.split(maxsplit=1)
    if not tokens or tokens[0].lower() != "fx":
        await matcher.finish(_help_text())
    remainder = tokens[1].strip() if len(tokens) > 1 else ""
    parts = remainder.split(maxsplit=1)
    sub = parts[0].lower() if parts else ""
    rest = parts[1].strip() if len(parts) > 1 else ""

    if sub in ("enable", "disable"):
        if not permissions.is_admin(int(getattr(event, "user_id", 0))):
            await matcher.finish("只有管理员可以开启/关闭汇率插件")
        state.set_enabled(sub == "enable")
        await matcher.finish(
            f"汇率插件已{'开启' if sub == 'enable' else '关闭'}"
        )

    if sub not in ("enable", "disable") and not _plugin_switch_enabled(event):
        await matcher.finish("该群已禁用汇率功能")
    if sub not in ("enable", "disable") and not state.is_enabled():
        await matcher.finish(
            "汇率插件当前未启用（测试模式），管理员可用 /shou fx enable 开启"
        )

    try:
        if not sub:
            await matcher.finish(_help_text())
        if sub == "price":
            await _cmd_price(matcher, rest)
        elif sub in ("calc", "convert"):
            await _cmd_calc(matcher, rest)
        elif sub in ("chart", "trend"):
            await _cmd_chart(matcher, rest)
        elif sub == "add":
            await _cmd_add(event, matcher, rest)
        elif sub == "del":
            await _cmd_del(event, matcher, rest)
        elif sub == "list":
            await _cmd_list(event, matcher)
        else:
            await matcher.finish(_help_text())
    except (rates.RateError, ValueError) as exc:
        await matcher.finish(str(exc))


@xr_cmd.handle()
async def handle_xr(
    event: MessageEvent,
    matcher: Matcher,
    arg: Message = CommandArg(),
) -> None:
    """闲人＠因幡めぐる大好き的代购计算器：R18 ×0.055；全年龄按当日日元兑人民币汇率。"""
    if not _plugin_switch_enabled(event):
        await matcher.finish("该群已禁用汇率功能")
    if not state.is_enabled():
        await matcher.finish(
            "汇率插件当前未启用（测试模式），管理员可用 /shou fx enable 开启"
        )
    try:
        mode, (amount, amount_text) = _parse_xr_input(
            (arg.extract_plain_text() or "").strip()
        )
        if mode == "R18":
            rate = XR_RATE
            rate_text = f"{rate:g}"
        else:
            rate = await rates.fetch_rate("JPY", "CNY")
            rate_text = f"{rate:.4f}"
        result = amount * rate
    except (rates.RateError, ValueError) as exc:
        await matcher.finish(str(exc))
    await matcher.finish(
        f"【{XR_NOTE} · {mode}】\n"
        f"{amount_text} × {rate_text} = {rates.format_amount(result)} 元"
    )


async def _cmd_price(matcher: Matcher, value: str) -> None:
    base, quote = rates.parse_pair(value)
    value = await rates.fetch_rate(base, quote)
    await matcher.finish(
        f"1 {base} = {rates.format_rate(value)} {quote}"
    )


_AMOUNT_RE = re.compile(
    r"^(\d+(?:\.\d+)?)\s*"
    r"([A-Za-z]{3,6}(?:\s*[/\-]\s*[A-Za-z]{3,6})?)$"
)


def _split_amount(value: str) -> tuple[float, str, str]:
    """把 "100 USD/CNY"、"100USD"、"0.5 btc usd" 拆成（金额, 原样金额文本, 币种对）。"""
    text = (value or "").strip().replace("，", "/")
    if not text:
        raise rates.RateError(
            "用法：/shou fx calc <金额> <币种对>，如 calc 100 USD/CNY"
        )
    match = _AMOUNT_RE.match(text)
    if match:
        amount = float(match.group(1))
        amount_text, pair_text = match.group(1), match.group(2)
    else:
        parts = text.split(maxsplit=1)
        try:
            amount = float(parts[0])
        except (ValueError, IndexError):
            raise rates.RateError("金额格式不正确，例如：calc 100 USD/CNY")
        amount_text = parts[0]
        pair_text = parts[1].strip() if len(parts) > 1 else ""
    if amount <= 0:
        raise rates.RateError("金额需大于 0")
    if not pair_text:
        raise rates.RateError("请输入要换算的币种对，例如：calc 100 USD/CNY")
    return amount, amount_text, pair_text


async def _cmd_calc(matcher: Matcher, value: str) -> None:
    """直接换算：calc <金额> <币种对>，如 calc 100 USD、calc 0.5 BTC/USD。"""
    amount, amount_text, pair_text = _split_amount(value)
    base, quote = rates.parse_pair(pair_text)
    rate = await rates.fetch_rate(base, quote)
    await matcher.finish(
        f"{amount_text} {base} = "
        f"{rates.format_amount(amount * rate)} {quote}"
    )


async def _cmd_chart(matcher: Matcher, value: str) -> None:
    parts = value.split()
    if not parts:
        await matcher.finish("用法：/shou fx chart <币种对> [天数]")
    pair_text = parts[0]
    days = 30
    if len(parts) >= 2 and parts[1].isdigit():
        days = int(parts[1])
    days = max(1, min(days, 90))
    base, quote = rates.parse_pair(pair_text)
    labels, values = await rates.fetch_history(base, quote, days)
    if not values:
        await matcher.finish("没有获取到走势数据")
    png = chart.render_chart(
        f"{base}/{quote} 近{days}天走势",
        labels,
        values,
    )
    caption = (
        f"{base}/{quote} 近{days}天走势"
        f"（最新 {rates.format_rate(values[-1])}）"
    )
    await matcher.finish(
        Message(
            [
                MessageSegment.image(f"base64://{base64.b64encode(png).decode()}"),
                MessageSegment.text(caption),
            ]
        )
    )


async def _cmd_add(
    event: MessageEvent, matcher: Matcher, value: str
) -> None:
    base, quote = rates.parse_pair(value)
    rates.classify(base)
    rates.classify(quote)
    user_id = int(getattr(event, "user_id", 0))
    if watchlist.add_pair(user_id, base, quote):
        await matcher.finish(f"已关注 {base}/{quote}（最多展示见 /shou fx list）")
    await matcher.finish(f"{base}/{quote} 已在你的关注列表")


async def _cmd_del(
    event: MessageEvent, matcher: Matcher, value: str
) -> None:
    base, quote = rates.parse_pair(value)
    user_id = int(getattr(event, "user_id", 0))
    if watchlist.remove_pair(user_id, base, quote):
        await matcher.finish(f"已取消关注 {base}/{quote}")
    await matcher.finish(f"{base}/{quote} 不在你的关注列表")


async def _cmd_list(event: MessageEvent, matcher: Matcher) -> None:
    user_id = int(getattr(event, "user_id", 0))
    pairs = watchlist.list_pairs(user_id)
    if not pairs:
        await matcher.finish("你还没有关注任何币种：/shou fx add <币种对>")
    lines = ["【我的汇率关注】"]
    for base, quote in pairs[:10]:
        try:
            value = await rates.fetch_rate(base, quote)
            lines.append(f"1 {base} = {rates.format_rate(value)} {quote}")
        except rates.RateError as exc:
            lines.append(f"{base}/{quote}：{exc}")
    await matcher.finish(Message(MessageSegment.text("\n".join(lines))))
