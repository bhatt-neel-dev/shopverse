package com.shopverse.catalog;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }

    @Bean
    ApplicationRunner initSchema(JdbcTemplate jdbc) {
        // retried in the background because mysql may still be starting when this container comes up
        return args -> new Thread(() -> {
            while (true) {
                try {
                    jdbc.execute("CREATE TABLE IF NOT EXISTS products ("
                            + "id INT PRIMARY KEY, name VARCHAR(200), description TEXT, "
                            + "price DECIMAL(10,2), category VARCHAR(60), stock INT)");
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
