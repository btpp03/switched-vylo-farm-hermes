# switched.cloud 云令牌刷取工具（Cuty 线路 · 面板 v2.0）

自动跑改版后 `panel.switched.cloud` 面板的赚钱任务，把刷到的 **Cloud Token**
换成 VPS 运行时长（**1 token = 2 天**）。

> 2026-11-10 面板升级到 v2.0.2，旧的 **Earn with Vylo** 按钮已移除、旧余额清零、
> runtime 重置。本仓库已改造为新版路线，本地端到端实测通过：
> `Cuty link completed +1`，余额 `1 → 2`，当日配额 `1/2 → 2/2`。

## 新版面板的三条赚钱通道（怎么处理）

面板 `/tokens` 页现在有三种方式，本脚本的处理：

| 通道 | 收益 | 上限 | 脚本 | 原因 |
| --- | --- | --- | --- | --- |
| **Cuty** | 1 token/条 | 2 条/天 | ✅ 自动刷 | 走 `cuttty.com`，验证码是 Cloudflare Turnstile，旧脚本的坐标点击逻辑可直接复用，实测能到账 |
| **每日签到** | 0.25→1 token/天 | 1 次/天 | ✅ 顺带完成 | 没有按钮，服务端在你打开 `/tokens` 页时自动发放；GA 每天跑一次就必得 |
| **Linkvertise** | 1.5 token/条 | 10 条/天 | ❌ 不做 | 免费路径要「看 3 个广告 + hcaptcha + 订阅/试用诱导页」，机房 runner 过不了，且绝不能误点付费项 |

> 保活够不够：单台 VPS 一天耗 1 天 runtime，Cuty 2 条 = 2 token = 4 天，
> 加签到 ≥0.25，净增。不需要硬啃 Linkvertise。

## Cuty 完整链路（实测）

```
POST panel/tokens/earn  (form: _token + provider=cuty)   → 302 cuty.io/<短链>
 → cuttty.com/<短链>: 点 "Continue"
 → 出现 Cloudflare Turnstile 复选框（closed shadow root）
 → CDP 真实鼠标事件按容器坐标点击，拿到 ~773 字符 token
 → 点 "I am not a robot" 提交 → "preparing your link"
 → 点含 "Go" 的按钮 → 自动跳回 panel.switched.cloud → postback +1 token
```

脚本每次刷新面板读当天配额 `N of 2 today`，只补到 2 条，配额满了直接跳过，不空跑。

## 为什么必须走住宅出口

`cuttty.com` 的 Turnstile 和以前的 `vylo.cc` 一样拒绝机房 IP。GitHub 托管 runner
本身是机房 IP，所以 Actions 路线必须挂住宅代理。三种可选项，填一个就行：

* **推荐 `HOME_VLESS_URL`**（或 `JP_SOCKS_URL`）：一条家宽住宅 vless / socks URL，
  job 用 `scripts/make_relay.py` 起本地 sing-box，统一出口 `127.0.0.1:10900`。
* **`PROXY`**：现成的 `socks5://user:pass@host:port` 或 `http://` 代理 URL。
* **临时覆盖**：手动触发时填 `proxy` 输入项，优先级最高。

## Turnstile 为什么点得这么怪

验证码挂在 **closed shadow root** 里，`page.locator()` / `querySelector()` 摸不到。
但 `.cf-turnstile` **容器**有真实坐标，脚本读 bounding box，用 **CDP 真实鼠标事件**
（`Input.dispatchMouseEvent`）点 28px 处；3 轮没解出来再 fallback 点 challenge iframe。
这套逻辑沿用旧 Vylo 脚本，在 cuttty.com 上同样稳定拿到 773 字符 token。

## 本机用法（xvfb 有头模式，Turnstile 更容易过）

```bash
pip install playwright && python -m playwright install chromium
export SW_PROXY=socks5://127.0.0.1:10900        # 住宅出口
python3 -u vylo_farm.py --count 25              # 只补当天剩余的 Cuty 配额(最多2)
python3 -u add_runtime.py --dry-run             # 只读余额/时长
python3 -u add_runtime.py                       # 把余额全部换成 runtime
```

Cookie 来源二选一：

* `NOPROFIT_COOKIES` —— 面板 cookie 的 JSON 本体，raw 或 base64（CI 用这个），或
* `NOPROFIT_COOKIE_FILE` —— cookie JSON 路径（默认 `~/noprofit_cookies.json`）

获取方式：已登录浏览器 DevTools → Application → Cookies → `panel.switched.cloud`，
导出为 `[{name, value, domain, ...}, ...]` 的 JSON 数组。

## GitHub Actions

`.github/workflows/farm.yml` 只支持手动触发（`workflow_dispatch`）。需要的 secrets：

| secret | 内容 |
| --- | --- |
| `NOPROFIT_COOKIES` | 面板 cookie JSON（raw 或 base64），**必填** |
| `HOME_VLESS_URL` | 家宽住宅 vless URL（推荐），与 `JP_SOCKS_URL` 二选一 |
| `JP_SOCKS_URL` | 备用 socks URL |
| `PROXY` | 现成代理 URL，与上面二选一；也可在触发时填 `proxy` 覆盖 |

输入参数：

* `count`（默认 25）：最多尝试几条 Cuty；**面板硬上限 2/天**，脚本会自动只用当天剩余配额，填 25 也不会多刷。
* `spend`（默认 **false**）：刷完后是否把全部余额换成 runtime。默认不换，token 留余额里。
* `proxy`：临时覆盖代理 URL。

> Cloud Token 只是余额，不会自动转时长。`add_runtime.py` 默认不跑，需要时把 `spend` 勾 true。

## 定时触发

工作流本身**没有** `schedule`（本机账号的 GA 原生定时基本不 fire）。外部用
cron-job.org 每天 09:00（北京时间）POST 一次 `workflow_dispatch`：
body `count=25&spend=false`。改脚本不需要动定时。

## 文件说明

* `vylo_farm.py` —— 刷 token 主脚本（Cuty 线路 + 每日签到）
* `add_runtime.py` —— 把余额换成时长（`--tokens`、`--dry-run`）
* `panelcookies.py` —— 共用的 cookie 读取/落盘
* `scripts/make_relay.py` —— vless/socks URL → 本地 sing-box relay 配置

## 已知限制 / 回滚

* Cuty 每天只有 2 条；Linkvertise 的 15 个潜在 token 主动放弃。
* 每日签到靠「打开页面」发放，按面板本地时间午夜重置；连续签到逐日升到 1 token。
* 时长纯倒计时，VPS 不干活也在掉。1 token = 2 天，1 台机一天耗 1 天。
* 若面板再改版：`/root/vylo-farm-backup/` 存了 v1 备份，回滚一行：
  `cp /root/vylo-farm-backup/vylo_farm.py.v1 vylo_farm.py && cp /root/vylo-farm-backup/farm.yml.v1 .github/workflows/farm.yml && cp /root/vylo-farm-backup/README.md.v1 README.md`
* 这是针对某奖励计划自身界面的个人自动化，请只用自己的账号跑。
