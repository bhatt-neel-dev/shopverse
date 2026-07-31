package com.shopverse.order;

import com.rabbitmq.client.Channel;
import com.rabbitmq.client.Connection;
import com.rabbitmq.client.ConnectionFactory;
import com.rabbitmq.client.MessageProperties;
import org.springframework.stereotype.Component;

import java.nio.charset.StandardCharsets;

/**
 * Publishes order events to the durable queue "order.events" (default exchange).
 * Connection is lazy and self-healing; a publish failure never fails the order —
 * it logs ERROR and moves on (notify is a best-effort side channel).
 */
@Component
public class RabbitPublisher {

    static final String QUEUE = "order.events";

    private final ConnectionFactory factory = new ConnectionFactory();
    private Connection connection;
    private Channel channel;

    public RabbitPublisher() throws Exception {
        factory.setUri(System.getenv().getOrDefault("RABBIT_URL", "amqp://shop:shoppass@rabbitmq:5672/"));
        factory.setAutomaticRecoveryEnabled(true);
        factory.setConnectionTimeout(3000);
    }

    public synchronized void publish(String json, String traceId, int orderId) {
        try {
            ensureChannel();
            channel.basicPublish("", QUEUE, MessageProperties.PERSISTENT_TEXT_PLAIN,
                    json.getBytes(StandardCharsets.UTF_8));
        } catch (Exception e) {
            channel = null;
            JsonLog.emit("ERROR", TraceFilter.SVC, "failed to publish order event", traceId,
                    null, null, 0, 0, orderId, null, e.getMessage());
        }
    }

    private void ensureChannel() throws Exception {
        if (channel != null && channel.isOpen()) return;
        if (connection == null || !connection.isOpen()) {
            connection = factory.newConnection();
        }
        channel = connection.createChannel();
        channel.queueDeclare(QUEUE, true, false, false, null);
    }
}
