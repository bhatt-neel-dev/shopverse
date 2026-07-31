package com.shopverse.catalog;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;

import java.time.Instant;
import java.time.temporal.ChronoUnit;

final class JsonLog {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    private JsonLog() {
    }

    static void emit(String level, String svc, String msg, String traceId, String method,
                     String path, int status, long latencyMs, Integer orderId, Integer userId, String err) {
        ObjectNode n = MAPPER.createObjectNode();
        n.put("ts", Instant.now().truncatedTo(ChronoUnit.MILLIS).toString());
        n.put("level", level);
        n.put("svc", svc);
        n.put("msg", msg);
        n.put("trace_id", traceId);
        n.put("method", method);
        n.put("path", path);
        n.put("status", status);
        n.put("latency_ms", latencyMs);
        if (orderId == null) n.putNull("order_id"); else n.put("order_id", orderId);
        if (userId == null) n.putNull("user_id"); else n.put("user_id", userId);
        if (err != null) n.put("err", err);
        System.out.println(n);
    }
}
