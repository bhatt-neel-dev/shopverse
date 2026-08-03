# Scenario Studio

Control plane for making things happen in ShopVerse on demand. Two containers:

- **studio-api** (`admin/api`, FastAPI, :9000) — the endpoints below
- **studio-ui** (`admin/ui`, React + Vite behind nginx, :9001) — the panel; proxies `/api/*` to studio-api

## studio-api endpoints

| Endpoint | What it does |
|---|---|
| `GET /health` | liveness |
| `GET /inject` | current per-service fault-injection flags (Redis db 1) |
| `POST /inject` `{svc, error_rate?, latency_ms?}` | set flags for one service |
| `POST /inject/clear?svc=` | clear one service's flags (all services when omitted) |
| `POST /traces/bulk` `{journey, count, concurrency, error_rate, latency_ms, tag}` | fire N **real** journeys (browse / search / checkout) through the gateway → genuine traces; optional temporary injection flags are restored afterwards |
| `POST /load/spike` `{magnitude, duration_s}` | ramp Locust to `baseline × magnitude` users, auto-restore after the duration (`GET` for status, `POST /load/spike/stop` to end early) |
| `POST /logs/storm` `{severity, pattern, count, interval_ms}` | burst of contract-format log lines tagged with a storm id |
| `GET /chaos` | scenario states |
| `POST /chaos/{scenario}` `{duration_s}` | stop the scenario's containers, auto-restart after the duration; scenarios: `payment-outage`, `db-outage`, `cache-outage`, `queue-outage`, `search-outage` |
| `POST /chaos/{scenario}/stop` | recover early |
| `GET /coverage` | live scorecard: every service health, Locust state, RabbitMQ queue depth, active injection flags |
| `GET /history?n=` | scenario history (newest first) — the ground-truth timeline to validate Motadata alerts against |

Every action is appended to `/data/history.jsonl` (volume `studio-data`) with its
timestamp, parameters, and result.
