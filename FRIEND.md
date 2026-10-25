# 给你的朋友：怎么把这个仓库跑起来

不需要懂代码，也不需要装任何东西，全部在网页上点。
唯一的前提：**你自己的 switched.cloud 账号** + **一条住宅代理**（机房 IP 一定失败）。

---

## 第 0 步：先确认面板能用

打开 https://panel.switched.cloud/tokens ，登录后确认页面上有 **Earn with Vylo** 按钮和
`X cloud tokens`、`X of 25 earned today` 这两个数字。看不到就不要往下走了。

---

## 第 1 步：Fork 仓库

在 https://github.com/btpp03/switched-vylo-farm-hermes 点右上角 **Fork** → **Create fork**。
之后所有操作都在**你自己账号下的那份 fork** 里做。

---

## 第 2 步：启用 Actions

进入你的 fork，点顶部 **Actions** 标签。会有一条蓝色提示问你确认启用 workflow，
点 **I understand my workflows, go ahead and enable them**。
不点这一步，任何东西都不会跑。

---

## 第 3 步：拿面板 cookie

1. 浏览器登录 https://panel.switched.cloud
2. 按 **F12** 打开开发者工具
3. 切到 **Application** 标签（Firefox 叫 **Storage**）→ 左侧 **Cookies** → `https://panel.switched.cloud`
4. 需要两条：
   - `switched_cloud_session`，值形如 `eyJpdiI6...`
   - `remember_web_59ba36addc2...`（名字后面那串 hash 必须和网站上完全一致）
5. 把这两条拼成下面这个 JSON（把 `<...>` 换成真实值）：

```json
[{"name":"switched_cloud_session","value":"<v1>","domain":"panel.switched.cloud","path":"/","secure":true,"httpOnly":true},
 {"name":"remember_web_59ba36addc2...","value":"<v2>","domain":"panel.switched.cloud","path":"/","secure":true,"httpOnly":true}]
```

嫌麻烦就装浏览器扩展 **Cookie-Editor**：打开面板页 → 点扩展 → **Export** → 选 **JSON**，
整段复制即可（多余的 cookie 无害）。

> 注意：这两个 cookie 是 HttpOnly，Console 里 `document.cookie` 读不到，别走那条路。

---

## 第 4 步：准备住宅代理（SB_CONFIG）

面板和 vylo.cc 都会拒绝机房 IP，所以必须走住宅出口。你需要一条住宅 socks5 或 http 代理，
然后写成 sing-box 配置：

```json
{"log":{"level":"warn"},
 "inbounds":[{"type":"socks","tag":"in","listen":"127.0.0.1","listen_port":10807}],
 "outbounds":[{"type":"socks","tag":"home","server":"住宅代理IP","server_port":1080,
               "username":"用户名","password":"密码"}],
 "route":{"final":"home"}}
```

出口是 http 代理就把 `outbounds.type` 改成 `"http"`。
整段 JSON 就是 `SB_CONFIG` 的值。

---

## 第 5 步：加两个 secret

你的 fork → **Settings** → 左侧 **Secrets and variables** → **Actions** →
右上 **New repository secret**，加两条：

| Name | Secret |
| --- | --- |
| `NOPROFIT_COOKIES` | 第 3 步的 cookie JSON |
| `SB_CONFIG` | 第 4 步的 sing-box 配置 JSON |

---

## 第 6 步：跑

**Actions** → 左侧 `farm-cloud-tokens` → 右侧 **Run workflow**：
- `count` 填 `25`（每日上限）
- `spend` **不勾**（先只赚不花）

点绿色 **Run workflow**。点进这次运行看日志，正常应该看到：

```
residential exit ip: 1.2.3.4          <- 住宅出口通了
balance before: 0 ['0']
vylo link: https://vylo.cc/xxxxxx      <- 拿到链接，开始过验证码
SUMMARY: farmed N token(s)
```

一次大约 90 秒一个，25 个约 40 分钟。1 token = 1 天运行时长。

---

## 第 7 步：把 token 换成时长

**Actions** → `Run workflow` 这次勾上 `spend`，跑完就会把余额全部转成 VPS 运行时长。

---

## 出问题看这里

| 日志 | 原因 |
| --- | --- |
| `no vylo link (panel refused / rate-limited?)` | 三种可能：cookie 失效（面板会跳登录）、住宅出口没起（看不到 `residential exit ip`）、或当天 25 个已刷满（`of 25 earned today` 到 25） |
| `proxy: socks5://127.0.0.1:10807` 但后面没有 `residential exit ip` | SB_CONFIG 里的代理连不上，检查 IP/端口/账号密码 |
| 直接报 `NOPROFIT_COOKIES` 相关错误 | secret 名字拼错，或值是空的 |
| Actions 页面没有 `farm-cloud-tokens` | 第 2 步没启用 workflow |

## 别做的事

- 不要把别人的仓库加 collaborator 来共享 secret —— 有写权限的人可以改 workflow 把 secret 打出来。要给别人用就 fork。
- 不要用自己的机房 VPS 当出口，vylo.cc 会直接拒。
