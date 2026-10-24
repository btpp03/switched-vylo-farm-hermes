#!/usr/bin/env python3
"""Spend switched.cloud Cloud Tokens: +1 day runtime each ("Add runtime" modal).

Checked against the live panel (2026-10-23): /tokens -> button "Add runtime" opens a
modal with one number input (mountedActionSchema0.tokens) and a submit "Add runtime".

Usage:
  python3 add_runtime.py            # spend every token in the balance
  python3 add_runtime.py --tokens 7 # spend exactly 7
  python3 add_runtime.py --dry-run  # just print balance + runtime, spend nothing

Cookies: same as vylo_farm.py (NOPROFIT_COOKIES env, or a cookie JSON file).
"""
import argparse
import re
import sys
import time

from playwright.sync_api import sync_playwright

from panelcookies import load_cookies, save_cookies, proxy_from_env

PANEL = "https://panel.switched.cloud/tokens"


def body(p):
    try:
        return " ".join(p.evaluate("document.body.innerText").split())
    except Exception:
        return ""


def balance(text):
    m = re.search(r"(\d+) cloud tokens", text)
    return int(m.group(1)) if m else None


def runtime_line(text):
    m = re.search(r"Runtime\s+([0-9a-z ]+?)\s+lasts until\s+(\d{1,2} \w{3,9}, \d{2}:\d{2})", text)
    return f"Runtime {m.group(1)} lasts until {m.group(2)}" if m else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tokens", type=int, default=0, help="how many to spend; 0 = all")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--proxy", default=proxy_from_env())
    ap.add_argument("--headless", action="store_true")
    args = ap.parse_args()

    cookies = load_cookies()
    spent = None
    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=args.headless,
                                args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = br.new_context(viewport={"width": 1400, "height": 950}, locale="en-US",
                             proxy={"server": args.proxy} if args.proxy else None)
        ctx.add_cookies(cookies)
        page = ctx.new_page()
        page.goto(PANEL, wait_until="domcontentloaded", timeout=60000)
        time.sleep(4)
        text = body(page)
        bal = balance(text)
        print(f"balance: {bal}  |  {runtime_line(text)}", flush=True)
        if args.dry_run:
            br.close()
            return 0
        if not bal:
            print("nothing to spend")
            br.close()
            return 0
        n = bal if not args.tokens else min(args.tokens, bal)
        page.get_by_role("button", name="Add runtime").first.click()
        time.sleep(3)
        num = page.locator("input[type='number']").last
        num.fill(str(n))
        time.sleep(0.5)
        page.locator("button:has-text('Add runtime')").last.click()
        time.sleep(6)
        spent = n
        text = body(page)
        print(f"after: balance {balance(text)}  |  {runtime_line(text)}", flush=True)
        save_cookies(ctx.cookies())
        br.close()

    # re-read to get the updated header runtime
    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = br.new_context(viewport={"width": 1400, "height": 950}, locale="en-US",
                             proxy={"server": args.proxy} if args.proxy else None)
        ctx.add_cookies(cookies)
        page = ctx.new_page()
        page.goto(PANEL, wait_until="domcontentloaded", timeout=60000)
        time.sleep(3)
        print(f"verified: {runtime_line(body(page))}", flush=True)
        br.close()
    print(f"SUMMARY: spent {spent} token(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
