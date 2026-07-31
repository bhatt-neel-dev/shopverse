"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import ErrorBanner from "../../../components/ErrorBanner";
import { apiFetch, DEMO_USER_ID } from "../../../lib/api";
import { productImage } from "../../../lib/product-image";

export default function ProductPage() {
  const { id } = useParams();
  const [product, setProduct] = useState(null);
  const [qty, setQty] = useState(1);
  const [error, setError] = useState(null);
  const [added, setAdded] = useState(false);

  useEffect(() => {
    apiFetch(`catalog/products/${id}`)
      .then((data) => setProduct(data.product || data))
      .catch(setError);
  }, [id]);

  async function addToCart() {
    setError(null);
    setAdded(false);
    try {
      await apiFetch(`cart/${DEMO_USER_ID}/items`, {
        method: "POST",
        body: JSON.stringify({ product_id: Number(id), qty: Number(qty) }),
      });
      setAdded(true);
    } catch (err) {
      setError(err);
    }
  }

  return (
    <main className="container">
      <ErrorBanner error={error} />
      {!product && !error && <p className="muted">Loading…</p>}
      {product && (
        <div className="product-detail">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={productImage(product.id, product.name)} alt={product.name} />
          <div>
            <h1>{product.name}</h1>
            <p className="price big">${Number(product.price).toFixed(2)}</p>
            {product.category && <p className="category">{product.category}</p>}
            <p>{product.description}</p>
            <p className="muted">{product.stock > 0 ? `${product.stock} in stock` : "Out of stock"}</p>
            <div className="buy-row">
              <input
                type="number"
                min="1"
                max="10"
                value={qty}
                onChange={(e) => setQty(e.target.value)}
                aria-label="Quantity"
              />
              <button onClick={addToCart}>Add to cart</button>
              {added && <span className="added">Added to cart ✓</span>}
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
