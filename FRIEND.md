# 给你的朋友：怎么把这个仓库跑起来

不需要懂代码，也不需要装任何东西，全部在网页上点。
唯一的前提：**你自己的 switched.cloud 账号** + **一条住宅代理**（机房 IP 一定失败，和用什么协议无关）。

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
4. 找到这两行：
   - `switched_cloud_session`
   - `remember_web_59ba36addc2...`（名字后面带一串 hash）

**只替换两个 `value`，其余字符一个都别动**。`remember_web_` 后面的 hash 要照抄你浏览器里那行的
完整名字（一般和上面一致，但以你看到的为准）。

```json
[{"name":"switched_cloud_session","value":"①换成 switched_cloud_session 的 Value","domain":"panel.switched.cloud","path":"/","secure":true,"httpOnly":true},
 {"name":"remember_web_59ba36addc2...","value":"②换成 remember_web 的 Value","domain":"panel.switched.cloud","path":"/","secure":true,"httpOnly":true}]
```

真实的值都很长、中间没有空格；看到 `%3D` 这类编码字符原样保留，别解码。

嫌手动拼麻烦就装浏览器扩展 **Cookie-Editor**：打开面板页 → 点扩展 → **Export** → 选 **JSON**，
整段复制即可（多余的 cookie 无害，脚本只认这两条）。

> 这两个 cookie 是 HttpOnly，Console 里 `document.cookie` 读不到，别走那条路。

---

## 第 4 步：准备住宅代理（SB_CONFIG）

面板和 vylo.cc 都会拒绝机房 IP。**站点看的是出口 IP 归属，不看协议**，
所以 vmess / trojan / ss 都一样，只要是家宽出口就行；反过来，机房 VPS 挂什么协议都白搭。

### 协议怎么选

| 你手上是什么 | `outbounds.type` |
| --- | --- |
| `socks5://ip:port`（推荐，字段最少） | `socks` |
| `http://ip:port` 或 `https://` | `http` |
| ss 节点 | `shadowsocks` |
| vmess 节点 | `vmess` |
| trojan 节点 | `trojan` |
| 节点带 TLS（hysteria2 / tuic） | `hysteria2` / `tuic`，需要 `tls` 段 |

### 硬要求

- `inbounds` 里必须有一个 **socks 入站，`listen_port` = 10807**（脚本写死了这个端口）
- `route.final` 必须等于出口的 `tag`（下面都叫 `home`）
- 一个出口就够了，不需要配多条

### 模板：住宅 socks5

```json
{"log":{"level":"warn"},
 "inbounds":[{"type":"socks","tag":"in","listen":"127.0.0.1","listen_port":10807}],
 "outbounds":[{"type":"socks","tag":"home","server":"住宅代理IP","server_port":1080,
               "version":"5","username":"用户名","password":"密码"}],
 "route":{"final":"home"}}
```

没有账号密码就删掉 `username`、`password` 两行。

### 模板：住宅 http 代理

```json
{"log":{"level":"warn"},
 "inbounds":[{"type":"socks","tag":"in","listen":"127.0.0.1","listen_port":10807}],
 "outbounds":[{"type":"http","tag":"home","server":"住宅代理IP","server_port":8080,
               "username":"用户名","password":"密码"}],
 "route":{"final":"home"}}
```

### 模板：shadowsocks 节点

```json
{"log":{"level":"warn"},
 "inbounds":[{"type":"socks","tag":"in","listen":"127.0.0.1","listen_port":10807}],
 "outbounds":[{"type":"shadowsocks","tag":"home","server":"节点IP","server_port":8388,
               "method":"aes-256-gcm","password":"密码"}],
 "route":{"final":"home"}}
```

### 模板：trojan（带 TLS）

```json
{"log":{"level":"warn"},
 "inbounds":[{"type":"socks","tag":"in","listen":"127.0.0.1","listen_port":10807}],
 "outbounds":[{"type":"trojan","tag":"home","server":"节点域名","server_port":443,
               "password":"密码","tls":{"enabled":true,"server_name":"节点域名"}}],
 "route":{"final":"home"}}
```

### 模板：vless（+TLS）

```json
{"log":{"level":"warn"},
 "inbounds":[{"type":"socks","tag":"in","listen":"127.0.0.1","listen_port":10807}],
 "outbounds":[{"type":"vless","tag":"home","server":"节点域名","server_port":443,
               "uuid":"你的UUID",
               "tls":{"enabled":true,"server_name":"节点域名"}}],
 "route":{"final":"home"}}
```

### 模板：vless + Vision（xtls-rprx-vision）

