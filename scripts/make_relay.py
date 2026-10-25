#!/usr/bin/env python3
"""Build a sing-box relay config: local socks 127.0.0.1:10900 -> authenticated upstream socks.

Usage: python scripts/make_relay.py 'socks5://user:pass@host:port' relay.json
Needed because Playwright's Chromium cannot send SOCKS5 proxy credentials.
"""
import json
import sys
from urllib.parse import unquote, urlparse


def main():
    url, out = sys.argv[1], sys.argv[2]
    u = urlparse(url)
    if u.scheme not in ("socks5", "socks5h", "socks"):
        sys.exit(f"unsupported scheme: {u.scheme}")
    cfg = {
        "log": {"level": "warn"},
        "inbounds": [{"type": "socks", "tag": "in", "listen": "127.0.0.1", "listen_port": 10900}],
        "outbounds": [{
            "type": "socks", "tag": "up",
            "server": u.hostname, "server_port": u.port, "version": "5",
            "username": unquote(u.username or ""), "password": unquote(u.password or ""),
        }],
    }
    json.dump(cfg, open(out, "w"), indent=2)
    print(f"relay -> {u.hostname}:{u.port}")


if __name__ == "__main__":
    main()
