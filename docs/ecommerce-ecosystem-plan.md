# Phase 2 Plan — "ShopVerse": One Connected E-Commerce Ecosystem for Motadata AIOps

**Goal:** a single, self-consistent multi-service e-commerce system whose *real* operation feeds
**all 13 Motadata ingestion pipelines** (see `motadata-aiops-product-overview.md` §2) with
correlated, meaningful data — orders that flow through services, databases, queues, load
balancers, and networks — so every alert, trace, log line, and flow record traces back to actual
business activity. Deployed with **minimum configuration**, and every component **selectable /
customizable** through a config-driven generator application.

**Design principles**
1. **One story, many signals.** A single user checkout must produce: a RUM session → an APM trace
   across ≥3 services → app logs → DB queries → queue messages → LB/flow traffic → host metrics.
   Kill one service and the metric alert, log burst, APM errors, and RUM failures all correlate.
2. **Minimum real, maximum simulated breadth.** Real components where data quality matters
   (services, DBs, LB, hosts). Simulators where hardware would be needed (SNMP device fleet,
   traps) — simulated *devices*, not simulated *data*: Motadata discovers and polls them like
   real hardware.
3. **3–4 databases, not 100.** Each DB earns its place in the business story AND covers a JDBC
   monitor type.
4. **Everything scriptable.** All Motadata onboarding via its REST API (`/api/v1/settings/*`) so
   the generator app can wire monitoring automatically.

---

## 1. Business scenario (why the data makes sense)

ShopVerse is an online store. Continuous synthetic shoppers browse the catalog, search, add to
cart, check out, pay, and get shipping notifications. Back-office jobs restock inventory and
generate reports. This yields a natural transaction chain:

```
Browser (RUM)
  └─ storefront (Next.js)  ──►  api-gateway (Nginx)
        └─ HAProxy VIP (HA pair)
              ├─ catalog-svc   (Java/Tomcat)   ─► MySQL      (products, stock)
              ├─ search-svc    (Python)        ─► MongoDB    (product docs, reviews)
              ├─ cart-svc      (Node.js)       ─► Redis      (carts, sessions)
              ├─ order-svc     (Java Spring)   ─► PostgreSQL (orders, payments ledger)
              ├─ payment-svc   (Go)            ─► PostgreSQL + external mock PSP (HTTP)
              └─ notify-worker (Python)        ◄─ RabbitMQ   (order.events queue)
                     └─ sends mail via local SMTP (Email service check target)
```

Every arrow is a real network call → APM spans, flow records, LB stats, DB sessions, logs.

---

## 2. Service matrix (APM language coverage with fewest services)

| Service | Runtime | Why this runtime | Data store | APM coverage |
|---|---|---|---|---|
| storefront | **Next.js (Node)** | RUM SDK target (Next.js guide exists) | — | Node.js agent |
| catalog-svc | **Java on Tomcat** | Covers Java agent + Apache Tomcat monitor type | MySQL | Java agent |
| order-svc | **Java Spring Boot** | Core transactional service (shares Java agent, no extra effort) | PostgreSQL | Java agent |
| cart-svc | **Node.js (Express)** | Covers Redis usage | Redis | Node.js agent |
| search-svc | **Python (FastAPI)** | Covers Python agent | MongoDB | Python agent |
| payment-svc | **Go** | Covers Go agent + demonstrates eBPF zero-code option | PostgreSQL | Go agent or eBPF OBI |
| notify-worker | **Python** | Background/queue consumer spans | RabbitMQ | Python agent |
| admin-panel *(optional)* | **PHP-FPM behind Apache** | Covers PHP agent + Apache HTTP monitor | MySQL | PHP agent |

7 services core + 1 optional = **Java, Node, Python, Go (+PHP) covered**; .NET is covered by the
Windows host (below) if desired later. All containerized (Docker), one compose project per host.

**Web/entry tier (monitor types for free):** Nginx (api-gateway), HAProxy ×2 (HA), Apache
(admin, optional) — all three are native Motadata monitor types.

## 3. Data stores — 4 DBs + 1 queue (each with a business role)

| Store | Role in ShopVerse | Motadata monitor type | HA/DR role |
|---|---|---|---|
| **PostgreSQL** | Orders + payment ledger (system of record) | PostgreSQL (JDBC) | **Primary + streaming replica on DR host** — the HA/DR showcase |
| **MySQL** | Product catalog + inventory | MySQL (JDBC) | Single + nightly dump to DR |
| **MongoDB** | Product documents, reviews, search index source | MongoDB | Single |
| **Redis** | Carts, sessions, hot cache | Redis DB | Single |
| **RabbitMQ** | order.events queue (order → notify/shipping) | RabbitMQ | Single |

*(Elasticsearch optional later — it's another monitor type but adds RAM cost; MongoDB text search
is enough for the story.)*

---

## 4. Infrastructure & HA/DR topology

**Target: 5 Linux VMs + 1 Windows VM + 1 virtual router.** (4 GB/2 vCPU each except node1/node2
at 8 GB; ~36 GB RAM total. Can shrink to 4 VMs by merging site-b + sim host.)

