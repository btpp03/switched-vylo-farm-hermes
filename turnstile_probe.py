#!/usr/bin/env python3
"""Diagnose Turnstile solving inside CI without burning panel quota.

Opens a (already consumed) vylo.cc link or any Turnstile page and prints everything
needed to tell apart "widget never rendered" / "click went to the wrong place" /
"Cloudflare rejected the exit IP" / "browser env is detected as automation".

v2: adds fingerprint extras (unmasked WebGL, hwConcurrency, plugins, uaData) and
captures every Cloudflare challenge-platform network response, which is where CF
states *why* it refuses.

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


net = []          # (method, url, status)
net_bodies = []   # (url, body snippet)
pending = []


def on_response(r):
    try:
        u = r.url
    except Exception:
        return
    if not any(k in u for k in ("challenge-platform", "challenges.cloudflare.com",
                                "turnstile", "/cdn-cgi/")):
        return
    try:
        net.append((r.request.method, u[:160], r.status))
    except Exception:
        return
    if "/flow/" in u or "/pat/" in u or "turnstile" in u:
        pending.append(r)


with sync_playwright() as pw:
    br = pw.chromium.launch(headless=False, args=["--no-sandbox",
                                                  "--disable-blink-features=AutomationControlled",
                                                  "--disable-dev-shm-usage"])
    ctx = br.new_context(viewport={"width": 1366, "height": 900}, locale="en-US",
                         proxy={"server": a.proxy} if a.proxy else None)
    page = ctx.new_page()
    page.on("response", on_response)
    cdp = ctx.new_cdp_session(page)
    cdp.send("Emulation.setFocusEmulationEnabled", {"enabled": True})
    page.goto(a.url, wait_until="domcontentloaded", timeout=60000)
    time.sleep(6)

    env = page.evaluate("""() => {
        const out = {ua: navigator.userAgent, webdriver: navigator.webdriver,
            dpr: devicePixelRatio, inner: [innerWidth, innerHeight],
            outer: [outerWidth, outerHeight], screen: [screen.width, screen.height],
            vis: document.visibilityState,
            tz: Intl.DateTimeFormat().resolvedOptions().timeZone,
            lang: navigator.language, hc: navigator.hardwareConcurrency,
            plugins: navigator.plugins.length,
            brands: (navigator.userAgentData||{}).brands};
        try { const c = document.createElement('canvas');
              const g = c.getContext('webgl');
              const d = g.getExtension('WEBGL_debug_renderer_info');
              out.webgl = g.getParameter(g.VERSION);
              out.glvendor = d ? g.getParameter(d.UNMASKED_VENDOR_WEBGL) : null;
              out.glrender = d ? g.getParameter(d.UNMASKED_RENDERER_WEBGL) : null;
              const dbg = c.getContext('webgl').getExtension('WEBGL_debug_renderer_info');
              out.glrender = out.glrender;
        } catch(e) { out.webgl = 'ERR'; }
        try { out.audio = new (window.OfflineAudioContext||window.webkitOfflineAudioContext)(1,1,44100).sampleRate; }
        catch(e) { out.audio = 'ERR'; }
        return out;}""")
    log("ENV: " + json.dumps(env))
    try:
        ip = page.evaluate("""() => fetch('https://ipinfo.io/json').then(r=>r.json())
            .then(j=>j.ip+' '+j.org).catch(e=>'?')""")
    except Exception as e:
        ip = f"? ({e})"
    log("EXIT IP: " + ip)
    log("URL now: " + page.url)
    log("TEXT: " + " ".join(page.inner_text("body").split())[:220])
    for i, f in enumerate(page.frames):
        log(f"frame[{i}] {f.url[:140]}")
    log("iframes: " + json.dumps(page.evaluate("""() => [...document.querySelectorAll('iframe')]
        .map(f => {const b=f.getBoundingClientRect();
                   return {src:(f.src||'').slice(0,110), x:b.x, y:b.y, w:b.width, h:b.height};})""")))

    def toklen():
        return page.evaluate("""() => {const e=document.querySelector('[name=cf-turnstile-response]');
            return e && e.value ? e.value.length : 0;}""")

    solved = False
    for attempt in range(a.rounds):
        rect = page.evaluate("""() => {const e=document.querySelector('.cf-turnstile,[data-sitekey]');
            if(!e) return null; const b=e.getBoundingClientRect();
            return {x:b.x,y:b.y,w:b.width,h:b.height,
                    iframes:e.querySelectorAll('iframe').length, sr: !!e.shadowRoot};}""")
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

    # flush CF challenge-platform responses: this is the "why"
    for r in pending:
        try:
            body = r.text()[:400].replace("\n", " ")
        except Exception as e:
            body = f"<no body: {e}>"
        net_bodies.append((r.url[:120], body))
    log("CF NET: " + json.dumps(net[-25:]))
    for u, b in net_bodies[-12:]:
        log(f"  CF BODY {u} -> {b}")
    log("COOKIES: " + json.dumps({c["name"]: len(c["value"]) for c in ctx.cookies()}))

    shot = f"/tmp/turnstile_probe_{int(time.time())}.png"
    page.screenshot(path=shot, full_page=True)
    log("RESULT: " + ("SOLVED" if solved else "FAILED") + f" shot={shot}")
    br.close()
