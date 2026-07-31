// Browser-side gateway access. Every call goes through the Next.js proxy route
// (/api/proxy/<path> → ${GATEWAY_URL}/api/<path>) so the browser never needs
// direct service access, and every call carries the session X-Trace-Id.

import { getTraceId } from "./trace";

export const DEMO_USER_ID = 1;

export async function apiFetch(path, options = {}) {
  const res = await fetch(`/api/proxy/${path}`, {
    ...options,
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      "X-Trace-Id": getTraceId(),
      ...(options.headers || {}),
    },
  });

  let data = null;
  try {
    data = await res.json();
  } catch {
    // non-JSON body (e.g. raw nginx error page) — fall through with null data
  }

  if (!res.ok) {
    const err = new Error(
      (data && data.error) || `Request failed with status ${res.status}`
    );
    err.status = res.status;
    err.data = data;
    err.traceId = (data && data.trace_id) || getTraceId();
    throw err;
  }
  return data;
}

// Services aren't all built yet, so be liberal in what we accept for list shapes.
export function cartItems(data) {
  if (!data) return [];
  if (Array.isArray(data)) return data;
  if (Array.isArray(data.items)) return data.items;
  if (data.cart && Array.isArray(data.cart.items)) return data.cart.items;
  return [];
}

export function productList(data) {
  if (!data) return [];
  if (Array.isArray(data)) return data;
  if (Array.isArray(data.products)) return data.products;
  if (Array.isArray(data.items)) return data.items;
  if (Array.isArray(data.results)) return data.results;
  return [];
}

// Cart entries only store {product_id, qty}; enrich each line with catalog
// name/price so the cart and checkout pages can render and price the order.
export async function loadDetailedCart() {
  const data = await apiFetch(`cart/${DEMO_USER_ID}`);
  const items = cartItems(data).filter((i) => Number(i.qty) > 0);
  return Promise.all(
    items.map(async (item) => {
      const pid = item.product_id ?? item.id;
      try {
        const pd = await apiFetch(`catalog/products/${pid}`);
        const p = (pd && (pd.product || pd)) || {};
        return {
          product_id: pid,
          qty: Number(item.qty) || 0,
          name: p.name || `Product #${pid}`,
          price: Number(p.price ?? item.price ?? 0),
          category: p.category || "",
        };
      } catch {
        return {
          product_id: pid,
          qty: Number(item.qty) || 0,
          name: `Product #${pid}`,
          price: Number(item.price ?? 0),
          category: "",
        };
      }
    })
  );
}
