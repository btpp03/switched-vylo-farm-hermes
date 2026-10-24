#!/usr/bin/env python3
"""switched.cloud Cloud-Token farmer (Vylo route).

Flow per token (all verified working, 2026-10-23):
  1. open panel.switched.cloud/tokens with the saved session cookies (residential exit)
  2. click "Earn with Vylo"  -> the panel asks Vylo for a fresh one-time link
     (the link shows up as a network request to https://vylo.cc/<code>)
  3. open that link top-level, because the Turnstile widget is rendered inside a
     closed shadow root: no locator / querySelector can reach it. The `.cf-turnstile`
     container's bounding box is exact though, so we dispatch REAL CDP mouse events there.
  4. walk the Vylo steps: Continue -> timer -> Unlock -> Continue -> timer -> Unlock -> Get link
  5. it redirects back to the panel and Vylo's postback credits 1 Cloud Token (= 1 day runtime)

Usage:
  SW_PROXY=socks5://127.0.0.1:10807 python3 vylo_farm.py --count 25
  python3 vylo_farm.py --count 3 --proxy socks5://127.0.0.1:10807
"""
import argparse
import json
import os
import re
import sys
import time

from playwright.sync_api import sync_playwright

from panelcookies import load_cookies, save_cookies

PANEL = "https://panel.switched.cloud/tokens"

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

CLICK_BTN_JS = r"""
(txt) => {
  const want = txt.toLowerCase().trim();
  for (const e of document.querySelectorAll('button,[role=button]')) {
    const r = e.getBoundingClientRect();
    if (r.width < 2 || r.height < 2 || e.disabled) continue;
    const t = (e.innerText || '').trim().replace(/\s+/g, ' ').toLowerCase();
    if (t === want || (t.length <= 25 && t.includes(want))) {
      e.scrollIntoView({block: 'center'}); e.click();
      return (e.innerText || '').trim().replace(/\s+/g, ' ');
    }
  }
  return null;
}
"""


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
    for i in range(tries):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            return True
        except Exception as e:
            print(f"    goto retry {i}: {type(e).__name__}", flush=True)
            time.sleep(5)
    return False


def balance(page):
    m = re.search(r"(\d+) cloud tokens", body(page))
    earned = re.findall(r"(\d+) of 25 earned today", body(page))
    return (int(m.group(1)) if m else None), earned


def earn_one(ctx, page, log):
    """Returns True if a token was credited."""
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
    solved = False
    for _ in range(6):
        r = page.evaluate("""() => {const e=document.querySelector('.cf-turnstile,[data-sitekey]');
            if(!e) return null; const b=e.getBoundingClientRect();
            return {x:b.x,y:b.y,w:b.width,h:b.height};}""")
        if r and r["w"] > 5:
            click_at(cdp, r["x"] + 28, r["y"] + r["h"] / 2)
        for _ in range(8):
            time.sleep(2)
            if toklen(page) > 10:
                solved = True
                break
        if solved:
            break
    log(f"turnstile: {'solved' if solved else 'FAILED'}")
    if not solved:
        try:
            page.screenshot(path=f"/tmp/vylo_turnstile_fail_{int(time.time())}.png", full_page=True)
            log(f"  url at fail: {page.url}")
            log(f"  text at fail: {body(page)[:160]}")
            r = page.evaluate("""() => {const e=document.querySelector('.cf-turnstile,[data-sitekey]');
                if(!e) return null; const b=e.getBoundingClientRect();
                return {x:b.x,y:b.y,w:b.width,h:b.height,vis:getComputedStyle(e).visibility};}""")
            log(f"  widget rect: {r} viewport={page.viewport_size}")
        except Exception as e:
            log(f"  diag failed: {type(e).__name__}")
        return False

    # walk the steps until it sends us back to the panel
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
    ok = bool(after and before is not None and after > before)
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=25, help="how many tokens to farm")
    ap.add_argument("--proxy", default=os.environ.get("SW_PROXY", "socks5://127.0.0.1:10807"))
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
        br = pw.chromium.launch(headless=args.headless, args=["--no-sandbox",
                                                      "--disable-blink-features=AutomationControlled",
                                                      "--disable-dev-shm-usage"])
        ctx = br.new_context(viewport={"width": 1366, "height": 900}, locale="en-US",
                             proxy={"server": args.proxy} if args.proxy else None)
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
