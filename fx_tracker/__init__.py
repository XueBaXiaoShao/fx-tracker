"""汇率关注插件（测试）：法定货币 + 虚拟货币，个人关注列表。

默认关闭，仅管理员用 /shou fx enable 开启后生效；
命令入口 /shou fx，与 xqq-forwarder 的 /shou 管理命令共存。
"""

from nonebot.plugin import PluginMetadata

from . import commands  # noqa: F401

__plugin_meta__ = PluginMetadata(
    name="汇率关注（测试）",
    description=(
        "关注汇率：支持法定货币与虚拟货币、个人币种关注列表；"
        "默认关闭，管理员 /shou fx enable 开启"
    ),
    usage=(
        "/shou fx price <币种对>、/shou fx add <币种对>、/shou fx del <币种对>、"
        "/shou fx list、/shou fx enable|disable（管理员）"
    ),
    type="application",
    homepage="",
    supported_adapters={"~onebot.v11"},
)