```json
{"log":{"level":"warn"},
 "inbounds":[{"type":"socks","tag":"in","listen":"127.0.0.1","listen_port":10807}],
 "outbounds":[{"type":"vless","tag":"home","server":"节点域名","server_port":443,
               "uuid":"你的UUID","flow":"xtls-rprx-vision",
               "tls":{"enabled":true,"server_name":"节点域名"}}],
 "route":{"final":"home"}}
```

### 模板：vless + WS + TLS（常见 CDN 节点）

```json
{"log":{"level":"warn"},
 "inbounds":[{"type":"socks","tag":"in","listen":"127.0.0.1","listen_port":10807}],
 "outbounds":[{"type":"vless","tag":"home","server":"节点域名","server_port":443,
               "uuid":"你的UUID",
               "transport":{"type":"ws","path":"/ray","headers":{"Host":"节点域名"}},
               "tls":{"enabled":true,"server_name":"节点域名"}}],
 "route":{"final":"home"}}
```

### 模板：vless + Reality

```json
{"log":{"level":"warn"},
 "inbounds":[{"type":"socks","tag":"in","listen":"127.0.0.1","listen_port":10807}],
 "outbounds":[{"type":"vless","tag":"home","server":"节点IP或域名","server_port":443,
               "uuid":"你的UUID","flow":"xtls-rprx-vision",
               "tls":{"enabled":true,"server_name":"伪装域名，如 www.microsoft.com",
                      "utls":{"enabled":true,"fingerprint":"chrome"},
                      "reality":{"enabled":true,"public_key":"你的PUBLIC_KEY","short_id":"shortId"}}}],
 "route":{"final":"home"}}
```

Reality 的 `public_key` 必须是**真实的那串 43 位 base64url 字符**（从节点链接的 `pbk=` 取）。
随便填一个词会直接报 `FATAL: initialize outbound: invalid public_key`，这一条踩过。
`short_id` 没配就删掉这一行。

### 模板：vmess + WS + TLS

```json
{"log":{"level":"warn"},
 "inbounds":[{"type":"socks","tag":"in","listen":"127.0.0.1","listen_port":10807}],
 "outbounds":[{"type":"vmess","tag":"home","server":"节点域名","server_port":443,
               "uuid":"你的UUID","security":"auto","alter_id":0,
               "transport":{"type":"ws","path":"/ray","headers":{"Host":"节点域名"}},
               "tls":{"enabled":true,"server_name":"节点域名"}}],
 "route":{"final":"home"}}
```

> 注意：vless / vmess / trojan / ss 这类节点**出口 IP 基本都是机房**，vylo.cc 会直接拒。
> 它们只适合「上游是家宽落地」的场景（比如你的节点出口本身是住宅 IP）。
> 纯粹的机房节点填进来也跑不出 token。

### 自检（可选）

装个 sing-box 同款版本，本地校验语法，能省掉一轮瞎跑：

```bash
sing-box check -c sb.json      # 无输出 = 格式正确
```

上面四种模板已在 **sing-box 1.14.1**（workflow 用的就是这个版本）上逐个 `check` 通过，
并用 `curl --socks5-hostname 127.0.0.1:10807` 实测出网正常。

---

## 第 5 步：加两个 secret

你的 fork → **Settings** → 左侧 **Secrets and variables** → **Actions** →
右上 **New repository secret**，加两条（名字必须完全一致，区分大小写）：

| Name | Secret |
| --- | --- |
| `NOPROFIT_COOKIES` | 第 3 步的 cookie JSON |
| `SB_CONFIG` | 第 4 步的 sing-box 配置 JSON |

只需要这两个，别的不用填。

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

| 现象 | 原因 |
| --- | --- |
| `no vylo link (panel refused / rate-limited?)` | 三种可能：cookie 失效（面板会跳登录）、住宅出口没起、或当天 25 个已刷满（`of 25 earned today` 到 25） |
| 日志只有 `proxy: socks5://127.0.0.1:10807`，没有 `residential exit ip` | SB_CONFIG 里的代理连不上；查 IP、端口、账号密码、协议类型对不对 |
| 报 secret 未定义 / 空值 | secret 名字拼错（要 `NOPROFIT_COOKIES`、`SB_CONFIG`），或值是空字符串 |
| `sing-box` 启动即退出 | 配置 JSON 语法错（尾逗号、注释、单引号） |
| Actions 页面没有 `farm-cloud-tokens` | 第 2 步没启用 workflow |

## 别做的事

- 不要把别人的仓库加 collaborator 来共享 secret —— 有写权限的人可以改 workflow 把 secret 打出来。要给别人用就 fork。
- 不要用自己的机房 VPS 当出口，vylo.cc 会直接拒。
- 一个账号一天上限 25 个，刷满后面板就不给链接了，这是正常的，不是坏了。
