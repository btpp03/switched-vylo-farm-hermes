#!/usr/bin/env python3
"""Farm switched.cloud Cloud Tokens AFTER the v2.0 panel redesign (Vylo route removed).

New panel (v2.0.2) earn routes:
  * Daily streak  - no button: server credits 0.25 (->1 on day 7) just for opening /tokens.
                    One claim/day, so a single daily visit is all this script needs for it.
  * Cuty          - 1 Cloud Token / link, 2 links/day. This is the automatable route:
      POST /tokens/earn (provider=cuty) -> 302 to cuty.io/<short>
      -> cuttty.com: click "Continue" -> Cloudflare Turnstile checkbox
      -> solve via CDP coordinate clicks (same shadow-root trick as the old Vylo script)
      -> click "I am not a robot" -> "preparing" -> click the "Go ..." button
      -> the page redirects back to panel.switched.cloud and the postback credits +1.
  * Linkvertise   - 1.5/link, 10/day, but the free path hides behind hcaptcha + a
                    subscription/3-ad wall. Not automatable on a datacenter runner; SKIPPED.

A residential exit is still required: the Turnstile on cuttty.com rejects datacenter IPs
exactly like Vylo did. Keep using secret HOME_VLESS_URL / the local sing-box relay.

usage:
  SW_PROXY=socks5://127.0.0.1:10900 xvfb-run -a python3 vylo_farm.py --count 25
env:
  NOPROFIT_COOKIES   base64 or raw JSON cookie list (CI); else ~/noprofit_cookies.json
"""
import argparse
import json
import os
import re
import sys
import time

from playwright.sync_api import sync_playwright

from panelcookies import load_cookies, save_cookies

PANEL = os.environ.get("SW_PANEL", "https://panel.switched.cloud/tokens")
# Daily hard caps enforced by the panel; --count only bounds how many we *attempt*.
CUTY_CAP = 2

RECT_JS = r"""() => {const e=document.querySelector('.cf-turnstile,[data-sitekey]');
    if(!e) return null; const b=e.getBoundingClientRect();
    return {x:b.x,y:b.y,w:b.width,h:b.height};}"""
HIT_JS = """([x,y]) => {const e=document.elementFromPoint(x,y);
    return e ? (e.tagName + '.' + String(e.className).slice(0,40)) : 'none';}"""

# Loose substring button clicker for the Cuty ad chain. Never touches paid paths.
CLICK_BTN_JS = r"""(want) => {
  const w = want.toLowerCase();
  const BAD = /premium|trial|subscribe|charge|9\.99|59\.99|skip all ads|become a/i;
  for (const e of document.querySelectorAll('button,[role=button],input[type=submit],a[href]')) {
    const r = e.getBoundingClientRect();
    if (r.width < 2 || r.height < 2 || e.disabled) continue;
    const t = (e.innerText || e.value || '').trim().replace(/\s+/g,' ').toLowerCase();
    if (!t || t.length > 40 || BAD.test(t)) continue;
    if (t.includes(w)) {
      e.scrollIntoView({block:'center'}); e.click();
      return t.slice(0, 40);
    }
  }
  return null;
}"""

ADVANCE_WORDS = ["go", "get link", "continue", "unlock", "next", "proceed",
                 "click here", "visit", "i am not a robot", "verify", "submit"]


def proxy_cfg(url):
    if not url:
        return None
    from urllib.parse import urlparse, unquote
    u = urlparse(url)
    cfg = {"server": f"{u.scheme}://{u.hostname}:{u.port}"}
    if u.username:
        cfg["username"] = unquote(u.username)
        cfg["password"] = unquote(u.password or "")
    return cfg


def body(p):
    try:
        return " ".join(p.evaluate("document.body.innerText").split())
    except Exception:
        return ""


def toklen(p):
    try:
        return p.evaluate(
            "()=>{const e=document.querySelector('[name=\"cf-turnstile-response\"]');"
            "return e?(e.value||'').length:-1}")
    except Exception:
        return -1


