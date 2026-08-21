# 汇率关注插件（测试）

NoneBot2 + OneBot v11 独立插件，命令挂在 **`/shou fx`** 下，与 xqq-forwarder 的
`/shou` 管理命令共存。支持**法定货币**（USD/CNY/JPY/EUR 等）与**虚拟货币**
（BTC/ETH/USDT 等，内置常见币种映射），并提供个人币种关注列表。

> ⚠️ 测试模式：插件**默认关闭**，只有管理员执行 `/shou fx enable` 后才响应。

## 功能

| 命令 | 说明 |
| --- | --- |
| `/shou fx price <币种对>` | 查询汇率，如 `BTC/USD`、`CNY/JPY` |
| `/shou fx calc <金额> <币种对>` | 直接换算，如 `calc 100 USD`、`calc 0.5 BTC/USD`（别名 `convert`） |
| `/xr [r18\|全年龄\|全\|sfw] <金额>` | 闲人＠因幡めぐる大好き的代购计算器：`r18`/`18`（默认）按固定 ×0.055，`全年龄`（简写 `全`/`sfw`/`all`）按当日日元兑人民币汇率换算（命令单独，集成在 fx 插件内） |
| `/shou fx chart <币种对> [天数]` | 查看近 N 天汇率走势图（默认 30，最多 90） |
| `/shou fx add <币种对>` | 加入我的关注列表 |
| `/shou fx del <币种对>` | 移出我的关注列表 |
| `/shou fx list` | 查看我的关注列表及最新汇率 |
| `/shou fx enable` | 开启插件（仅管理员，测试用） |
| `/shou fx disable` | 关闭插件（仅管理员） |

币种对可用 `/`、`-` 或空格分隔，单币种默认兑 CNY。

## 数据源

- 法定货币：Frankfurter（ECB 汇率，免费无需密钥）；
- 虚拟货币：CoinGecko（免费无需密钥）；
- 币币对（如 BTC/ETH）经 USD 换算。

## 开关与权限

- 默认关闭：`data/fx_state.json` 不存在时按 `FX_ENABLED`（默认 false）；
- `/shou fx enable|disable` 仅管理员可用，管理员名单读取与 x_admin/galgame-box
  共用的 `data/admin_ids.json`（`{"version": 2, "admins": [...]}`）；
- 关注列表持久化在 `data/fx_watchlist.json`。

## 配置（环境变量）

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `FX_ENABLED` | `false` | 强制启用（测试时可直接设 true） |
| `FX_DATA_DIR` | `data/` | 状态与关注列表目录（回退 `LOCALSTORE_DATA_DIR`） |
| `FX_REQUEST_TIMEOUT` | `15` | 汇率接口超时（秒） |
| `FX_REQUEST_RETRIES` | `3` | 请求重试次数（429 限流自动重试） |

## 安装

```bash
cd /opt/fx-tracker
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

在 `bot.py` 中加载：

```python
nonebot.load_plugin("fx_tracker")
```

## 测试

```bash
make test
```
