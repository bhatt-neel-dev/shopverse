"""Idempotent seeder: 5000 products into MySQL (catalog) and MongoDB (search)."""
import os
import random
import sys
import time

import pymysql
from pymongo import MongoClient, TEXT

ADJECTIVES = ["Aurora", "Nimbus", "Vertex", "Cobalt", "Ember", "Lunar", "Quartz", "Rustic",
              "Velvet", "Titan", "Breeze", "Onyx", "Ivory", "Crimson", "Zephyr", "Solar",
              "Nova", "Atlas", "Pixel", "Echo"]
NOUNS = ["Headphones", "Backpack", "Sneakers", "Watch", "Lamp", "Keyboard", "Mug", "Jacket",
         "Speaker", "Notebook", "Camera", "Bottle", "Chair", "Monitor", "Charger", "Wallet",
         "Sunglasses", "Drone", "Blender", "Router"]
CATEGORIES = ["electronics", "fashion", "home", "sports", "office", "outdoors", "kitchen", "toys"]

N_PRODUCTS = 5000


def build_products():
    rng = random.Random(42)
    products = []
    for pid in range(1, N_PRODUCTS + 1):
        name = f"{rng.choice(ADJECTIVES)} {rng.choice(NOUNS)} {pid}"
        cat = rng.choice(CATEGORIES)
        price = round(rng.uniform(4.99, 899.99), 2)
        desc = (f"The {name} is a premium {cat} product with outstanding build quality, "
                f"rated {rng.randint(3, 5)} stars by our shoppers.")
        products.append((pid, name, desc, price, cat, rng.randint(0, 500)))
    return products


def wait_for(fn, name, attempts=60):
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:
            print(f"waiting for {name} ({i}): {e}", flush=True)
            time.sleep(2)
    print(f"{name} never became ready", flush=True)
    sys.exit(1)


def seed_mysql(products):
    conn = wait_for(lambda: pymysql.connect(
        host=os.environ["MYSQL_HOST"], user=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"], database=os.environ["MYSQL_DB"]), "mysql")
    with conn.cursor() as cur:
        cur.execute("""CREATE TABLE IF NOT EXISTS products(
            id INT PRIMARY KEY, name VARCHAR(200), description TEXT,
            price DECIMAL(10,2), category VARCHAR(60), stock INT)""")
        cur.execute("SELECT COUNT(*) FROM products")
        if cur.fetchone()[0] >= N_PRODUCTS:
            print("mysql already seeded", flush=True)
        else:
            cur.executemany(
                "REPLACE INTO products(id,name,description,price,category,stock) "
                "VALUES(%s,%s,%s,%s,%s,%s)", products)
            print(f"mysql seeded {len(products)} products", flush=True)
    conn.commit()
    conn.close()


def seed_mongo(products):
    client = MongoClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=3000)
    db = wait_for(lambda: client.get_database(), "mongo")
    wait_for(lambda: client.admin.command("ping"), "mongo-ping")
    col = db["products"]
    if col.estimated_document_count() < N_PRODUCTS:
        col.delete_many({})
        col.insert_many([
            {"_id": p[0], "id": p[0], "name": p[1], "description": p[2],
             "price": float(p[3]), "category": p[4], "stock": p[5]} for p in products])
        print(f"mongo seeded {len(products)} products", flush=True)
    else:
        print("mongo already seeded", flush=True)
    col.create_index([("name", TEXT), ("description", TEXT), ("category", TEXT)])


if __name__ == "__main__":
    prods = build_products()
    seed_mysql(prods)
    seed_mongo(prods)
    print("seed complete", flush=True)