def click_at(cdp, x, y):
    for t, ex in (("mouseMoved", {"x": x, "y": y}),
                  ("mousePressed", {"x": x, "y": y, "button": "left", "clickCount": 1}),
                  ("mouseReleased", {"x": x, "y": y, "button": "left", "clickCount": 1})):
        cdp.send("Input.dispatchMouseEvent", dict({"type": t}, **ex))
        time.sleep(0.18)


def goto_retry(page, url, tries=4):
    """home residential exits throw transient net::ERR_CONNECTION_CLOSED - just retry."""
    for i in range(tries):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            return True
        except Exception as e:
            print(f"    goto retry {i}: {type(e).__name__}", flush=True)
            time.sleep(5)
    return False


def read_state(page):
    """Parse the v2 panel: integer balance, Cuty/Linkvertise daily usage, streak."""
    t = body(page)
    bal = re.search(r"(\d+) cloud tokens", t)
    cuty = re.search(r"(\d+) of 2 today", t)
    lv = re.search(r"(\d+) of 10 today", t)
    claimed = "Claimed today" in t
    return {
        "bal": int(bal.group(1)) if bal else None,
        "cuty": int(cuty.group(1)) if cuty else None,
        "lv": int(lv.group(1)) if lv else None,
        "claimed": claimed,
    }


def solve_turnstile(page, cdp, log):
    """Click the checkbox; if that does not take, click the challenge iframe directly."""
    for rnd in range(8):
        r = page.evaluate(RECT_JS)
        if not (r and r["w"] > 5 and r["h"] > 5):
            log(f"  widget not rendered yet: {r}")
            time.sleep(2)
            continue
        x, y = r["x"] + 28, r["y"] + r["h"] / 2
        hit = page.evaluate(HIT_JS, [x, y])
        log(f"  round {rnd}: rect={r} click {x:.0f},{y:.0f} top={hit}")
        click_at(cdp, x, y)
        for _ in range(8):
            time.sleep(2)
            if toklen(page) > 10:
                log(f"  token len {toklen(page)}")
                return True
        if rnd == 2:
            for fr in page.frames:
                if "challenges.cloudflare.com" not in (fr.url or ""):
                    continue
                try:
                    fr.frame_element().click(force=True, timeout=8000)
                    log("  fallback: clicked challenge iframe element")
                except Exception as e:
                    log(f"  fallback click failed: {type(e).__name__}: {str(e)[:80]}")
                break
    return False


