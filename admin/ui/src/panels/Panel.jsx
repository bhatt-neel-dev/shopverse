import { useState } from "react";

/** Shared card chrome: title, description, error line, and a `run` helper that
 * panels use to call the API and surface success/failure inline. */
export default function Panel({ title, desc, children }) {
  return (
    <section className="panel">
      <h2>{title}</h2>
      {desc && <p className="panel-desc">{desc}</p>}
      {children}
    </section>
  );
}

export function useRun(onAction) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  async function run(fn) {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const data = await fn();
      setResult(data);
      onAction && onAction();
      return data;
    } catch (err) {
      setError(err.message);
      return null;
    } finally {
      setBusy(false);
    }
  }

  return { busy, error, result, run };
}

export function ResultLine({ error, result }) {
  if (error) return <p className="result error">✗ {error}</p>;
  if (result) return <pre className="result ok">{JSON.stringify(result, null, 1)}</pre>;
  return null;
}
