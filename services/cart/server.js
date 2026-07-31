const crypto = require("crypto");
const express = require("express");
const { createClient } = require("redis");

const SVC = process.env.SVC_NAME || "cart";
const REDIS_URL = process.env.REDIS_URL || "redis://redis:6379";
const PORT = 8083;

function logLine(level, msg, fields = {}) {
  const line = {
    ts: new Date().toISOString(),
    level,
    svc: SVC,
    msg,
    trace_id: fields.trace_id || null,
    method: fields.method || null,
    path: fields.path || null,
    status: fields.status ?? null,
    latency_ms: fields.latency_ms ?? null,
    order_id: null,
    user_id: fields.user_id || null,
  };
  if (fields.err) line.err = fields.err;
  process.stdout.write(JSON.stringify(line) + "\n");
}

// db 0 = cart storage, db 1 = fault-injection flags
const store = createClient({ url: REDIS_URL, database: 0 });
const injectDb = createClient({ url: REDIS_URL, database: 1 });
store.on("error", (e) => logLine("ERROR", "redis store error", { err: e.message }));
injectDb.on("error", (e) => logLine("ERROR", "redis inject error", { err: e.message }));

const injectCache = new Map();
async function injectVal(key) {
  const now = Date.now();
  const hit = injectCache.get(key);
  if (hit && now - hit.ts < 2000) return hit.val;
  let val = 0;
  try {
    val = parseInt(await injectDb.get(key), 10) || 0;
  } catch {
    val = 0;
  }
  injectCache.set(key, { val, ts: now });
  return val;
}

const app = express();
app.use(express.json());

// First middleware: trace id, fault injection, and the single access-log line per request.
app.use(async (req, res, next) => {
  req.traceId = req.get("X-Trace-Id") || crypto.randomUUID();
  const start = Date.now();
  res.on("finish", () => {
    const status = res.statusCode;
    logLine(status >= 500 ? "ERROR" : "INFO", `${req.method} ${req.path} ${status}`, {
      trace_id: req.traceId,
      method: req.method,
      path: req.path,
      status,
      latency_ms: Date.now() - start,
      err: status >= 500 ? res.locals.err || "internal error" : undefined,
    });
  });
  const errRate = await injectVal(`inject:${SVC}:error_rate`);
  if (Math.random() * 100 < errRate) {
    res.locals.err = "injected";
    return res.status(500).json({ error: "injected", trace_id: req.traceId });
  }
  const latencyMs = await injectVal(`inject:${SVC}:latency_ms`);
  if (latencyMs > 0) await new Promise((r) => setTimeout(r, latencyMs));
  next();
});

// Express 4 does not catch rejected promises from async handlers.
const wrap = (fn) => (req, res, next) => fn(req, res, next).catch(next);

const cartKey = (user) => `cart:${user}`;

async function readCart(user) {
  const raw = await store.get(cartKey(user));
  return raw ? JSON.parse(raw) : { items: [], updated_at: null };
}

app.get("/health", async (req, res) => {
  try {
    await store.ping();
    res.json({ status: "ok", svc: SVC, trace_id: req.traceId });
  } catch (e) {
    res.status(503).json({ status: "error", svc: SVC, err: e.message, trace_id: req.traceId });
  }
});

app.get(
  "/cart/:user",
  wrap(async (req, res) => {
    const cart = await readCart(req.params.user);
    res.json({ ...cart, trace_id: req.traceId });
  })
);

app.post(
  "/cart/:user/items",
  wrap(async (req, res) => {
    const { product_id, qty } = req.body || {};
    if (product_id === undefined || !Number.isFinite(qty) || qty <= 0) {
      return res
        .status(400)
        .json({ error: "product_id and positive qty required", trace_id: req.traceId });
    }
    const cart = await readCart(req.params.user);
    const existing = cart.items.find((i) => i.product_id === product_id);
    if (existing) existing.qty += qty;
    else cart.items.push({ product_id, qty });
    cart.updated_at = new Date().toISOString();
    await store.set(cartKey(req.params.user), JSON.stringify(cart));
    res.json({ ...cart, trace_id: req.traceId });
  })
);

app.delete(
  "/cart/:user",
  wrap(async (req, res) => {
    await store.del(cartKey(req.params.user));
    res.json({ status: "deleted", trace_id: req.traceId });
  })
);

app.use((err, req, res, _next) => {
  res.locals.err = err.message;
  res.status(500).json({ error: err.message, trace_id: req.traceId });
});

// Connect in the background so the server still comes up (health 503) when Redis is down.
store.connect().catch(() => {});
injectDb.connect().catch(() => {});

app.listen(PORT, () => logLine("INFO", `cart listening on ${PORT}`));
