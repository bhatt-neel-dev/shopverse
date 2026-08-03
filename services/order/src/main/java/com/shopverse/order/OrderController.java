package com.shopverse.order;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import java.math.BigDecimal;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.sql.PreparedStatement;
import java.sql.Statement;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@RestController
public class OrderController {

    private static final String PAYMENT_URL =
            System.getenv().getOrDefault("PAYMENT_URL", "http://payment:8085");

    private final JdbcTemplate jdbc;
    private final RabbitPublisher rabbit;
    private final ObjectMapper mapper = new ObjectMapper();
    private final HttpClient http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(3))
            .build();

    OrderController(JdbcTemplate jdbc, RabbitPublisher rabbit) {
        this.jdbc = jdbc;
        this.rabbit = rabbit;
    }

    @PostMapping("/orders")
    ResponseEntity<Map<String, Object>> create(@RequestBody JsonNode body, HttpServletRequest req) {
        String traceId = trace(req);

        JsonNode items = body.path("items");
        int userId = body.path("user_id").asInt(0);
        if (!items.isArray() || items.isEmpty()) {
            return ResponseEntity.badRequest()
                    .body(Map.of("error", "items array required", "trace_id", traceId));
        }
        req.setAttribute("user_id", userId);

        BigDecimal total = BigDecimal.ZERO;
        for (JsonNode item : items) {
            BigDecimal price = new BigDecimal(item.path("price").asText("0"));
            total = total.add(price.multiply(BigDecimal.valueOf(item.path("qty").asInt(1))));
        }
        BigDecimal finalTotal = total;

        KeyHolder keys = new GeneratedKeyHolder();
        jdbc.update(con -> {
            PreparedStatement ps = con.prepareStatement(
                    "INSERT INTO orders(user_id, total, status, trace_id) VALUES(?,?,?,?)",
                    Statement.RETURN_GENERATED_KEYS);
            ps.setInt(1, userId);
            ps.setBigDecimal(2, finalTotal);
            ps.setString(3, "pending");
            ps.setString(4, traceId);
            return ps;
        }, keys);
        int orderId = ((Number) keys.getKeys().get("id")).intValue();
        req.setAttribute("order_id", orderId);

        for (JsonNode item : items) {
            jdbc.update("INSERT INTO order_items(order_id, product_id, qty, price) VALUES(?,?,?,?)",
                    orderId, item.path("product_id").asInt(), item.path("qty").asInt(1),
                    new BigDecimal(item.path("price").asText("0")));
        }

        String status = pay(orderId, total, traceId);
        jdbc.update("UPDATE orders SET status = ? WHERE id = ?", status, orderId);

        ObjectNode event = mapper.createObjectNode();
        event.put("order_id", orderId);
        event.put("user_id", userId);
        event.put("total", total);
        event.put("status", status);
        event.put("trace_id", traceId);
        rabbit.publish(event.toString(), traceId, orderId);

        Map<String, Object> resBody = new LinkedHashMap<>();
        resBody.put("order_id", orderId);
        resBody.put("status", status);
        resBody.put("total", total);
        resBody.put("trace_id", traceId);
        int code = "payment_error".equals(status) ? 502 : 201;
        return ResponseEntity.status(code).body(resBody);
    }

    /** Calls payment /pay; returns approved / declined / payment_error. */
    private String pay(int orderId, BigDecimal amount, String traceId) {
        try {
            String payload = mapper.createObjectNode()
                    .put("order_id", orderId)
                    .put("amount", amount)
                    .toString();
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(PAYMENT_URL + "/pay"))
                    .timeout(Duration.ofSeconds(10))
                    .header("Content-Type", "application/json")
                    .header("X-Trace-Id", traceId)
                    .POST(HttpRequest.BodyPublishers.ofString(payload))
                    .build();
            HttpResponse<String> response = http.send(request, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() == 200) return "approved";
            if (response.statusCode() == 402) return "declined";
            JsonLog.emit("ERROR", TraceFilter.SVC, "payment call failed " + response.statusCode(),
                    traceId, "POST", "/pay", response.statusCode(), 0, orderId, null,
                    "payment returned " + response.statusCode());
            return "payment_error";
        } catch (Exception e) {
            if (e instanceof InterruptedException) Thread.currentThread().interrupt();
            JsonLog.emit("ERROR", TraceFilter.SVC, "payment call failed", traceId,
                    "POST", "/pay", 0, 0, orderId, null, e.getMessage());
            return "payment_error";
        }
    }

    @GetMapping("/orders/{id}")
    ResponseEntity<Map<String, Object>> get(@PathVariable int id, HttpServletRequest req) {
        String traceId = trace(req);
        List<Map<String, Object>> rows = jdbc.queryForList(
                "SELECT id, user_id, total, status, trace_id, created_at FROM orders WHERE id = ?", id);
        if (rows.isEmpty()) {
            return ResponseEntity.status(404).body(Map.of("error", "not found", "trace_id", traceId));
        }
        req.setAttribute("order_id", id);
        Map<String, Object> body = new LinkedHashMap<>(rows.get(0));
        body.put("items", jdbc.queryForList(
                "SELECT product_id, qty, price FROM order_items WHERE order_id = ?", id));
        body.put("trace_id", traceId);
        return ResponseEntity.ok(body);
    }

    @GetMapping("/health")
    ResponseEntity<Map<String, Object>> health(HttpServletRequest req) {
        try {
            jdbc.queryForObject("SELECT 1", Integer.class);
            return ResponseEntity.ok(Map.of("status", "ok", "svc", TraceFilter.SVC, "trace_id", trace(req)));
        } catch (Exception e) {
            return ResponseEntity.status(503)
                    .body(Map.of("status", "error", "svc", TraceFilter.SVC, "trace_id", trace(req)));
        }
    }

    private static String trace(HttpServletRequest req) {
        return (String) req.getAttribute("trace_id");
    }
}
