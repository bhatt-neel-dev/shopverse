import { useEffect, useState } from "react";
import { api } from "../api";
import Panel, { ResultLine, useRun } from "./Panel";

const SERVICES = ["catalog", "order", "cart", "search", "payment", "storefront"];

export default function InjectionPanel({ onAction }) {
  const [svc, setSvc] = useState("payment");
  const [errorRate, setErrorRate] = useState(10);
  const [latencyMs, setLatencyMs] = useState(0);
  const [flags, setFlags] = useState(null);
  const { busy, error, result, run } = useRun(onAction);

  const loadFlags = () => api("/inject").then(setFlags).catch(() => {});
  useEffect(() => {
    loadFlags();
  }, [result]);

  return (
    <Panel
      title="Fault injection"
      desc="Per-service error % and added latency, applied live via Redis flags — no redeploys."
    >
      <label>
        Service
        <select value={svc} onChange={(e) => setSvc(e.target.value)}>
          {SERVICES.map((s) => (
            <option key={s}>{s}</option>
          ))}
        </select>
      </label>
      <label>
        Error rate: {errorRate}%
        <input
          type="range"
          min="0"
          max="100"
          value={errorRate}
          onChange={(e) => setErrorRate(Number(e.target.value))}
        />
      </label>
      <label>
        Latency: {latencyMs} ms
        <input
          type="range"
          min="0"
          max="5000"
          step="50"
          value={latencyMs}
          onChange={(e) => setLatencyMs(Number(e.target.value))}
        />
      </label>
      <div className="btn-row">
        <button
          disabled={busy}
          onClick={() =>
            run(() =>
              api("/inject", {
                method: "POST",
                body: { svc, error_rate: errorRate, latency_ms: latencyMs },
              })
            )
          }
        >
          Apply
        </button>
        <button
          className="secondary"
          disabled={busy}
          onClick={() => run(() => api(`/inject/clear?svc=${svc}`, { method: "POST" }))}
        >
          Clear {svc}
        </button>
        <button
          className="secondary"
          disabled={busy}
          onClick={() => run(() => api("/inject/clear", { method: "POST" }))}
        >
          Clear all
        </button>
      </div>
      <ResultLine error={error} result={result} />
      {flags && (
        <div className="flags-table">
          {Object.entries(flags)
            .filter(([, f]) => f.error_rate > 0 || f.latency_ms > 0)
            .map(([s, f]) => (
              <div key={s}>
                <strong>{s}</strong>: {f.error_rate}% err, +{f.latency_ms}ms
              </div>
            ))}
        </div>
      )}
    </Panel>
  );
}
