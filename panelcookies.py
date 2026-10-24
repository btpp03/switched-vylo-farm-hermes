"""Shared helpers: load panel cookies from a file or env, build sane cookie dicts."""
import base64
import json
import os

DEFAULT_FILE = os.path.expanduser("~/noprofit_cookies.json")


def load_cookies(path: str | None = None):
    """Cookies from (in order): NOPROFIT_COOKIES env (raw JSON or base64), or a file."""
    raw = os.environ.get("NOPROFIT_COOKIES", "").strip()
    if raw:
        if not raw.startswith("["):
            raw = base64.b64decode(raw).decode()
        data = json.loads(raw)
    else:
        p = path or os.environ.get("NOPROFIT_COOKIE_FILE", DEFAULT_FILE)
        data = json.load(open(p))
    out = []
    for c in data:
        d = dict(name=c["name"], value=c["value"], domain=c["domain"],
                 path=c.get("path", "/"), secure=c.get("secure", True),
                 httpOnly=c.get("httpOnly", False), sameSite="Lax")
        if c.get("expires"):
            d["expires"] = c["expires"]
        out.append(d)
    return out


def save_cookies(cookies, path: str | None = None):
    """Only persist locally; in CI there is nothing to persist to."""
    if os.environ.get("NOPROFIT_COOKIES"):
        return
    p = path or os.environ.get("NOPROFIT_COOKIE_FILE", DEFAULT_FILE)
    try:
        json.dump(cookies, open(p, "w"))
    except OSError:
        pass


def proxy_from_env(default: str | None = None):
    return os.environ.get("SW_PROXY", default or "")
