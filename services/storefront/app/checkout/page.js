"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import ErrorBanner from "../../components/ErrorBanner";
import { apiFetch, DEMO_USER_ID, loadDetailedCart } from "../../lib/api";

export default function CheckoutPage() {
  const [items, setItems] = useState(null);
  const [error, setError] = useState(null);
  const [placing, setPlacing] = useState(false);
  const [result, setResult] = useState(null);

  useEffect(() => {
    loadDetailedCart().then(setItems).catch(setError);
  }, []);

  const total = (items || []).reduce((sum, i) => sum + i.price * i.qty, 0);

  async function placeOrder() {
    setPlacing(true);
    setError(null);
    setResult(null);
    try {
      const order = await apiFetch("orders", {
        method: "POST",
        body: JSON.stringify({
          user_id: DEMO_USER_ID,
          items: items.map((i) => ({ product_id: i.product_id, qty: i.qty, price: i.price })),
        }),
      });
      setResult(order);
      if (order.status === "approved") {
        await apiFetch(`cart/${DEMO_USER_ID}`, { method: "DELETE" }).catch(() => {});
        setItems([]);
      }
    } catch (err) {
      setError(err);
    } finally {
      setPlacing(false);
    }
  }

  return (
    <main className="container">
      <h1>Checkout</h1>
      <ErrorBanner error={error} />

      {result && (
        <div className={`order-result ${result.status}`}>
          {result.status === "approved" && <h2>Order #{result.order_id} confirmed 🎉</h2>}
          {result.status === "declined" && <h2>Payment declined for order #{result.order_id}</h2>}
          {result.status !== "approved" && result.status !== "declined" && (
            <h2>Order #{result.order_id}: {result.status}</h2>
          )}
          <p>
            Total ${Number(result.total).toFixed(2)} · trace_id <code>{result.trace_id}</code>
          </p>
          <Link href="/">Continue shopping</Link>
        </div>
      )}

      {items === null && !error && <p className="muted">Loading…</p>}
      {items !== null && items.length === 0 && !result && (
        <p className="muted">
          Nothing to check out. <Link href="/">Browse products</Link>.
        </p>
      )}
      {items !== null && items.length > 0 && (
        <>
          <ul className="checkout-list">
            {items.map((i) => (
              <li key={i.product_id}>
                {i.name} × {i.qty} — ${(i.price * i.qty).toFixed(2)}
              </li>
            ))}
          </ul>
          <p className="price big">Total: ${total.toFixed(2)}</p>
          <button onClick={placeOrder} disabled={placing}>
            {placing ? "Placing order…" : "Place order"}
          </button>
        </>
      )}
    </main>
  );
}
