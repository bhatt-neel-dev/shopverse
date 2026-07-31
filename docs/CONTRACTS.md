# ShopVerse — Service Contracts (all services MUST follow this)

## Trace propagation
- Every service honors incoming header `X-Trace-Id`; if absent, generate `uuid4`.
- Pass `X-Trace-Id` on every downstream HTTP call and include it in every log line and in the
  JSON response field `trace_id` (top level).

## Logging (stdout, one JSON object per line)
```json
{"ts":"2026-07-31T10:00:00.123Z","level":"INFO","svc":"catalog","msg":"GET /products 200",
 "trace_id":"...","method":"GET","path":"/products","status":200,"latency_ms":12,
 "order_id":null,"user_id":null}
```
`level` ∈ DEBUG/INFO/WARN/ERROR. Errors include `"err"` with the exception message.

## Fault injection (every HTTP service, first middleware in chain)
Read Redis **db 1** (`REDIS_URL` host, db index 1), cache values for 2s:
- `inject:<svc>:error_rate`  → int 0–100; with that probability return HTTP 500
  `{"error":"injected","trace_id":...}` and log ERROR.
- `inject:<svc>:latency_ms`  → int; sleep that many ms before handling.
Missing keys = 0. `<svc>` is the service name below.

## Services, ports, endpoints
| svc | tech | port | endpoints |
|---|---|---|---|
| storefront | Next.js | 3000 | UI pages: `/` (product grid), `/product/[id]`, `/cart`, `/checkout` (calls gateway) |
| catalog | Java 17 Spring Boot | 8081 | `GET /products?limit=&offset=`, `GET /products/{id}`, `GET /health` (MySQL) |
| order | Java 17 Spring Boot | 8082 | `POST /orders {user_id,items:[{product_id,qty,price}]}` → calls payment `/pay`, INSERT into PG, publish RabbitMQ `order.events`; `GET /orders/{id}`; `GET /health` |
| cart | Node 20 Express | 8083 | `GET /cart/{user}`, `POST /cart/{user}/items {product_id,qty}`, `DELETE /cart/{user}`, `GET /health` (Redis db 0, key `cart:<user>` JSON) |
| search | Python 3.12 FastAPI | 8084 | `GET /search?q=`, `GET /health` (Mongo text index on `products`) |
| payment | Go 1.22 | 8085 | `POST /pay {order_id,amount}` → 92% `{"status":"approved"}`, 8% `{"status":"declined"}` (HTTP 402); writes row to PG `ledger`; `GET /health` |
| notify | Python 3.12 worker | — | consume `order.events`, log INFO with order_id + trace_id |
| studio-api | Python 3.12 FastAPI | 9000 | see admin/README |
| studio-ui | React (Vite) | 9001 | Scenario Studio UI |
| gateway | nginx | 8080 | `/api/catalog/*→catalog:8081/*`, `/api/orders*→order:8082/orders*`, `/api/cart/*→cart:8083/cart/*`, `/api/search*→search:8084/search*`, `/api/pay*→payment:8085/pay*` (strip `/api/<name>` prefix, keep rest) |

## Env vars (read exactly these)
```
MYSQL_HOST=mysql MYSQL_DB=shopverse MYSQL_USER=shop MYSQL_PASSWORD=shoppass
PG_HOST=postgres PG_DB=shopverse PG_USER=shop PG_PASSWORD=shoppass
MONGO_URL=mongodb://mongo:27017/shopverse
REDIS_URL=redis://redis:6379
RABBIT_URL=amqp://shop:shoppass@rabbitmq:5672/
GATEWAY_URL=http://gateway:8080          # storefront/loadgen only
SVC_NAME=<svc>                            # used for injection keys + logs
```

## Schema ownership (create idempotently on startup)
- catalog: MySQL `products(id INT PK, name VARCHAR(200), description TEXT, price DECIMAL(10,2), category VARCHAR(60), stock INT)` — seeded externally, CREATE TABLE IF NOT EXISTS only.
- order: PG `orders(id SERIAL PK, user_id INT, total DECIMAL, status VARCHAR(20), trace_id VARCHAR(64), created_at TIMESTAMPTZ DEFAULT now())` and `order_items(order_id INT, product_id INT, qty INT, price DECIMAL)`.
- payment: PG `ledger(id SERIAL PK, order_id INT, amount DECIMAL, status VARCHAR(20), trace_id VARCHAR(64), created_at TIMESTAMPTZ DEFAULT now())`.

## Docker
Each service dir has a `Dockerfile` (multi-stage where a build step exists), `EXPOSE <port>`,
and starts with plain `CMD`. No compose files inside service dirs — the root
`deploy/docker-compose.yml` owns orchestration. Health endpoints return
`{"status":"ok","svc":"<name>"}` 200 when dependencies are reachable, 503 otherwise.