def earn_cuty(ctx, panel_page, log):
    """Complete ONE Cuty sponsored link. Returns True if the panel credits it."""
    # 1. get a fresh short link from the panel (POST /tokens/earn)
    form = panel_page.evaluate("""()=>{
      const f=[...document.querySelectorAll('form')].find(x=>/tokens\\/earn/.test(x.action));
      if(!f) return null;
      const g=n=>f.querySelector(`input[name=${n}]`)?.value;
      return {action:f.action, token:g('_token')};
    }""")
    if not form or not form.get("token"):
        log("  no /tokens/earn form (quota exhausted / markup changed?)")
        return False
    try:
        r = ctx.request.post(form["action"],
                             form={"_token": form["token"], "provider": "cuty"},
                             max_redirects=0, timeout=30000)
        cu = r.headers.get("location")
    except Exception as e:
        log(f"  earn POST failed: {type(e).__name__}: {str(e)[:100]}")
        return False
    if not cu or "cuty" not in cu:
        log(f"  unexpected earn redirect: {cu}")
        return False
    log(f"  cuty link: {cu}")

    # 2. walk the cutty.com chain in its own page (panel page stays for verification)
    q = ctx.new_page()
    try:
        if not goto_retry(q, cu):
            log("  cutty page unreachable")
            return False
        time.sleep(5)
        cdp = ctx.new_cdp_session(q)
        try:
            cdp.send("Emulation.setFocusEmulationEnabled", {"enabled": True})
        except Exception:
            pass

        # step A: first "Continue" -> captcha page
        q.evaluate("""()=>{const b=document.getElementById('submit-button')||
            [...document.querySelectorAll('button')].find(x=>/continue/i.test(x.innerText||''));
            if(b)b.click()}""")
        time.sleep(6)

        # step B: solve the Cloudflare Turnstile checkbox
        if not solve_turnstile(q, cdp, log):
            log("  turnstile: FAILED")
            try:
                q.screenshot(path=f"/tmp/cuty_fail_{int(time.time())}.png", full_page=True)
            except Exception:
                pass
            return False
        log("  turnstile: solved")

        # step C: submit + advance through "preparing" until it redirects back to the panel
        for i in range(20):
            if "panel.switched.cloud" in q.url:
                log("  back on panel")
                break
            txt = body(q)
            # re-solve a fresh turnstile if the ad chain raises another one
            if q.evaluate("!!document.querySelector('.cf-turnstile,[data-sitekey]')") \
                    and toklen(q) < 10 and i % 4 == 0:
                solve_turnstile(q, cdp, log)
            for w in ADVANCE_WORDS:
                hit = q.evaluate(CLICK_BTN_JS, w)
                if hit:
                    if i % 2 == 0:
                        log(f"  step{i}: clicked '{hit}'")
                    break
            if i % 4 == 0:
                log(f"  step{i}: {q.url.split('/')[-1][:20]} :: {txt[:60]}")
            time.sleep(4)

        back = "panel.switched.cloud" in q.url
        log(f"  {'redirected back' if back else 'NO redirect'} (last url {q.url[:70]})")
        return back
    finally:
        try:
            q.close()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=25,
                    help="max Cuty links to attempt (hard panel cap is 2/day)")
    ap.add_argument("--proxy", default=os.environ.get("SW_PROXY", "socks5://127.0.0.1:10900"))
    ap.add_argument("--max-fail", type=int, default=3, help="abort after N consecutive failures")
    ap.add_argument("--headless", action="store_true",
                    help="run headless; default is headed (xvfb), which Turnstile likes")
    args = ap.parse_args()

    def log(msg):
        print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

    cookies = load_cookies()
    done = 0
    fails = 0
    st = {}
    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=args.headless, args=[
            "--no-sandbox", "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage"])
        ctx = br.new_context(viewport={"width": 1366, "height": 900}, locale="en-US",
                             proxy=proxy_cfg(args.proxy))
        ctx.add_cookies(cookies)
        page = ctx.new_page()
        try:
            log("open panel (also claims the daily streak)")
            if not goto_retry(page, PANEL):
                log("panel unreachable")
                return 1
            time.sleep(4)
            st = read_state(page)
            log(f"state: {st}")

            # how many Cuty links are still available today
            remaining = CUTY_CAP - (st["cuty"] if st["cuty"] is not None else CUTY_CAP)
            if remaining <= 0:
                log("Cuty daily cap already used (2/2) - nothing to farm")
            target = min(args.count, remaining)
            log(f"will attempt up to {target} Cuty link(s)")

            while done < target and fails < args.max_fail:
                log(f"--- cuty {done + 1}/{target} (fails={fails}) ---")
                try:
                    ok = earn_cuty(ctx, page, log)
                except Exception as e:
                    log(f"error: {type(e).__name__}: {str(e)[:120]}")
                    ok = False
                # refresh panel to read the authoritative quota/balance
                goto_retry(page, PANEL)
                time.sleep(3)
                after = read_state(page)
                credited = (after["cuty"] is not None and st["cuty"] is not None
                            and after["cuty"] > st["cuty"])
                log(f"  quota {st['cuty']}->{after['cuty']} balance {st['bal']}->{after['bal']} "
                    f"credited={credited}")
                st = after
                if ok and credited:
                    done += 1
                    fails = 0
                else:
                    fails += 1
                    time.sleep(8)
                save_cookies(ctx.cookies())
        finally:
            log(f"SUMMARY: farmed {done} Cuty link(s), {fails} consecutive failure(s), "
                f"final {st}")
            br.close()
    # 正常收尾一律算成功：当天配额已满、刷 0 条、刷到 N 条，都是正常日。
    # 只有「面板连不上」(上面直接 return 1) 或「连续失败到 max-fail」才算失败，
    # 否则 GA 会标红并短路跳过后面的 spend 换时长步骤，保活反而断在这里。
    return 1 if fails >= args.max_fail else 0


if __name__ == "__main__":
    sys.exit(main())
