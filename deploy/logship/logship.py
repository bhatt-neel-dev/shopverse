"""Forward ShopVerse container logs to Motadata as syslog.

Reads container stdout through the Docker API and re-emits each line as RFC3164 syslog to the
appliance. Using the Docker API rather than the `syslog` log driver keeps `docker logs` working
for every service, which matters because the chaos scenarios are debugged through it.

Each service's log line is already a JSON object (docs/CONTRACTS.md), and it is forwarded
verbatim as the syslog MSG so the "ShopVerse JSON" parser on the appliance can read it.
"""

import json
import os
import socket
import threading
import time

import docker

APPLIANCE = os.environ.get("APPLIANCE_IP", "172.16.14.71")
PORT = int(os.environ.get("SYSLOG_PORT", "514"))
PROTO = os.environ.get("SYSLOG_PROTO", "udp").lower()
PREFIX = os.environ.get("CONTAINER_PREFIX", "shopverse-")
# Containers whose output is noise rather than application telemetry.
SKIP = {"shopverse-logship", "shopverse-local-registry", "shopverse-seed",
        "shopverse-mysql", "shopverse-postgres", "shopverse-mongo",
        "shopverse-redis", "shopverse-rabbitmq"}

FACILITY = 16  # local0
SEVERITY = {"ERROR": 3, "WARN": 4, "INFO": 6, "DEBUG": 7}

HOSTNAME = os.environ.get("SOURCE_HOST") or socket.gethostname()


def _sender():
    if PROTO == "tcp":
        s = socket.create_connection((APPLIANCE, PORT), timeout=10)
        return s, lambda payload: s.sendall(payload + b"\n")
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    return s, lambda payload: s.sendto(payload, (APPLIANCE, PORT))


def _frame(tag: str, line: str) -> bytes:
    level = "INFO"
    try:
        parsed = json.loads(line)
        level = str(parsed.get("level", "INFO")).upper()
    except Exception:  # noqa: BLE001 — non-JSON lines still ship, just at INFO
        pass
    pri = FACILITY * 8 + SEVERITY.get(level, 6)
    stamp = time.strftime("%b %d %H:%M:%S", time.localtime())
    return f"<{pri}>{stamp} {HOSTNAME} {tag}: {line}".encode("utf-8", "replace")


def follow(container, send) -> None:
    tag = container.name.replace(PREFIX, "")
    for raw in container.logs(stream=True, follow=True, tail=0):
        line = raw.decode("utf-8", "replace").strip()
        if not line:
            continue
        try:
            send(_frame(tag, line))
        except Exception as e:  # noqa: BLE001 — a dropped packet must not kill the follower
            print(json.dumps({"svc": "logship", "level": "WARN",
                              "msg": f"send failed for {tag}", "err": str(e)[:120]}), flush=True)
            time.sleep(1)


def main() -> None:
    client = docker.from_env()
    sock, send = _sender()
    print(json.dumps({"svc": "logship", "level": "INFO",
                      "msg": f"forwarding to {APPLIANCE}:{PORT}/{PROTO} as {HOSTNAME}"}),
          flush=True)

    watched: dict[str, threading.Thread] = {}
    while True:
        try:
            for c in client.containers.list():
                if not c.name.startswith(PREFIX) or c.name in SKIP:
                    continue
                thread = watched.get(c.name)
                if thread and thread.is_alive():
                    continue
                t = threading.Thread(target=follow, args=(c, send), daemon=True)
                watched[c.name] = t
                t.start()
                print(json.dumps({"svc": "logship", "level": "INFO",
                                  "msg": f"following {c.name}"}), flush=True)
        except Exception as e:  # noqa: BLE001 — docker restarts, keep trying
            print(json.dumps({"svc": "logship", "level": "ERROR",
                              "msg": "container scan failed", "err": str(e)[:160]}), flush=True)
        time.sleep(15)


if __name__ == "__main__":
    main()
