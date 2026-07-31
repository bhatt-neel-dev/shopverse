package com.shopverse.catalog;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@RestController
public class ProductController {

    private final JdbcTemplate jdbc;

    ProductController(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @GetMapping("/products")
    Map<String, Object> list(@RequestParam(defaultValue = "20") int limit,
                             @RequestParam(defaultValue = "0") int offset,
                             HttpServletRequest req) {
        List<Map<String, Object>> rows = jdbc.queryForList(
                "SELECT id, name, description, price, category, stock FROM products ORDER BY id LIMIT ? OFFSET ?",
                limit, offset);
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("trace_id", trace(req));
        body.put("count", rows.size());
        body.put("products", rows);
        return body;
    }

    @GetMapping("/products/{id}")
    ResponseEntity<Map<String, Object>> get(@PathVariable int id, HttpServletRequest req) {
        List<Map<String, Object>> rows = jdbc.queryForList(
                "SELECT id, name, description, price, category, stock FROM products WHERE id = ?", id);
        if (rows.isEmpty()) {
            return ResponseEntity.status(404).body(Map.of("error", "not found", "trace_id", trace(req)));
        }
        Map<String, Object> body = new LinkedHashMap<>(rows.get(0));
        body.put("trace_id", trace(req));
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
