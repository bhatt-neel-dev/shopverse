"""Notify worker: consumes RabbitMQ `order.events` and logs a contract-format
INFO line per order (stand-in for the SMTP notification path). Reconnects
forever so it survives RabbitMQ restarts and chaos scenarios."""

import json
import os
import time
from datetime import datetime, timezone

import pika

SVC = os.environ.get("SVC_NAME", "notify")
RABBIT_URL = os.environ.get("RABBIT_URL", "amqp://shop:shoppass@rabbitmq:5672/")
QUEUE = "order.events"


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def log_line(level, msg, trace_id=None, order_id=None, user_id=None, err=None):
    line = {
        "ts": _ts(),
        "level": level,
        "svc": SVC,
        "msg": msg,
        "trace_id": trace_id,
        "method": None,
        "path": None,
        "status": None,
        "latency_ms": None,
        "order_id": order_id,
        "user_id": user_id,
    }
    if err:
        line["err"] = err
    print(json.dumps(line), flush=True)


def on_message(channel, method, _properties, body):
    try:
        event = json.loads(body)
    except json.JSONDecodeError as e:
        log_line("WARN", "dropping malformed order event", err=str(e))
        channel.basic_ack(delivery_tag=method.delivery_tag)
        return
    order_id = event.get("order_id")
    status = event.get("status", "unknown")
    log_line(
        "INFO",
        f"order notification sent: order {order_id} {status}",
        trace_id=event.get("trace_id"),
        order_id=order_id,
        user_id=event.get("user_id"),
    )
    channel.basic_ack(delivery_tag=method.delivery_tag)


def main():
    while True:
        try:
            connection = pika.BlockingConnection(pika.URLParameters(RABBIT_URL))
            channel = connection.channel()
            channel.queue_declare(queue=QUEUE, durable=True)
            channel.basic_qos(prefetch_count=16)
            channel.basic_consume(queue=QUEUE, on_message_callback=on_message)
            log_line("INFO", f"consuming {QUEUE}")
            channel.start_consuming()
        except Exception as e:  # noqa: BLE001 — reconnect on any broker error
            log_line("WARN", "rabbitmq unavailable, retrying in 3s", err=str(e))
            time.sleep(3)


if __name__ == "__main__":
    main()
