"use client";

import { useEffect, useState } from "react";
import ErrorBanner from "../components/ErrorBanner";
import ProductCard from "../components/ProductCard";
import { apiFetch, productList } from "../lib/api";

const PAGE_SIZE = 24;

export default function HomePage() {
  const [products, setProducts] = useState([]);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    apiFetch(`catalog/products?limit=${PAGE_SIZE}&offset=${offset}`)
      .then((data) => {
        if (!cancelled) setProducts(productList(data));
      })
      .catch((err) => {
        if (!cancelled) setError(err);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [offset]);

  return (
    <main className="container">
      <h1>Products</h1>
      <ErrorBanner error={error} />
      {loading ? (
        <p className="muted">Loading products…</p>
      ) : (
        <>
          <div className="grid">
            {products.map((p) => (
              <ProductCard key={p.id} product={p} />
            ))}
          </div>
          <div className="pager">
            <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
              ← Previous
            </button>
            <span className="muted">
              {offset + 1}–{offset + products.length}
            </span>
            <button
              disabled={products.length < PAGE_SIZE}
              onClick={() => setOffset(offset + PAGE_SIZE)}
            >
              Next →
            </button>
          </div>
        </>
      )}
    </main>
  );
}
