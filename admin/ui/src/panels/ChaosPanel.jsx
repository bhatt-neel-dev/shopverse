import { useEffect, useState } from "react";
import { api } from "../api";
import Panel, { ResultLine, useRun } from "./Panel";

const LABELS = {
  "payment-outage": "Payment outage",
  "db-outage": "MySQL outage",
  "cache-outage": "Redis outage",
  "queue-outage": "RabbitMQ outage",
  "search-outage": "MongoDB outage",
};

export default function ChaosPanel({ onAction }) {
  const [durationS, setDurationS] = useState(120);
  const [states, setStates] = useState({});
  const { busy, error, result, run } = useRun(onAction);

  useEffect(() => {
    let cancelled = false;
    const load = () =>
      api("/chaos")
        .then((s) => !cancelled && setStates(s))
        .catch(() => {});
    load();
    const id = setInterval(load, 5000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [result]);

  return (
    <Panel
      title="Chaos scenarios"
      desc="Stop real containers for a window, auto-recover after. Exact timestamps land in history — that's your alert ground truth."
    >
      <label>
        Duration: {durationS}s
        <input
          type="range"
          min="30"
          max="600"
          step="30"
          value={durationS}
          onChange={(e) => setDurationS(Number(e.target.value))}
        />
      </label>
      <div className="chaos-list">
        {Object.entries(LABELS).map(([scenario, label]) => {
          const st = states[scenario];
          const running = st?.state === "running";
          return (
            <div key={scenario} className="chaos-row">
              <span className={running ? "chaos-name running" : "chaos-name"}>
                {label}
                {running && <em> · {st.remaining_s}s left</em>}
              </span>
              {running ? (
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() => run(() => api(`/chaos/${scenario}/stop`, { method: "POST" }))}
                >
                  Recover now
                </button>
              ) : (
                <button
                  className="danger"
                  disabled={busy}
                  onClick={() =>
                    run(() =>
                      api(`/chaos/${scenario}`, { method: "POST", body: { duration_s: durationS } })
                    )
                  }
                >
                  Break it
                </button>
              )}
            </div>
          );
        })}
      </div>
      <ResultLine error={error} result={result} />
    </Panel>
  );
}
