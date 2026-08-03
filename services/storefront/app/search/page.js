"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import ErrorBanner from "../../components/ErrorBanner";
import ProductCard from "../../components/ProductCard";
import { apiFetch, productList } from "../../lib/api";

function SearchResults() {
  const params = useSearchParams();
  const q = params.get("q") || "";
  const [results, setResults] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    setResults(null);
    setError(null);
    apiFetch(`search?q=${encodeURIComponent(q)}`)
      .then((data) => setResults(productList(data)))
      .catch(setError);
  }, [q]);

  return (
    <>
      <h1>Search{q && <>: “{q}”</>}</h1>
      <ErrorBanner error={error} />
      {results === null && !error && <p className="muted">Searching…</p>}
      {results !== null && results.length === 0 && <p className="muted">No products found.</p>}
      {results !== null && results.length > 0 && (
        <div className="grid">
          {results.map((p) => (
            <ProductCard key={p.id} product={p} />
          ))}
        </div>
      )}
    </>
  );
}

export default function SearchPage() {
  return (
    <main className="container">
      <Suspense fallback={<p className="muted">Searching…</p>}>
        <SearchResults />
      </Suspense>
    </main>
  );
}
