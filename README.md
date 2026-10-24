# switched.cloud Cloud-Token farmer (Vylo route)

Automates the "Earn with Vylo" sponsored-link flow on `panel.switched.cloud`, then
spends the farmed **Cloud Tokens** as extra VPS runtime (1 token = 1 day).

Verified live on 2026-10-23: 25/25 tokens in one run, ~90 s per token, balance
`50 cloud tokens` → runtime `2d 22h` → `52d 22h`.

## Why it needs a residential exit

Both the panel and `vylo.cc` refuse datacenter IPs:

```
Turn off your VPN or proxy — Vylo links can't be opened through a VPN, proxy, Tor or a server network.
```

GitHub-hosted runners are datacenter IPs, so a residential proxy is mandatory for the
Actions route (secret `PROXY`, e.g. `socks5://host:port`). Direct/DC runs simply return
`no vylo link`.

## Why the Turnstile click is weird

The widget is rendered inside a **closed shadow root**: `page.locator()` and
`querySelector()` cannot reach it, and there is no `cf-turnstile-response` node to read
until it is solved. The `.cf-turnstile` *container* still has a real bounding box, so the
script reads that box and dispatches **real CDP mouse events** (`Input.dispatchMouseEvent`)
at it — that consistently yields a ~773-char token.

After the captcha the page is a small state machine:
`Continue → countdown (/wait?t=…) → Unlock → Continue → countdown → Unlock → Get link`,
which redirects back to the panel where Vylo's postback credits the token.

## Usage

Local (headed browser under xvfb — the configuration that actually passes Turnstile):

```bash
pip install playwright && python -m playwright install chromium
export SW_PROXY=socks5://127.0.0.1:10807        # residential exit
python3 -u vylo_farm.py --count 25              # farm
python3 -u add_runtime.py                       # spend every token as runtime
```

Cookies come from either:

* `NOPROFIT_COOKIES` — the panel cookie JSON itself, raw or base64 (used in CI), or
* `NOPROFIT_COOKIE_FILE` — path to the cookie JSON (default `~/noprofit_cookies.json`).

Grab them once from a logged-in browser (DevTools → Application → Cookies →
`panel.switched.cloud`), export as a JSON array of `{name, value, domain, ...}`.

## GitHub Actions

`.github/workflows/farm.yml` is `workflow_dispatch` only. Secrets needed:

| secret | content |
| --- | --- |
| `NOPROFIT_COOKIES` | panel cookie JSON (raw or base64) |
| `PROXY` | residential proxy URL, e.g. `socks5://user:pass@host:port` |

Inputs: `count` (default 25 = the daily cap), `spend` (default true), `proxy` (override).

## Files

* `vylo_farm.py` — the farmer (`--count`, `--proxy`, `--max-fail`, `--headless`)
* `add_runtime.py` — spends the balance via the "Add runtime" modal (`--tokens`, `--dry-run`)
* `panelcookies.py` — cookie loading/saving shared by both

## Notes / limits

* 25 tokens per day per site; the counter resets at the panel's local midnight.
* `--headless` exists, but headed-under-xvfb is what has been tested against Turnstile.
* Runtime is a pure countdown: it drains whether or not the VPS is doing anything, and an
  expired VPS is deleted after a short grace window, so spend tokens before the deadline.
* This is a personal automation of a reward program's own UI; use it with your own account.
