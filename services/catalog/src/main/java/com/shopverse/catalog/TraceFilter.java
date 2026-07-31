package com.shopverse.catalog;

import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import redis.clients.jedis.DefaultJedisClientConfig;
import redis.clients.jedis.HostAndPort;
import redis.clients.jedis.Jedis;
import redis.clients.jedis.JedisPool;

import java.io.IOException;
import java.net.URI;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.ThreadLocalRandom;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class TraceFilter implements Filter {

    static final String SVC = System.getenv().getOrDefault("SVC_NAME", "catalog");

    private final JedisPool redis;
    private volatile int errorRate;
    private volatile int latencyMs;
    private volatile long fetchedAt;

    public TraceFilter() {
        URI u = URI.create(System.getenv().getOrDefault("REDIS_URL", "redis://redis:6379"));
        int port = u.getPort() > 0 ? u.getPort() : 6379;
        redis = new JedisPool(new HostAndPort(u.getHost(), port),
                DefaultJedisClientConfig.builder().database(1).timeoutMillis(2000).build());
    }

    @Override
    public void doFilter(ServletRequest request, ServletResponse response, FilterChain chain)
            throws IOException {
        HttpServletRequest req = (HttpServletRequest) request;
        HttpServletResponse res = (HttpServletResponse) response;

        String traceId = req.getHeader("X-Trace-Id");
        if (traceId == null || traceId.isBlank()) traceId = UUID.randomUUID().toString();
        req.setAttribute("trace_id", traceId);
        res.setHeader("X-Trace-Id", traceId);

        long start = System.nanoTime();
        refreshInjection();
        if (latencyMs > 0) {
            try {
                Thread.sleep(latencyMs);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }
        if (errorRate > 0 && ThreadLocalRandom.current().nextInt(100) < errorRate) {
            writeJson(res, 500, "{\"error\":\"injected\",\"trace_id\":\"" + traceId + "\"}");
            emit(req, traceId, 500, start, "injected");
            return;
        }

        String err = null;
        try {
            chain.doFilter(request, response);
        } catch (Exception e) {
            err = e.getMessage() == null ? e.getClass().getSimpleName() : e.getMessage();
            if (!res.isCommitted()) {
                writeJson(res, 500, "{\"error\":\"internal\",\"trace_id\":\"" + traceId + "\"}");
            }
        }
        emit(req, traceId, res.getStatus(), start, err);
    }

    private static void writeJson(HttpServletResponse res, int status, String body) throws IOException {
        res.setStatus(status);
        res.setContentType("application/json");
        res.getWriter().write(body);
    }

    private void emit(HttpServletRequest req, String traceId, int status, long startNanos, String err) {
        long latency = (System.nanoTime() - startNanos) / 1_000_000;
        String level = status >= 500 ? "ERROR" : status >= 400 ? "WARN" : "INFO";
        String path = req.getRequestURI();
        JsonLog.emit(level, SVC, req.getMethod() + " " + path + " " + status, traceId,
                req.getMethod(), path, status, latency,
                (Integer) req.getAttribute("order_id"), (Integer) req.getAttribute("user_id"), err);
    }

    private void refreshInjection() {
        long now = System.currentTimeMillis();
        if (now - fetchedAt < 2000) return;
        fetchedAt = now;
        try (Jedis j = redis.getResource()) {
            List<String> v = j.mget("inject:" + SVC + ":error_rate", "inject:" + SVC + ":latency_ms");
            errorRate = parse(v.get(0));
            latencyMs = parse(v.get(1));
        } catch (Exception e) {
            errorRate = 0;
            latencyMs = 0;
        }
    }

    private static int parse(String v) {
        if (v == null) return 0;
        try {
            return Integer.parseInt(v.trim());
        } catch (NumberFormatException e) {
            return 0;
        }
    }
}
