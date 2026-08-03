# ShopVerse — Build Plan (single-VM edition)

Prereqs: one Ubuntu 24.04 VM (8 vCPU / 16 GB / 150 GB), SSH sudo access, ~20 free IPs on the
appliance-reachable subnet, license headroom on 172.16.14.71 for ~20 monitors.

## Current status (2026-07-31)

The app-level core is **complete and runnable**: `cd deploy && docker compose up -d --build`
brings up the full stack on any Docker host.

- [x] Data tier (MySQL, PostgreSQL, MongoDB, Redis, RabbitMQ) + idempotent seeder (5k products)
- [x] All seven services per docs/CONTRACTS.md — catalog (Java), order (Java), cart (Node),
      search (Python), payment (Go), notify (Python worker), storefront (Next.js UI with
      browse/search/product/cart/checkout pages)
- [x] nginx gateway (`deploy/gateway`) with JSON access logs
- [x] Trace propagation (`X-Trace-Id`), shared JSON log schema, and Redis-flag fault
      injection in every HTTP service
- [x] Scenario Studio API (`admin/api`): /inject, /traces/bulk, /load/spike, /logs/storm,
      /chaos/{scenario} (docker-socket stop/start with auto-recover), /coverage, /history
- [x] Scenario Studio UI (`admin/ui`): live scorecard + injection/traces/spike/storm/chaos
      panels + scenario history table
- [x] Locust baseline load (constant + diurnal profile)
- [x] `forge/register.py` — idempotent Motadata registration (credential profiles, discovery
      profiles with auto-provision, ShopVerse JSON log parser, RUM apps, trap listeners);
      `--dry-run` supported. **Untested against the appliance — needs the VM + a PAT.**
- [x] Phase C device layer scaffolded: `deploy/docker-compose.devices.yml` (snmpsim fleet,
      softflowd NetFlow export, trapgen), `deploy/devices/trapgen` (HTTP-triggered vendor
      trap replays), `deploy/macvlan.md` (per-component LAN IPs)
- [x] Studio trap bursts: `GET /traps`, `POST /traps/burst` → trapgen
- [ ] snmpsim `.snmprec` recordings — `deploy/devices/snmpsim-data/` is empty; needs public
      snapshots or recordings from real devices before the fleet answers
- [ ] VyOS container (NCCM backup target, NetRoute hops, real router syslog)
- [ ] RUM SDK snippets — placeholders sit in both UIs; needs the real SDK from the appliance
- [ ] Motadata policies/dashboards/SLOs (register.py covers onboarding only)
- [ ] Forge one-YAML lifecycle (`render/deploy/register/verify/destroy`) (Phase D)

**Verified locally (2026-08-03):** `docker compose up -d --build` builds and starts on a Docker
host. One real bug found and fixed during verification — `services/cart` had no
`package-lock.json`, so its `npm ci` build step failed.

## Phase A — Core loop (first correlated data end-to-end)

**Goal:** browser click → RUM → trace → logs → DB → metrics visible in Motadata, all correlated.

1. `deploy/bootstrap.sh` — Docker + compose, snmpd, rsyslog forward, macvlan network.
2. Data tier up: PostgreSQL, MySQL, MongoDB, Redis, RabbitMQ (each with macvlan IP), seeded
   (~5k products, 500 users).
3. Minimum app path: storefront → nginx → catalog (Java/Tomcat) + order (Spring) + cart (Node).
4. Structured JSON logging in every service (one shared log schema: ts, svc, level, trace_id,
   order_id…) — this is what makes log↔trace↔alert correlation real.
5. Motadata wiring (scripted in `forge/register.py`): SSH + JDBC + SNMP credential profiles,
   discovery profiles with auto-provision, JSON log parser, first dashboard.
6. Locust baseline traffic (constant low RPS).

**Exit test:** stop MySQL for 5 min → verify availability alert + catalog error logs + APM error
spike + storefront RUM errors all land in Motadata within the same window.

## Phase B — Scenario Studio (the admin panel) + full app

**Goal:** every "generate X" knob works from the browser.

1. Remaining services: search (Python/FastAPI + MongoDB), payment (Go), notify (Python + RabbitMQ
   + SMTP). APM agents on all; eBPF OBI on payment.
2. **Injection middleware in every service** (reads flags from Redis, no redeploys):
   `error_rate`, `latency_ms`, `exception_type`, `slow_query` — per service, per endpoint.
3. **Scenario Studio backend** (FastAPI, `admin/api/`):
   - `POST /traces/bulk` — fire N real journeys (journey type, count, concurrency, custom tags,
     error %) through the actual stack → bulk *genuine* traces.
   - `POST /inject` — set/clear per-service error/latency flags.
   - `POST /load/spike` — magnitude × duration ramp via Locust REST; diurnal profile toggle.
   - `POST /logs/storm` — severity/pattern/count log bursts through real service loggers.
   - `POST /chaos/{scenario}` — payment-outage, db-pressure, disk-fill, memory-leak, link-flap,
     trap-burst, dr-drill (docker API + stress-ng + VyOS ssh + trap replays).
   - `GET /coverage` — pipeline scorecard (queries Motadata REST: is metric/log/flow/trap/APM/RUM
     data arriving?).
   - Scheduler: cron-style recurring scenarios (nightly spike, weekly DR drill).
4. **Scenario Studio UI** (React, RUM app #2): dashboard of toggles/sliders/buttons + live
   scorecard + scenario history ("what did I break and when") — the history doubles as the
   ground-truth timeline to validate Motadata alerts against.
5. Register both RUM apps; policies: availability, CPU/mem/disk, APM latency, RUM Apdex,
   anomaly (orders/min), forecast (disk).

**Exit test:** from Studio, run "500 checkout traces with 10% payment errors + 2× load spike" →
see the burst in APM Explorer, error logs, RUM sessions, and an anomaly alert.

## Phase C — Network & device breadth

1. VyOS container (macvlan, two subnets) → NCCM onboarding (backup, scheduled config change →
   change-detection alert), syslog source, NetRoute path target.
2. softflowd on the gateway bridge → NetFlow to :2055; verify Flow Explorer conversations match
   real service traffic.
3. snmpsim fleet: router, switch, firewall, UPS, printer, storage snapshots — each on its own
   macvlan IP; SNMP discovery range picks them all up.
4. Trap replays tied to chaos events (link-flap fires the matching linkDown trap).
5. Service checks: Ping/Port/URL/REST/SSL/Email/NTP batch; SLO profiles (APM checkout, RUM
   storefront, NetRoute).

## Phase D — Forge (one-YAML lifecycle) + polish

1. `forge/shopverse.yaml` drives everything: which services, which DBs (2–4), device-fleet
   counts, load profile, chaos schedule, pipelines on/off.
2. `forge render` → compose files; `forge deploy` → SSH push + up; `forge register` → Motadata
   REST (idempotent); `forge verify` → coverage scorecard; `forge destroy`.
3. README quickstart, demo script (guided 15-min tour: normal ops → chaos → correlate in
   Motadata), optional second-VM split instructions (HA/DR tier).

## Definition of "everything connected"

One `trace_id`/`order_id` traceable across: RUM session → APM trace → service logs → DB row →
queue message → flow conversation → (on failure) alert + trap + syslog, with Scenario Studio's
history as the ground truth for when each condition was injected.
