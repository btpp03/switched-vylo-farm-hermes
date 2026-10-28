#!/usr/bin/env python3
"""Build a sing-box relay config: local socks 127.0.0.1:10900 -> one upstream proxy.

Usage:
  python scripts/make_relay.py 'socks5://user:pass@host:port' relay.json
  python scripts/make_relay.py 'vless://uuid@host:port?type=tcp' relay.json

Needed because Playwright's Chromium cannot send SOCKS5 proxy credentials, and because
GitHub runners have no direct route to the residential exits we want to look like.
"""
import json
import sys
from urllib.parse import parse_qsl, unquote, urlparse


def build(url: str) -> dict:
    u = urlparse(url)
    if u.scheme in ("socks5", "socks5h", "socks"):
        up = {
            "type": "socks",
            "tag": "up",
            "server": u.hostname,
            "server_port": u.port,
            "version": "5",
            "username": unquote(u.username or ""),
            "password": unquote(u.password or ""),
        }
    elif u.scheme == "vless":
        q = dict(parse_qsl(u.query))
        up = {
            "type": "vless",
            "tag": "up",
            "server": u.hostname,
            "server_port": u.port,
            "uuid": unquote(u.username or ""),
            "packet_encoding": "xudp",
        }
        if q.get("flow"):
            up["flow"] = q["flow"]
        if q.get("type") and q["type"] != "tcp":
            tr = {"type": q["type"]}
            if q.get("path"):
                tr["path"] = q["path"]
            if q.get("host"):
                tr["host"] = q["host"]
            if q.get("serviceName"):
                tr["service_name"] = q["serviceName"]
            up["transport"] = tr
        if q.get("security") in ("tls", "reality"):
            up["tls"] = {"enabled": True, "server_name": q.get("sni") or q.get("host") or u.hostname}
            if q.get("security") == "reality":
                up["tls"]["reality"] = {"enabled": True, "public_key": q.get("pbk", ""),
                                        "short_id": q.get("sid", "")}
    else:
        sys.exit(f"unsupported scheme: {u.scheme}")

    return {
        "log": {"level": "warn"},
        "inbounds": [{"type": "socks", "tag": "in", "listen": "127.0.0.1", "listen_port": 10900}],
        "outbounds": [up],
    }


def main():
    url, out = sys.argv[1], sys.argv[2]
    cfg = build(url)
    up = cfg["outbounds"][0]
    json.dump(cfg, open(out, "w"), indent=2)
    print(f"relay -> {up['type']} {up['server']}:{up['server_port']}")


if __name__ == "__main__":
    main()
