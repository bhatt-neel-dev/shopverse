# ShopVerse

A self-contained, single-VM e-commerce ecosystem that feeds **every Motadata AIOps ingestion
pipeline** with real, correlated data — plus a **Scenario Studio** admin panel to generate bulk
traces, inject errors, fire load spikes, and run chaos scenarios on demand.

> Built as the demo/validation ecosystem for Motadata ObserveOps (appliance: 172.16.14.71).
> Full research background: [docs/motadata-aiops-product-overview.md](docs/motadata-aiops-product-overview.md)
> and [docs/ecommerce-ecosystem-plan.md](docs/ecommerce-ecosystem-plan.md).

## The two UIs

| UI | What it is | Stack |
|---|---|---|
| **Storefront** (fake product UI) | A real e-commerce site — catalog, search, cart, checkout — used by synthetic shoppers and by you. Every click produces RUM events, APM traces, logs, DB queries, flows. | Next.js + RUM SDK |
| **Scenario Studio** (admin) | Control panel to *make things happen*: bulk trace generation, per-service error/latency injection, load spikes, log storms, trap bursts, chaos scenarios, DR drill — and a live pipeline-coverage scorecard. | React (RUM app #2) + FastAPI control-plane |

## Architecture (single VM, Docker)

```
                          ┌────────────────────── one VM ──────────────────────┐
 Browser ── RUM ──►  storefront (Next.js)     Scenario Studio (React+FastAPI)  │
                          │                        │ docker API / redis flags   │
                     nginx gateway ── HAProxy ─────┼────────────────────────────│
                          │                        ▼                            │
       catalog(Java/Tomcat) order(Spring) cart(Node) search(Py) payment(Go)     │
              │MySQL         │PostgreSQL    │Redis     │MongoDB   │             │
              └──────────────┴─── RabbitMQ ─► notify-worker (Py) ─► SMTP        │
                                                                                │
  macvlan IPs: DBs • HAProxy • VyOS(NCCM) • snmpsim fleet(router/switch/fw/UPS/printer)
  telemetry out: NetFlow(softflowd) • syslog • traps • APM(9474/9433) • RUM     │
└───────────────────────────────────────────────────────────────────────────────┘
                                     │
                        Motadata appliance 172.16.14.71
```

The **forge** layer (`forge/`) renders and deploys all of this from one YAML and auto-registers
credentials/discoveries/policies in Motadata via its REST API.

## Recommended VM spec

| Tier | vCPU | RAM | Disk | Notes |
|---|---|---|---|---|
| **Recommended** | 8 | **16 GB** | 150 GB SSD | ~30 containers + 3 headless browsers + sims, comfortable |
| Comfortable | 12 | 24 GB | 200 GB | headroom for Elasticsearch + bigger load |
| Minimum | 6 | 12 GB | 80 GB | trim sim fleet + 1 browser |

OS: **Ubuntu 24.04 LTS**. Network: same subnet reachability with 172.16.14.71 + ~20 free IPs for
macvlan device identities + internet access for image pulls.

## Repository layout

```
services/   # storefront, catalog, order, cart, search, payment, notify (one folder each)
admin/      # Scenario Studio — FastAPI control-plane + React UI
loadgen/    # Locust journeys, diurnal shaper, Playwright browser pool
deploy/     # bootstrap.sh, docker-compose files, macvlan setup, VyOS/snmpsim/softflowd units
forge/      # shopverse.yaml config + Motadata auto-registration scripts
docs/       # research + plans
```

## Status

Phase 0 — scaffold. See [docs/PLAN.md](docs/PLAN.md) for the build phases.
