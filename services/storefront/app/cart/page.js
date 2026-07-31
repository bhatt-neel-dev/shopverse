"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import ErrorBanner from "../../components/ErrorBanner";
import { apiFetch, DEMO_USER_ID, loadDetailedCart } from "../../lib/api";

export default function CartPage() {
  const [items, setItems] = useState(null);
  const [error, setError] = useState(null);

  function refresh() {
    loadDetailedCart().then(setItems).catch(setError);
  }

  useEffect(refresh, []);

  async function clearCart() {
    setError(null);
    try {
      await apiFetch(`cart/${DEMO_USER_ID}`, { method: "DELETE" });
      setItems([]);
    } catch (err) {
      setError(err);
    }
  }

  const total = (items || []).reduce((sum, i) => sum + i.price * i.qty, 0);

  return (
    <main className="container">
      <h1>Your cart</h1>
      <ErrorBanner error={error} />
      {items === null && !error && <p className="muted">Loading…</p>}
      {items !== null && items.length === 0 && (
        <p className="muted">
          Cart is empty. <Link href="/">Browse products</Link>.
        </p>
      )}
      {items !== null && items.length > 0 && (
        <>
          <table className="cart-table">
            <thead>
              <tr>
                <th>Product</th>
                <th>Qty</th>
                <th>Price</th>
                <th>Subtotal</th>
              </tr>
            </thead>
            <tbody>
              {items.map((i) => (
                <tr key={i.product_id}>
                  <td>
                    <Link href={`/product/${i.product_id}`}>{i.name}</Link>
                  </td>
                  <td>{i.qty}</td>
                  <td>${i.price.toFixed(2)}</td>
                  <td>${(i.price * i.qty).toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <td colSpan="3">Total</td>
                <td>${total.toFixed(2)}</td>
              </tr>
            </tfoot>
          </table>
          <div className="cart-actions">
            <button className="secondary" onClick={clearCart}>
              Clear cart
            </button>
            <Link href="/checkout" className="button">
              Proceed to checkout →
            </Link>
          </div>
        </>
      )}
    </main>
  );
}
