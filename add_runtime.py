#!/usr/bin/env python3
"""花掉 switched.cloud 的 Cloud Token：+1 天运行时长/个。

面板实测（2026-10-24）：/tokens 页上的 "Add runtime" 是 Livewire 动作，点开后弹窗里
只有一个 number 输入（mountedActionSchema0.tokens），再点弹窗里的 "Add runtime" 提交。
弹窗有时几秒才渲染出输入框，且页面上可能只有一个候选按钮，所以这里逐个候选点击并轮询
number 输入是否出现，而不是盲点一次就填。

用法：
  python3 add_runtime.py            # 把余额全部换成时长
  python3 add_runtime.py --tokens 7 # 只换 7 个
  python3 add_runtime.py --dry-run  # 只读余额与时长，不花钱

Cookie 来源与 vylo_farm.py 一致（NOPROFIT_COOKIES 环境变量或 cookie JSON 文件）。
"""
import argparse
import os
import re
import sys
import time

from playwright.sync_api import sync_playwright

from panelcookies import load_cookies, save_cookies, proxy_from_env

PANEL = "https://panel.switched.cloud/tokens"
CAND_JS = """()=>[...document.querySelectorAll('button,a,[role=button]')]
  .filter(e=>/add runtime/i.test(e.innerText||''))
  .map((e,i)=>{const r=e.getBoundingClientRect();
     return {i,tag:e.tagName,txt:(e.innerText||'').trim().slice(0,20),w:Math.round(r.width),h:Math.round(r.height)}})"""
CLICK_I_JS = """(i)=>{const els=[...document.querySelectorAll('button,a,[role=button]')]
  .filter(e=>/add runtime/i.test(e.innerText||''));const el=els[i];if(!el)return false;
  el.scrollIntoView({block:'center'});el.click();return true}"""
RT_RE = r"Runtime\s+([0-9a-z ]+?)\s+lasts until\s+(\d{1,2} \w{3,9}, \d{2}:\d{2})"


def body(p):
    try:
        return " ".join(p.evaluate("document.body.innerText").split())
    except Exception:
        return ""


def read_state(p):
    text = body(p)
    m = re.search(r"(\d+) cloud tokens", text)
    rt = re.search(RT_RE, text)
    return (int(m.group(1)) if m else None,
            f"Runtime {rt.group(1)} lasts until {rt.group(2)}" if rt else None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tokens", type=int, default=0, help="花几个；0 = 全部")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--proxy", default=proxy_from_env())
    ap.add_argument("--headless", action="store_true")
    args = ap.parse_args()

    cookies = load_cookies()
    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=args.headless, args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = br.new_context(viewport={"width": 1400, "height": 950}, locale="en-US",
                             proxy={"server": args.proxy} if args.proxy else None)
        ctx.add_cookies(cookies)
        p = ctx.new_page()
        p.goto(PANEL, wait_until="domcontentloaded", timeout=60000)
        time.sleep(5)
        bal, rt = read_state(p)
        print(f"balance={bal} runtime={rt}", flush=True)
        if args.dry_run or not bal:
            br.close()
            return 0

        opened = False
        for c in p.evaluate(CAND_JS):
            if c["w"] < 2 or c["h"] < 2:
                continue
            p.evaluate(CLICK_I_JS, c["i"])
            for _ in range(10):
                time.sleep(1)
                if p.evaluate("document.querySelectorAll('input[type=number]').length"):
                    opened = True
                    break
            print(f"  click[{c['i']}] -> modal={opened}", flush=True)
            if opened:
                break
        if not opened:
            print("没等到 Add runtime 弹窗，放弃（余额未动）")
            br.close()
            return 1

        n = bal if not args.tokens else min(args.tokens, bal)
        inp = p.locator("input[type='number']").last
        inp.fill(str(n))
        time.sleep(1)
        print(f"filled={inp.input_value()}", flush=True)
        p.locator("button:has-text('Add runtime')").last.click()
        time.sleep(8)
        p.goto(PANEL, wait_until="domcontentloaded", timeout=60000)
        time.sleep(5)
        bal2, rt2 = read_state(p)
        print(f"after: balance={bal2} runtime={rt2}", flush=True)
        save_cookies(ctx.cookies())
        br.close()
        print(f"SUMMARY: spent {n} token(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
