package com.shopverse.order;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }

    @Bean
    ApplicationRunner initSchema(JdbcTemplate jdbc) {
        // retried in the background because postgres may still be starting when this container comes up
        return args -> new Thread(() -> {
            while (true) {
                try {
                    jdbc.execute("CREATE TABLE IF NOT EXISTS orders ("
                            + "id SERIAL PRIMARY KEY, user_id INT, total DECIMAL, status VARCHAR(20), "
                            + "trace_id VARCHAR(64), created_at TIMESTAMPTZ DEFAULT now())");
                    jdbc.execute("CREATE TABLE IF NOT EXISTS order_items ("
                            + "order_id INT, product_id INT, qty INT, price DECIMAL)");
                    return;
                } catch (Exception e) {
                    try {
                        Thread.sleep(3000);
                    } catch (InterruptedException ie) {
                        return;
                    }
                }
            }
        }, "schema-init").start();
    }
}
