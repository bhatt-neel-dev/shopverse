"use client";

import Link from "next/link";
import { useState } from "react";
import { apiFetch, DEMO_USER_ID } from "../lib/api";
import { productImage } from "../lib/product-image";

export default function ProductCard({ product }) {
  const [state, setState] = useState("idle"); // idle | adding | added | error

  async function addToCart() {
    setState("adding");
    try {
      await apiFetch(`cart/${DEMO_USER_ID}/items`, {
        method: "POST",
        body: JSON.stringify({ product_id: product.id, qty: 1 }),
      });
      setState("added");
      setTimeout(() => setState("idle"), 1500);
    } catch {
      setState("error");
      setTimeout(() => setState("idle"), 2500);
    }
  }

  return (
    <div className="card">
      <Link href={`/product/${product.id}`}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={productImage(product.id, product.name)} alt={product.name} />
      </Link>
      <div className="card-body">
        <Link href={`/product/${product.id}`} className="card-title">
          {product.name}
        </Link>
        <div className="card-meta">
          <span className="price">${Number(product.price).toFixed(2)}</span>
          {product.category && <span className="category">{product.category}</span>}
        </div>
        <button onClick={addToCart} disabled={state === "adding"}>
          {state === "adding"
            ? "Adding…"
            : state === "added"
              ? "Added ✓"
              : state === "error"
                ? "Failed — retry"
                : "Add to cart"}
        </button>
      </div>
    </div>
  );
}
