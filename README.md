# switched.cloud 云令牌刷取工具（Vylo 线路）

自动跑 `panel.switched.cloud` 面板上的 **Earn with Vylo** 赞助链接流程，把刷到的
**Cloud Token** 换成 VPS 运行时长（1 token = 1 天）。

2026-10-23 实机验证：一次跑满 25/25，单条约 90 秒；余额 `50 cloud tokens` → 时长
`2d 22h` → `52d 22h`。

> **只想照做、不想读代码**：看 [FRIEND.md](FRIEND.md)，从 fork 到跑通的 7 步图文说明，
> 含 cookie 怎么取、住宅代理怎么选、`SB_CONFIG` 的 socks / http / ss / vmess / trojan /
> vless / Reality 全套模板。

## 为什么必须走住宅出口

面板和 `vylo.cc` 都会拒绝机房 IP：

```
Turn off your VPN or proxy — Vylo links can't be opened through a VPN, proxy, Tor or a server network.
```

GitHub 托管 runner 本身就是机房 IP，所以 Actions 路线必须挂住宅代理（secret `PROXY`，
形如 `socks5://host:port`）。直连或裸跑只有一句 `no vylo link`。

## Turnstile 为什么点得这么怪

验证码挂在 **closed shadow root** 里：`page.locator()`、`querySelector()` 都摸不到，
解出来之前页面上也没有 `cf-turnstile-response` 节点可读。但 `.cf-turnstile` **容器**
有真实坐标，所以脚本读容器 bounding box，再用 **CDP 真实鼠标事件**
（`Input.dispatchMouseEvent`）点上去 —— 稳定拿到约 773 字符的 token。

过验证码之后是个小状态机：
`Continue → 倒计时（/wait?t=…）→ Unlock → Continue → 倒计时 → Unlock → Get link`
最后跳回面板，Vylo 的回调到账，加 1 个 token。

## 本机用法

用 xvfb 跑「有头」浏览器，这是实测能过 Turnstile 的配置：

```bash
pip install playwright && python -m playwright install chromium
export SW_PROXY=socks5://127.0.0.1:10807        # 住宅出口
python3 -u vylo_farm.py --count 25              # 刷 token
python3 -u add_runtime.py                       # 把余额全部换成运行时长
```

Cookie 来源二选一：

* `NOPROFIT_COOKIES` —— 面板 cookie 的 JSON 本体，raw 或 base64（CI 用这个），或
* `NOPROFIT_COOKIE_FILE` —— cookie JSON 的路径（默认 `~/noprofit_cookies.json`）

获取方式：在已登录的浏览器里 DevTools → Application → Cookies → `panel.switched.cloud`，
导出为 `[{name, value, domain, ...}, ...]` 的 JSON 数组。

## GitHub Actions

`.github/workflows/farm.yml` 只支持手动触发（`workflow_dispatch`）。需要的 secrets：

| secret | 内容 |
| --- | --- |
| `NOPROFIT_COOKIES` | 面板 cookie JSON（raw 或 base64） |
| `PROXY` | 住宅代理 URL，如 `socks5://user:pass@host:port` |
| `SB_CONFIG` | *`PROXY` 的替代方案*：一份 sing-box 配置，其本地 socks 入口监听 10801‑10808（job 自己拉起 sing-box，并用 `socks5://127.0.0.1:10807`） |

输入参数：`count`（默认 25，即每日上限）、`spend`（默认 **false**：只刷 token 留在余额里，需要时才手动勾选换时长）、
`proxy`（临时覆盖代理）。

> 说明：Cloud Token 只是余额，不会自动转成时长；`add_runtime.py` 是**手动**才跑的，
> 工作流默认不调用它。

## 文件说明

* `vylo_farm.py` —— 刷 token 主脚本（`--count`、`--proxy`、`--max-fail`、`--headless`）
* `add_runtime.py` —— 通过 "Add runtime" 弹窗把余额换成时长（`--tokens`、`--dry-run`）
* `panelcookies.py` —— 两个脚本共用的 cookie 读取/落盘

## 已知限制

* 每个站每天 25 个 token，计数按面板本地时间的午夜重置。
* 脚本里有 `--headless`，但实测能过 Turnstile 的是 xvfb 下的「有头」模式。
* 时长是纯倒计时：VPS 什么都不干也在掉，过期后过一小段宽限期就删机，所以要在到期前把
  token 换成时长。
* 这是针对某个奖励计划自身界面的个人自动化，请只用自己的账号跑。
