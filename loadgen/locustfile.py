"""Synthetic shopper journeys. Web UI on :8089; Scenario Studio drives spikes via the REST API.

LOAD_PROFILE=diurnal enables a sinusoidal day-shaped baseline; `constant` (default) leaves
user count to the web UI / studio.
"""
import math
import os
import random
import time
import uuid

from locust import HttpUser, LoadTestShape, between, task

WORDS = ["aurora", "nimbus", "vertex", "cobalt", "ember", "lunar", "quartz", "watch",
         "sneakers", "lamp", "keyboard", "camera", "jacket", "speaker", "drone"]


class Shopper(HttpUser):
    wait_time = between(1, 4)

    def on_start(self):
        self.user_id = random.randint(1000, 1999)

    def _headers(self):
        return {"X-Trace-Id": str(uuid.uuid4()), "X-Load-Tag": "locust-baseline"}

    @task(6)
    def browse(self):
        h = self._headers()
        with self.client.get("/api/catalog/products?limit=24", headers=h,
                             name="/api/catalog/products", catch_response=True) as r:
            if r.status_code != 200:
                r.failure(f"status {r.status_code}")
                return
        pid = random.randint(1, 5000)
        self.client.get(f"/api/catalog/products/{pid}", headers=h,
                        name="/api/catalog/products/[id]")

    @task(3)
    def search(self):
        q = random.choice(WORDS)
        self.client.get(f"/api/search?q={q}", headers=self._headers(), name="/api/search")

    @task(2)
    def cart_and_checkout(self):
        h = self._headers()
        items = []
        for _ in range(random.randint(1, 3)):
            pid = random.randint(1, 5000)
            qty = random.randint(1, 3)
            self.client.post(f"/api/cart/{self.user_id}/items",
                             json={"product_id": pid, "qty": qty}, headers=h,
                             name="/api/cart/[user]/items")
            items.append({"product_id": pid, "qty": qty,
                          "price": round(random.uniform(4.99, 899.99), 2)})
        if random.random() < 0.6:  # 40% cart abandonment, on purpose
            self.client.post("/api/orders", json={"user_id": self.user_id, "items": items},
                             headers=h, name="/api/orders")
            self.client.delete(f"/api/cart/{self.user_id}", headers=h,
                               name="/api/cart/[user]")


if os.environ.get("LOAD_PROFILE") == "diurnal":

    class DiurnalShape(LoadTestShape):
        """Sinusoidal daily curve: trough ~03:00, peak ~15:00 local, plus jitter."""
        base = int(os.environ.get("BASELINE_USERS", "5"))

        def tick(self):
            hour = time.localtime().tm_hour + time.localtime().tm_min / 60
            factor = 0.5 + 0.5 * math.sin((hour - 9) / 24 * 2 * math.pi)
            users = max(1, round(self.base * (0.4 + 1.6 * factor)))
            return users, max(1, users // 4)
