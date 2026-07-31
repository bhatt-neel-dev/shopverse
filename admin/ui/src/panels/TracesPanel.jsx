import { useState } from "react";
import { api } from "../api";
import Panel, { ResultLine, useRun } from "./Panel";

export default function TracesPanel({ onAction }) {
  const [journey, setJourney] = useState("checkout");
  const [count, setCount] = useState(100);
  const [concurrency, setConcurrency] = useState(10);
  const [errorRate, setErrorRate] = useState(0);
  const [tag, setTag] = useState("studio-bulk");
  const { busy, error, result, run } = useRun(onAction);

  return (
    <Panel
      title="Bulk traces"
      desc="Fire N real journeys through the actual stack — every one is a genuine end-to-end trace."
    >
      <label>
        Journey
        <select value={journey} onChange={(e) => setJourney(e.target.value)}>
          <option value="browse">browse (catalog)</option>
          <option value="search">search</option>
          <option value="checkout">checkout (cart → order → payment)</option>
        </select>
      </label>
      <label>
        Count
        <input
          type="number"
          min="1"
          max="5000"
          value={count}
          onChange={(e) => setCount(Number(e.target.value))}
        />
      </label>
      <label>
        Concurrency
        <input
          type="number"
          min="1"
          max="100"
          value={concurrency}
          onChange={(e) => setConcurrency(Number(e.target.value))}
        />
      </label>
      <label>
        Temporary error rate: {errorRate}%
        <input
          type="range"
          min="0"
          max="100"
          value={errorRate}
          onChange={(e) => setErrorRate(Number(e.target.value))}
        />
      </label>
      <label>
        Tag
        <input value={tag} onChange={(e) => setTag(e.target.value)} />
      </label>
      <div className="btn-row">
        <button
          disabled={busy}
          onClick={() =>
            run(() =>
              api("/traces/bulk", {
                method: "POST",
                body: {
                  journey,
                  count,
                  concurrency,
                  error_rate: errorRate,
                  latency_ms: 0,
                  tag,
                },
              })
            )
          }
        >
          {busy ? "Running…" : "Fire traces"}
        </button>
      </div>
      <ResultLine error={error} result={result} />
    </Panel>
  );
}
