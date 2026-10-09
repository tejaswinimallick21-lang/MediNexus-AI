"""
Capture full-resolution screenshots of the React app with headless Chrome (DevTools protocol).

    python scripts/capture_screenshots.py /login /reception --email receptionist@medinexus.org
    python scripts/capture_screenshots.py / --out docs/screenshots

Needs the backend (npm run backend) and frontend (npm run frontend) running, Chrome installed,
and the websocket-client package. Signs in through the API so protected routes render.
"""

import argparse
import base64
import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

import websocket

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "google-chrome",
    "chromium",
]


def find_chrome() -> str:
    for c in CHROME_CANDIDATES:
        if os.path.exists(c) or shutil.which(c):
            return c
    raise SystemExit("Chrome/Edge not found")


class CDP:
    def __init__(self, ws_url: str):
        self.ws = websocket.create_connection(ws_url, timeout=60)
        self.msg_id = 0

    def call(self, method: str, **params):
        self.msg_id += 1
        self.ws.send(json.dumps({"id": self.msg_id, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.msg_id:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})


def login_cookie(base: str, email: str, password: str) -> str:
    req = urllib.request.Request(
        f"{base}/api/auth/login",
        data=json.dumps({"email": email, "password": password}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        for header in resp.headers.get_all("set-cookie") or []:
            name, _, rest = header.partition("=")
            if name == "medinexus_session":
                return rest.split(";", 1)[0]
    raise SystemExit("Login did not return a session cookie")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--base", default="http://localhost:5173")
    parser.add_argument("--email")
    parser.add_argument("--password", default=os.getenv("MEDINEXUS_SEED_PASSWORD", "MediNexus@2026"))
    parser.add_argument("--out", default="docs/screenshots")
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=900)
    parser.add_argument("--full", action="store_true", help="Capture the full scroll height")
    parser.add_argument("--wait", type=float, default=3.5)
    parser.add_argument("--prefix", default="")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    profile = tempfile.mkdtemp(prefix="medinexus_chrome_")
    port = 9333
    proc = subprocess.Popen(
        [find_chrome(), "--headless=new", f"--remote-debugging-port={port}", f"--remote-allow-origins=http://127.0.0.1:{port}", f"--user-data-dir={profile}",
         "--hide-scrollbars", "--force-device-scale-factor=1", f"--window-size={args.width},{args.height}", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(50):
            try:
                targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json"))
                page = next(t for t in targets if t["type"] == "page")
                break
            except Exception:
                time.sleep(0.2)
        cdp = CDP(page["webSocketDebuggerUrl"])
        cdp.call("Page.enable")
        cdp.call("Network.enable")
        cdp.call("Emulation.setDeviceMetricsOverride", width=args.width, height=args.height, deviceScaleFactor=1, mobile=False)
        if args.email:
            token = login_cookie(args.base, args.email, args.password)
            cdp.call("Network.setCookie", name="medinexus_session", value=token, url=args.base, httpOnly=True, sameSite="Lax")

        for path in args.paths:
            cdp.call("Page.navigate", url=f"{args.base}{path}")
            time.sleep(args.wait)
            params = {"format": "png"}
            if args.full:
                metrics = cdp.call("Page.getLayoutMetrics")
                h = int(metrics["cssContentSize"]["height"])
                cdp.call("Emulation.setDeviceMetricsOverride", width=args.width, height=h, deviceScaleFactor=1, mobile=False)
                time.sleep(1.0)
            data = cdp.call("Page.captureScreenshot", **params)["data"]
            name = args.prefix + ("home" if path == "/" else path.strip("/").replace("/", "_")) + ".png"
            (out / name).write_bytes(base64.b64decode(data))
            print(f"saved {out / name}")
            if args.full:
                cdp.call("Emulation.setDeviceMetricsOverride", width=args.width, height=args.height, deviceScaleFactor=1, mobile=False)
    finally:
        proc.terminate()
        shutil.rmtree(profile, ignore_errors=True)


if __name__ == "__main__":
    main()
