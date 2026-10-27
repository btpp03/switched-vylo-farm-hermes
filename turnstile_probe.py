#!/usr/bin/env python3
"""Diagnose Turnstile solving inside CI without burning panel quota.

Opens a (already consumed) vylo.cc link or any Turnstile page and prints everything
needed to tell apart "widget never rendered" / "click went to the wrong place" /
"Cloudflare rejected the exit IP" / "browser env is detected as automation".

usage: turnstile_probe.py [--url U] [--proxy socks5://127.0.0.1:10900]
"""
import argparse
import json
import os
import time

from playwright.sync_api import sync_playwright

ap = argparse.ArgumentParser()
ap.add_argument("--url", default="https://vylo.cc/z4dwU1")
ap.add_argument("--proxy", default=os.environ.get("SW_PROXY", "socks5://127.0.0.1:10900"))
ap.add_argument("--rounds", type=int, default=3)
a = ap.parse_args()


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


with sync_playwright() as pw:
    br = pw.chromium.launch(headless=False, args=["--no-sandbox",
                                                  "--disable-blink-features=AutomationControlled",
                                                  "--disable-dev-shm-usage"])
    ctx = br.new_context(viewport={"width": 1366, "height": 900}, locale="en-US",
                         proxy={"server": a.proxy} if a.proxy else None)
    page = ctx.new_page()
    cdp = ctx.new_cdp_session(page)
    cdp.send("Emulation.setFocusEmulationEnabled", {"enabled": True})
    page.goto(a.url, wait_until="domcontentloaded", timeout=60000)
    time.sleep(6)

    env = page.evaluate("""() => ({
        ua: navigator.userAgent, webdriver: navigator.webdriver, dpr: devicePixelRatio,
        inner: [innerWidth, innerHeight], outer: [outerWidth, outerHeight],
        screen: [screen.width, screen.height], vis: document.visibilityState,
        tz: Intl.DateTimeFormat().resolvedOptions().timeZone, lang: navigator.language,
        webgl: (()=>{try{const c=document.createElement('canvas').getContext('webgl');
            return c ? c.getParameter(c.VERSION) : null;}catch(e){return 'ERR'}})(),
    })""")
    log("ENV: " + json.dumps(env))
    try:
        ip = page.evaluate("""() => fetch('https://ipinfo.io/json').then(r=>r.json())
            .then(j=>j.ip+' '+j.org).catch(e=>'?')""")
    except Exception as e:
        ip = f"? ({e})"
    log("EXIT IP: " + ip)
    log("URL now: " + page.url)
    log("TEXT: " + " ".join(page.inner_text("body").split())[:200])

    def toklen():
        return page.evaluate("""() => {const e=document.querySelector('[name=cf-turnstile-response]');
            return e && e.value ? e.value.length : 0;}""")

    solved = False
    for attempt in range(a.rounds):
        rect = page.evaluate("""() => {const e=document.querySelector('.cf-turnstile,[data-sitekey]');
            if(!e) return null; const b=e.getBoundingClientRect();
            const host=e.querySelector('iframe')||e;
            return {x:b.x,y:b.y,w:b.width,h:b.height,
                    iframes:e.querySelectorAll('iframe').length,
                    sr: !!e.shadowRoot};}""")
        log(f"attempt {attempt}: widget={rect} frames={page.frames.__len__()}")
        if not rect or rect["w"] < 5:
            time.sleep(5)
            continue
        for frac in (28, 150, 220):
            x, y = rect["x"] + frac, rect["y"] + rect["h"] / 2
            top = page.evaluate("([x,y]) => {const e=document.elementFromPoint(x,y);"
                                "return e ? e.tagName+'.'+(e.className||'') : null;}", [x, y])
            log(f"  click {x:.0f},{y:.0f} top={top}")
            for t in ("mouseMoved", "mousePressed", "mouseReleased"):
                cdp.send("Input.dispatchMouseEvent", {"type": t, "x": x, "y": y,
                                                      "button": "left", "clickCount": 1})
            for _ in range(12):
                time.sleep(2)
                n = toklen()
                if n:
                    log(f"  TOKEN len={n}")
                    solved = True
                    break
            if solved:
                break
        if solved:
            break
    shot = f"/tmp/turnstile_probe_{int(time.time())}.png"
    page.screenshot(path=shot, full_page=True)
    log("RESULT: " + ("SOLVED" if solved else "FAILED") + f" shot={shot}")
    br.close()
