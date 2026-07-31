package main

import (
	"context"
	cryptorand "crypto/rand"
	"database/sql"
	"encoding/json"
	"fmt"
	"math/rand/v2"
	"net/http"
	"os"
	"strconv"
	"sync"
	"time"

	_ "github.com/lib/pq"
	goredis "github.com/redis/go-redis/v9"
)

var (
	svc = getenv("SVC_NAME", "payment")
	db  *sql.DB
	rdb *goredis.Client

	cacheMu     sync.Mutex
	injectCache = map[string]cacheEntry{}
)

type cacheEntry struct {
	val int
	at  time.Time
}

func getenv(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func uuid4() string {
	b := make([]byte, 16)
	if _, err := cryptorand.Read(b); err != nil {
		return strconv.FormatInt(time.Now().UnixNano(), 16)
	}
	b[6] = (b[6] & 0x0f) | 0x40
	b[8] = (b[8] & 0x3f) | 0x80
	return fmt.Sprintf("%x-%x-%x-%x-%x", b[0:4], b[4:6], b[6:8], b[8:10], b[10:16])
}

func logLine(level, msg, traceID, method, path string, status, latencyMs int, orderID any, errMsg string) {
	line := map[string]any{
		"ts":         time.Now().UTC().Format("2006-01-02T15:04:05.000Z"),
		"level":      level,
		"svc":        svc,
		"msg":        msg,
		"trace_id":   traceID,
		"method":     method,
		"path":       path,
		"status":     status,
		"latency_ms": latencyMs,
		"order_id":   orderID,
		"user_id":    nil,
	}
	if errMsg != "" {
		line["err"] = errMsg
	}
	out, _ := json.Marshal(line)
	fmt.Println(string(out))
}

func injectVal(key string) int {
	cacheMu.Lock()
	if e, ok := injectCache[key]; ok && time.Since(e.at) < 2*time.Second {
		cacheMu.Unlock()
		return e.val
	}
	cacheMu.Unlock()
	val := 0
	ctx, cancel := context.WithTimeout(context.Background(), 500*time.Millisecond)
	defer cancel()
	if s, err := rdb.Get(ctx, key).Result(); err == nil {
		if n, err := strconv.Atoi(s); err == nil {
			val = n
		}
	}
	cacheMu.Lock()
	injectCache[key] = cacheEntry{val: val, at: time.Now()}
	cacheMu.Unlock()
	return val
}

type recorder struct {
	http.ResponseWriter
	status  int
	orderID any
	errMsg  string
}

func (r *recorder) WriteHeader(code int) {
	r.status = code
	r.ResponseWriter.WriteHeader(code)
}

func writeJSON(w http.ResponseWriter, status int, body map[string]any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(body)
}

// contract wraps a handler with trace propagation, fault injection (first),
// and the single access-log line per request.
func contract(next func(*recorder, *http.Request, string)) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		traceID := r.Header.Get("X-Trace-Id")
		if traceID == "" {
			traceID = uuid4()
		}
		start := time.Now()
		rec := &recorder{ResponseWriter: w, status: 200}
		if rand.IntN(100) < injectVal("inject:"+svc+":error_rate") {
			rec.errMsg = "injected"
			writeJSON(rec, 500, map[string]any{"error": "injected", "trace_id": traceID})
		} else {
			if ms := injectVal("inject:" + svc + ":latency_ms"); ms > 0 {
				time.Sleep(time.Duration(ms) * time.Millisecond)
			}
			next(rec, r, traceID)
		}
		level := "INFO"
		if rec.status >= 500 {
			level = "ERROR"
		}
		logLine(level,
			fmt.Sprintf("%s %s %d", r.Method, r.URL.Path, rec.status),
			traceID, r.Method, r.URL.Path, rec.status,
			int(time.Since(start).Milliseconds()), rec.orderID, rec.errMsg)
	}
}

type payReq struct {
	OrderID int     `json:"order_id"`
	Amount  float64 `json:"amount"`
}

func payHandler(rec *recorder, r *http.Request, traceID string) {
	if r.Method != http.MethodPost {
		writeJSON(rec, 405, map[string]any{"error": "method not allowed", "trace_id": traceID})
		return
	}
	var req payReq
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(rec, 400, map[string]any{"error": "invalid body: " + err.Error(), "trace_id": traceID})
		return
	}
	rec.orderID = req.OrderID
	status, code := "approved", 200
	if rand.IntN(100) >= 92 {
		status, code = "declined", 402
	}
	if _, err := db.Exec(
		"INSERT INTO ledger(order_id, amount, status, trace_id) VALUES($1,$2,$3,$4)",
		req.OrderID, req.Amount, status, traceID); err != nil {
		rec.errMsg = err.Error()
		writeJSON(rec, 500, map[string]any{"error": err.Error(), "trace_id": traceID})
		return
	}
	writeJSON(rec, code, map[string]any{"status": status, "trace_id": traceID})
}

func healthHandler(rec *recorder, r *http.Request, traceID string) {
	if err := db.Ping(); err != nil {
		writeJSON(rec, 503, map[string]any{"status": "error", "svc": svc, "err": err.Error(), "trace_id": traceID})
		return
	}
	writeJSON(rec, 200, map[string]any{"status": "ok", "svc": svc, "trace_id": traceID})
}

func ensureSchema() {
	for {
		_, err := db.Exec(`CREATE TABLE IF NOT EXISTS ledger(
			id SERIAL PRIMARY KEY,
			order_id INT,
			amount DECIMAL,
			status VARCHAR(20),
			trace_id VARCHAR(64),
			created_at TIMESTAMPTZ DEFAULT now())`)
		if err == nil {
			return
		}
		logLine("WARN", "ledger schema not ready, retrying", "", "", "", 0, 0, nil, err.Error())
		time.Sleep(3 * time.Second)
	}
}

func main() {
	dsn := fmt.Sprintf("host=%s dbname=%s user=%s password=%s sslmode=disable",
		getenv("PG_HOST", "postgres"), getenv("PG_DB", "shopverse"),
		getenv("PG_USER", "shop"), getenv("PG_PASSWORD", "shoppass"))
	var err error
	if db, err = sql.Open("postgres", dsn); err != nil {
		logLine("ERROR", "cannot open postgres", "", "", "", 0, 0, nil, err.Error())
		os.Exit(1)
	}
	// keep serving (health returns 503) while PG comes up
	go ensureSchema()

	opt, err := goredis.ParseURL(getenv("REDIS_URL", "redis://redis:6379"))
	if err != nil {
		logLine("ERROR", "bad REDIS_URL", "", "", "", 0, 0, nil, err.Error())
		os.Exit(1)
	}
	opt.DB = 1
	rdb = goredis.NewClient(opt)

	http.HandleFunc("/pay", contract(payHandler))
	http.HandleFunc("/health", contract(healthHandler))
	logLine("INFO", "payment listening on 8085", "", "", "", 0, 0, nil, "")
	if err := http.ListenAndServe(":8085", nil); err != nil {
		logLine("ERROR", "server exited", "", "", "", 0, 0, nil, err.Error())
		os.Exit(1)
	}
}