| Host | Role | What runs there | Monitored via |
|---|---|---|---|
| `sv-lb` | Entry + HA | HAProxy + keepalived VIP, Nginx gateway, **softflowd** (NetFlow export :2055), rsyslog relay | SSH + SNMP (Linux SNMP), HAProxy & Nginx monitors |
| `sv-app1` | App node A | storefront, catalog, cart, search + MotaAgent (metrics+logs+APM) | MotaAgent + SSH |
| `sv-app2` | App node B (HA) | order, payment, notify + second replica of storefront/catalog (LB round-robin proves HA) | MotaAgent + SSH |
| `sv-data` | Data tier | PostgreSQL primary, MySQL, MongoDB, Redis, RabbitMQ | SSH + JDBC ×3 + Redis/Mongo/RabbitMQ monitors |
| `sv-dr` | **DR site** | PostgreSQL streaming replica, backup target (nightly dumps), standby compose of core services (stopped; started during DR drill) | SSH + JDBC (replica) |
| `sv-win` | Windows tier | Windows Server: IIS (static assets/"legacy" endpoint), optional AD DS + DNS; Windows Event log source; .NET mini-service later | PowerShell/WinRM + MotaAgent |
| `sv-router` | Network device | **VyOS** (free virtual router) routing the "site A ⇄ site B" subnets | SNMP, SSH → **NCCM config backup target**, syslog source, NetRoute hops |

**HA story:** keepalived VIP over HAProxy pair (sv-lb + backup instance on sv-app1); app services
duplicated across app1/app2; Postgres streaming replication → sv-dr.
**DR story:** scheduled failover drill (stop primary Postgres → promote replica) — generates a
realistic alert + correlation storm on schedule; Motadata Backup Profile pointed at sv-dr storage.

### Device breadth without hardware — the simulator fleet (runs on `sv-dr` or `sv-data`)

| Simulator | Covers Motadata types | Effort |
|---|---|---|
| **snmpsim** with real device snapshots (`snmpsim-data` community snapshots) | Router, Switch, Firewall, UPS (APC), Printer, Wireless Controller, Storage — each snapshot = one discoverable "device" with its own IP alias | Low — one container, N IP aliases |
| **snmptrap cron** (net-snmp) replaying vendor trap sequences (link down/up, UPS on battery, fan fail) tied to chaos events | Trap pipeline with *correlated* traps (fires when chaos script drops a link) | Low |
| **VyOS** (real router, not simulated) | NCCM backup/restore/compliance, syslog, SNMP, NetRoute hops, real flows | Medium (one VM) |
| **hsflowd** on app hosts *(optional)* | sFlow :6343 alongside NetFlow | Low |

This is how "every possible device type" is satisfied honestly: Motadata *actually discovers and
polls* these endpoints; only the device hardware is virtual.

---

## 5. Coverage map — every pipeline fed by the ecosystem

| # | Motadata pipeline | Fed by |
|---|---|---|
| 1 | Metrics agentless | SSH (5 Linux), PowerShell (Windows), SNMP (router+sim fleet+hosts), JDBC (PG/MySQL/…), HTTP (Nginx/HAProxy/RabbitMQ mgmt) |
| 2 | Metrics agent | MotaAgent on app1/app2/win (1s polling on checkout path) |
| 3 | Syslog | All Linux hosts + VyOS + HAProxy → collector |
| 4 | Agent logs / Windows events | App JSON logs tailed by MotaAgent; Windows Security/System/IIS events |
| 5 | Agentless log pull | One HTTP Log Collection Profile against RabbitMQ API or mock-PSP; DB collection type against Postgres (slow-query log table) |
| 6 | Flows | softflowd on sv-lb (NetFlow) + VyOS real flows (+ optional sFlow) |
| 7 | Traps | Correlated trap replays + VyOS genuine traps |
| 8 | APM | 4–5 language agents + eBPF on payment-svc host |
| 9 | RUM | storefront (Next.js SDK) + admin (React SDK) — 2 registered apps, sampled sessions from load generator's real browsers |
| 10 | NCCM | VyOS config backup, scheduled change ("add a firewall rule") → change-detection alert |
| 11 | NetRoute | Path: collector → VIP → app subnet (crosses VyOS hops) |
| 12 | IP SLA | Skip (needs Cisco) — document as gap, or VyOS + future Cisco lab device |
| 13 | Audit | Free (product usage) |
| — | Service Checks | Ping (all), Port (5432/3306/6379/5672), URL+REST (checkout API), SSL cert (storefront), DNS (sv-win AD DNS), Email (notify SMTP), NTP, Domain |
| — | SLO | Checkout-latency APM SLO, storefront RUM SLO, NetRoute SLO across VyOS |
| — | Dashboards/Reports/Policies | Business NOC dashboard (orders/min, revenue, cart abandonment) + per-tier dashboards; anomaly policy on orders/min, forecast on disk |

## 6. Load generation & realism (the "not dummy data" engine)

- **Traffic:** Locust (API journeys) + a small Playwright browser pool (real RUM sessions:
  browse → search → cart → checkout; 3–5 concurrent headless browsers is enough). Diurnal curve
  (sinusoidal RPS: low at night, peaks 11:00/20:00 IST), weekend uplift, occasional flash-sale
  spike (feeds anomaly + forecast policies honestly).
