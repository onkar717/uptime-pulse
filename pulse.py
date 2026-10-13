#!/usr/bin/env python3
"""
uptime-pulse: tiny scheduled endpoint watcher with push alerts (ntfy).

Watches a version index page and the next expected release path. When a new
version appears it sends a push alert, repeating every interval until the alert
is acknowledged from the phone (or a max repeat count is reached).

All targets come from the WATCH_CONFIG secret (JSON), never from this repo:
  {
    "name":     "<who to greet>",
    "index":    "<url of the page that lists versions>",
    "pattern":  "<regex with one group capturing the version number>",
    "next":     "<url template for the next version, e.g. https://host/{n:03d}/>",
    "label":    "<format for the version in alerts, e.g. {n:03d}>"
  }
Push channel comes from the NTFY_TOPIC secret. Logs never print targets.
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
LAST = ROOT / "state" / "last.txt"
ALERT = ROOT / "state" / "alert.json"

CFG = json.loads(os.environ.get("WATCH_CONFIG") or "{}")
TOPIC = os.environ.get("NTFY_TOPIC", "").strip()
ACK_TOPIC = f"{TOPIC}-ack"
RUN_SECONDS = int(os.environ.get("PULSE_RUN_SECONDS", "285"))
EVERY = int(os.environ.get("PULSE_EVERY", "60"))
MAX_RINGS = int(os.environ.get("PULSE_MAX_RINGS", "180"))
UA = "uptime-pulse/1.0"


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:
        return 0, ""


def label(n):
    return CFG.get("label", "{n}").format(n=n)


def push(title, msg, url, priority="urgent", ack=True):
    headers = {"Title": title, "Priority": priority, "Tags": "rotating_light",
               "Click": url, "User-Agent": UA}
    if ack:
        headers["Actions"] = (f"http, Got it, https://ntfy.sh/{ACK_TOPIC}, "
                              f"method=POST, body=ack, clear=true; view, Open, {url}")
    req = urllib.request.Request(f"https://ntfy.sh/{TOPIC}", data=msg.encode(),
                                 method="POST", headers=headers)
    try:
        urllib.request.urlopen(req, timeout=20).read()
        log("alert sent")
    except Exception as e:
        log("alert failed:", type(e).__name__)


def acked_since(ts):
    status, body = get(f"https://ntfy.sh/{ACK_TOPIC}/json?poll=1&since={int(ts)}")
    return status == 200 and any('"event":"message"' in line for line in body.splitlines())


def detect(last):
    nxt = last + 1
    status, index = get(CFG["index"])
    found = {int(x) for x in re.findall(CFG["pattern"], index)}
    nstatus, _ = get(CFG["next"].format(n=nxt))
    log(f"check: index={status} next={nstatus} state={last}")
    newest = max([x for x in found if x > last] or [0])
    if newest > last:
        return newest, True
    if nstatus and nstatus != 404 and nstatus < 500:
        return nxt, False
    return None, False


def ring(alert):
    alert["rings"] = alert.get("rings", 0) + 1
    url = CFG["index"] if alert.get("listed") else CFG["next"].format(n=alert["n"])
    push(f"Hey {CFG.get('name', 'there')}, {label(alert['n'])} is live now!",
         f"{label(alert['n'])} just went live. Ring #{alert['rings']}. "
         f"Tap 'Got it' to stop.", url)


def step():
    last = int(LAST.read_text().strip()) if LAST.exists() else 0
    try:
        alert = json.loads(ALERT.read_text())
    except Exception:
        alert = None

    if alert:
        if acked_since(alert["since"]) or alert.get("rings", 0) >= MAX_RINGS:
            log("alert closed")
            LAST.write_text(f"{alert['n']}\n")
            ALERT.unlink()
            return
        ring(alert)
        ALERT.write_text(json.dumps(alert))
        return

    n, listed = detect(last)
    if n:
        alert = {"n": n, "since": time.time() - 5, "rings": 0, "listed": listed}
        ring(alert)
        ALERT.write_text(json.dumps(alert))


def main():
    if not TOPIC or not CFG:
        sys.exit("missing NTFY_TOPIC or WATCH_CONFIG secret")
    if "--test" in sys.argv:
        push(f"Hey {CFG.get('name', 'there')}, monitor is armed",
             "Test alert. Checking every minute. Tap 'Got it' to test the button.",
             CFG["index"], priority="high")
        return
    if "--once" in sys.argv:
        step()
        return
    end = time.time() + RUN_SECONDS
    while True:
        started = time.time()
        step()
        if time.time() + EVERY > end:
            break
        time.sleep(max(1, EVERY - (time.time() - started)))


if __name__ == "__main__":
    main()
