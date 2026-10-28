#!/usr/bin/env python3
"""Farm switched.cloud Cloud Tokens through the Vylo sponsored link, in CI or locally.

Flow (all inside one browser context):
  1. open https://panel.switched.cloud/tokens with the stored session cookies
  2. click "Earn with Vylo"      -> the panel asks Vylo for a fresh one-time link
  3. follow that vylo.cc link    -> Turnstile checkbox sits in a closed shadow root, so the
     only reliable way to click it is by coordinates taken from the `.cf-turnstile`
     container rect (28px in from the left edge, vertically centred)
  4. walk the Vylo steps: Continue -> timer -> Unlock -> Continue -> timer -> Unlock -> Get link
  5. it redirects back to the panel and Vylo's postback credits 1 Cloud Token (= 2 days on a
     Plus account; the panel counter counts *links*, not tokens)

Nothing here spends tokens — "Add runtime" is a separate script (add_runtime.py).

usage:
  SW_PROXY=socks5://127.0.0.1:10804 xvfb-run -a python3 vylo_farm.py --count 25
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

CLICK_JS = r"""
(txt) => {
  const want = txt.toLowerCase().trim(); const cands = [];
  for (const e of document.querySelectorAll('button,a,[role=button],div,span')) {
    const r = e.getBoundingClientRect(); if (r.width < 2 || r.height < 2) continue;
    const t = (e.innerText || '').trim().replace(/\s+/g, ' '); if (!t || t.length > 120) continue;
    const lt = t.toLowerCase(); let score = 0;
    if (lt === want) score = 3; else if (lt.startsWith(want)) score = 2; else if (lt.includes(want)) score = 1;
    if (!score) continue;
    cands.push({e, score, kids: e.querySelectorAll('*').length, area: r.width * r.height});
  }
  if (!cands.length) return null;
  cands.sort((a, b) => b.score - a.score || a.kids - b.kids || a.area - b.area);
  const el = cands[0].e; el.scrollIntoView({block:'center'}); el.click();
  return (el.innerText||'').trim().replace(/\s+/g,' ').slice(0,40);
}
"""

# step machine: buttons only, exact-ish text, so the "3 Get link" breadcrumb is never hit
CLICK_BTN_JS = r"""
(txt) => {
  const want = txt.toLowerCase().trim();
  for (const e of document.querySelectorAll('button,[role=button]')) {
    const r = e.getBoundingClientRect();
    if (r.width < 2 || r.height < 2 || e.disabled) continue;
    const t = (e.innerText || '').trim().replace(/\s+/g, ' ').toLowerCase();
    if (t === want || (t.length <= 25 && t.includes(want))) {
      e.scrollIntoView({block: 'center'}); e.click();
      return (e.innerText || '').trim().replace(/\s+/g, ' ').slice(0, 40);
    }
  }
  return null;
}
"""

RECT_JS = r"""() => {const e=document.querySelector('.cf-turnstile,[data-sitekey]');
    if(!e) return null; const b=e.getBoundingClientRect();
    return {x:b.x,y:b.y,w:b.width,h:b.height};}"""

HIT_JS = """([x,y]) => {const e=document.elementFromPoint(x,y);
    return e ? (e.tagName + '.' + String(e.className).slice(0,40)) : 'none';}"""


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
            "()=>{const e=document.querySelector('[name=\"cf-turnstile-response\"]');return e?(e.value||'').length:-1}")
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


def balance(page):
    b = body(page)
    m = re.search(r"(\d+) cloud tokens", b)
    earned = re.findall(r"(\d+) of 25 earned today", b)
    return (int(m.group(1)) if m else None), earned


def solve_turnstile(page, cdp, log):
    """Click the checkbox; if that does not take, click the challenge iframe directly."""
    for rnd in range(8):
        r = page.evaluate(RECT_JS)
        if not (r and r["w"] > 5):
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
            # coordinate clicks are not landing (something covers the checkbox):
            # go through Playwright, which pierces the closed shadow root for us.
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


def earn_one(ctx, page, log):
    if not goto_retry(page, PANEL):
        log("panel unreachable")
        return False
    time.sleep(3)
    before, earn_before = balance(page)
    log(f"balance before: {before} {earn_before}")

    seen = []
    page.on("request", lambda r: seen.append(r.url))
    vurl = None
    for _ in range(3):
        page.evaluate(CLICK_JS, "Earn with Vylo")
        for _ in range(8):
            time.sleep(2)
            for u in seen:
                if "/static/" in u:
                    continue
                m = re.search(r"(https://vylo\.cc/[A-Za-z0-9]{4,})", u)
                if m:
                    vurl = m.group(1)
                    break
            if vurl:
                break
        if vurl:
            break
    if not vurl:
        log("no vylo link (panel refused / rate-limited?)")
        return False
    log(f"vylo link: {vurl}")

    if not goto_retry(page, vurl):
        log("vylo page unreachable")
        return False
    time.sleep(5)

    cdp = ctx.new_cdp_session(page)
    # CI runners have no window manager, so the page is never "focused" and Cloudflare
    # ignores synthetic clicks. Force the focus flag before touching the widget.
    try:
        cdp.send("Emulation.setFocusEmulationEnabled", {"enabled": True})
    except Exception as e:
        log(f"  focus emulation failed: {type(e).__name__}")
    log(f"  hasFocus={page.evaluate('document.hasFocus()')}")

    solved = solve_turnstile(page, cdp, log)
    log(f"turnstile: {'solved' if solved else 'FAILED'}")
    if not solved:
        try:
            page.screenshot(path=f"/tmp/vylo_turnstile_fail_{int(time.time())}.png", full_page=True)
            log(f"  url at fail: {page.url}")
            log(f"  text at fail: {body(page)[:160]}")
            log(f"  frames at fail: {[f.url[:70] for f in page.frames]}")
        except Exception as e:
            log(f"  diag failed: {type(e).__name__}")
        return False

    for i in range(22):
        txt = body(page)
        if "panel.switched.cloud" in page.url:
            log("back on panel")
            break
        clicked = None
        for lbl in ["Continue", "Unlock", "Get link", "Skip", "Next"]:
            clicked = page.evaluate(CLICK_BTN_JS, lbl)
            if clicked:
                break
        if i % 4 == 0:
            log(f"  step{i}: {page.url.split('/')[-1][:18]} :: {txt[:70]}")
        time.sleep(4)

    time.sleep(3)
    goto_retry(page, PANEL)
    time.sleep(3)
    after, earn_after = balance(page)
    log(f"balance after: {after} {earn_after}")
    return bool(after and before is not None and after > before)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=25, help="how many tokens to farm")
    ap.add_argument("--proxy", default=os.environ.get("SW_PROXY", "socks5://127.0.0.1:10804"))
    ap.add_argument("--max-fail", type=int, default=3, help="abort after N consecutive failures")
    ap.add_argument("--headless", action="store_true",
                    help="run headless (CI without xvfb); default is headed, which is what Turnstile likes")
    args = ap.parse_args()

    def log(msg):
        print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

    cookies = load_cookies()
    done = 0
    fails = 0
    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=args.headless, args=[
            "--no-sandbox", "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage"])
        ctx = br.new_context(viewport={"width": 1366, "height": 900}, locale="en-US",
                             proxy=proxy_cfg(args.proxy))
        ctx.add_cookies(cookies)
        page = ctx.new_page()
        try:
            while done < args.count and fails < args.max_fail:
                log(f"--- token {done + 1}/{args.count} (fails={fails}) ---")
                try:
                    ok = earn_one(ctx, page, log)
                except Exception as e:
                    log(f"error: {type(e).__name__}: {str(e)[:120]}")
                    ok = False
                if ok:
                    done += 1
                    fails = 0
                else:
                    fails += 1
                    time.sleep(8)
                save_cookies(ctx.cookies())
        finally:
            log(f"SUMMARY: farmed {done} token(s), {fails} consecutive failure(s)")
            br.close()
    return 0 if done else 1


if __name__ == "__main__":
    sys.exit(main())