- **Data seeding:** one-time realistic seed — ~5k products (public dataset), 500 users, price
  history — so search/catalog responses vary and DB working sets are non-trivial.
- **Chaos schedule** (cron-driven, each maps to an expected correlated alert cluster):
  | Scenario | Trigger | Expected Motadata evidence |
  |---|---|---|
  | Payment outage | stop payment-svc 10 min | APM error spike, order-svc log burst, RUM checkout failures, availability alert |
  | DB pressure | pgbench against PG primary | JDBC metric alert, slow queries, checkout latency SLO burn |
  | Disk fill | dd on sv-data /var | Forecast + threshold alert, runbook cleans up (**runbook automation demo**) |
  | Link flap | VyOS interface down 2 min | Trap + syslog + NetRoute path change + flow drop, all same window |
  | Memory leak | leaky flag in cart-svc | Anomaly policy catch, agent 1s metrics |
  | DR drill (weekly) | stop PG primary, promote replica | Availability alerts, NCCM-style change, DR narrative |

---

## 7. Motadata onboarding runbook (minimal-config wiring, fully API-driven)

Credential profiles: **7** (1 SSH shared-key, 1 PowerShell, 1 SNMP v2c community, 3–4 JDBC, 1
HTTP). Discovery profiles: **~8** (Linux CIDR, Windows IP, SNMP range covering router+sim fleet,
one per DB type batch, service-check batch) — all with auto-provision + Save & Schedule.
Then: enable NCCM on VyOS monitor; create 2 trap listeners (defaults); flow settings are
port-defaults (zero config); register 2 RUM apps + APM apps; assign log parsers (JSON parser for
app logs, Linux Syslog, Windows Event); create ~10 baseline policies (CPU/mem/disk/availability +
1 anomaly + 1 forecast + APM latency + RUM Apdex + trap policy); 3 dashboards; 2 SLO profiles.
**Every step above exists as a REST endpoint (verified in Phase 1) → the generator app can do
all of it idempotently.**

## 8. The customizable generator application ("this option should be customizable")

A config-driven CLI/app — working name **`shopverse-forge`** — that renders and deploys the whole
ecosystem from one YAML and then auto-wires Motadata:

```yaml
site: { name: shopverse, appliance: "https://172.16.14.71", pat: $MOTADATA_PAT }
hosts: { app_nodes: 2, windows: true, dr_site: true, router: vyos }
databases: [postgresql, mysql, mongodb, redis]        # pick 2..4
queue: rabbitmq
services: [storefront, catalog, cart, search, order, payment, notify]  # subset ok
apm: { languages: auto, ebpf: [payment] }
rum: { apps: [storefront], sample_rate: 100 }
device_fleet: { routers: 2, switches: 3, firewalls: 1, ups: 1, printer: 1 }   # snmpsim counts
load: { profile: diurnal, peak_rps: 40, browsers: 3 }
chaos: { schedule: default, dr_drill: weekly }
pipelines: { flows: netflow, traps: on, nccm: on, netroute: on }
```

Layers: **render** (docker-compose per host + cloud-init/Ansible for VMs, agent installs, rsyslog
drops, softflowd/snmpsim units) → **deploy** (SSH push, idempotent) → **register** (Motadata REST:
credentials, discoveries, listeners, parsers, policies, RUM/APM apps, dashboards) → **verify**
(poll `/api/v1/...` until every pipeline shows data; print coverage scorecard). Adding/removing a
DB or service is a YAML edit + re-run — that's the "minimum configuration" promise, and the same
knobs become the product-side customization story.

## 9. Phased execution

| Phase | Scope | Effort |
|---|---|---|
| **A — Core loop** | sv-lb + sv-app1 + sv-data; 4 services (storefront, catalog, order, cart), PG+MySQL+Redis, Locust, SSH/JDBC/agent discovery, syslog, 1 dashboard | 2–3 days |
| **B — Full app + DEM** | remaining services, MongoDB+RabbitMQ, APM agents all languages, RUM both apps, browser load, policies/SLOs | 2–3 days |
| **C — Network & devices** | VyOS (+NCCM, NetRoute), softflowd flows, snmpsim fleet, trap replays, Windows host | 2–3 days |
| **D — HA/DR + chaos + forge** | app2 + keepalived, PG replica + DR drills, chaos schedule, wrap everything into `shopverse-forge` YAML generator | 3–5 days |

## 10. Open items needed to start

1. **VM capacity**: 6 Linux + 1 Windows VMs (or ESXi/Proxmox access to create them) on a network
   reachable from the 172.16.14.71 appliance. Can compress to 4 VMs if RAM is tight.
2. **A Windows Server ISO/license** (skip Phase C Windows if unavailable — coverage note stays).
3. **MotaAgent + APM agent packages** (download from appliance or Motadata portal?).
4. **Confirm**: is the target appliance 172.16.14.71 okay to onboard ~25 monitors + license room
   (each host/DB/device consumes a license; sim fleet counts as devices)?
