"""/shou fx 命令入口：汇率关注（默认关闭，管理员 enable 后启用）。"""

from __future__ import annotations

import re
import json
from pathlib import Path

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Message, MessageEvent, MessageSegment
from nonebot.matcher import Matcher
from nonebot.params import CommandArg

from . import permissions, rates, state, watchlist
from .config import config


def _is_fx_event(event: MessageEvent) -> bool:
    text = (event.get_plaintext() or "").lstrip()
    return re.match(r"^/?shou\s*fx(?:\s|$)", text, re.IGNORECASE) is not None


fx_cmd = on_command("shou", rule=_is_fx_event, priority=1, block=True)


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
- /shou fx add <币种对> —— 加入我的关注列表
- /shou fx del <币种对> —— 移出我的关注列表
- /shou fx list —— 查看我的关注列表及最新汇率
- /shou fx enable|disable —— 开启/关闭插件（仅管理员）

支持法定货币（USD/CNY/JPY/EUR...）与虚拟货币（BTC/ETH/USDT...）；
币种对可用 /、- 或空格分隔，单币种默认兑 USD。"""


@fx_cmd.handle()
async def handle_fx(
    event: MessageEvent,
    matcher: Matcher,
    arg: Message = CommandArg(),
) -> None:
    text = (arg.extract_plain_text() or "").strip()
    parts = text.split(maxsplit=1)
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


async def _cmd_price(matcher: Matcher, value: str) -> None:
    base, quote = rates.parse_pair(value)
    value = await rates.fetch_rate(base, quote)
    await matcher.finish(
        f"1 {base} = {rates.format_rate(value)} {quote}"
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
