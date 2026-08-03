"""Trap generator — replays realistic vendor traps on demand.

Listens on :7070 so Scenario Studio can fire a burst that correlates with a chaos event
(e.g. link-flap sends linkDown then linkUp two minutes later, matching the flow drop).
"""
import os
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
import json

APPLIANCE = os.environ.get("APPLIANCE_IP", "172.16.14.71")
PORT = os.environ.get("TRAP_PORT", "1620")
COMMUNITY = os.environ.get("TRAP_COMMUNITY", "shopverse")

# name -> (trap OID, varbinds)
TRAPS = {
    "linkDown": ("1.3.6.1.6.3.1.1.5.3",
                 ["1.3.6.1.2.1.2.2.1.1.2", "i", "2",
                  "1.3.6.1.2.1.2.2.1.7.2", "i", "2",
                  "1.3.6.1.2.1.2.2.1.8.2", "i", "2"]),
    "linkUp": ("1.3.6.1.6.3.1.1.5.4",
               ["1.3.6.1.2.1.2.2.1.1.2", "i", "2",
                "1.3.6.1.2.1.2.2.1.7.2", "i", "1",
                "1.3.6.1.2.1.2.2.1.8.2", "i", "1"]),
    "coldStart": ("1.3.6.1.6.3.1.1.5.1", []),
    "authFailure": ("1.3.6.1.6.3.1.1.5.5", []),
    "upsOnBattery": ("1.3.6.1.4.1.318.0.5",
                     ["1.3.6.1.4.1.318.1.1.1.2.2.1.0", "i", "45"]),
    "upsLowBattery": ("1.3.6.1.4.1.318.0.7",
                      ["1.3.6.1.4.1.318.1.1.1.2.2.1.0", "i", "12"]),
    "fanFailure": ("1.3.6.1.4.1.9.9.13.3.0.4",
                   ["1.3.6.1.4.1.9.9.13.1.4.1.3.1", "i", "2"]),
    "tempHigh": ("1.3.6.1.4.1.9.9.13.3.0.1",
                 ["1.3.6.1.4.1.9.9.13.1.3.1.6.1", "i", "3"]),
}


def send(name: str, source: str = "127.0.0.1") -> bool:
    if name not in TRAPS:
        return False
    oid, varbinds = TRAPS[name]
    cmd = ["snmptrap", "-v", "2c", "-c", COMMUNITY,
           f"{APPLIANCE}:{PORT}", "", oid] + varbinds
    try:
        subprocess.run(cmd, check=True, timeout=10, capture_output=True)
        print(json.dumps({"svc": "trapgen", "level": "INFO",
                          "msg": f"trap {name} sent to {APPLIANCE}:{PORT}"}), flush=True)
        return True
    except Exception as e:
        print(json.dumps({"svc": "trapgen", "level": "ERROR",
                          "msg": f"trap {name} failed", "err": str(e)}), flush=True)
        return False


def burst(name: str, count: int, interval: float):
    for _ in range(count):
        send(name)
        time.sleep(interval)


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        name = body.get("trap", "linkDown")
        count = min(int(body.get("count", 1)), 500)
        interval = float(body.get("interval", 0.2))
        threading.Thread(target=burst, args=(name, count, interval), daemon=True).start()
        self._reply(202, {"status": "sending", "trap": name, "count": count})

    def do_GET(self):
        self._reply(200, {"status": "ok", "traps": sorted(TRAPS), "target": f"{APPLIANCE}:{PORT}"})

    def _reply(self, code, payload):
        data = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_):
        pass


if __name__ == "__main__":
    print(json.dumps({"svc": "trapgen", "level": "INFO",
                      "msg": f"trapgen ready, target {APPLIANCE}:{PORT}"}), flush=True)
    HTTPServer(("0.0.0.0", 7070), Handler).serve_forever()
