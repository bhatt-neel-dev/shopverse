import { useState } from "react";
import { api } from "../api";
import Panel, { ResultLine, useRun } from "./Panel";

export default function StormPanel({ onAction }) {
  const [severity, setSeverity] = useState("ERROR");
  const [pattern, setPattern] = useState("synthetic disk latency warning");
  const [count, setCount] = useState(500);
  const [intervalMs, setIntervalMs] = useState(10);
  const { busy, error, result, run } = useRun(onAction);

  return (
    <Panel
      title="Log storm"
      desc="Burst of contract-format log lines with your pattern, tagged with a storm id."
    >
      <label>
        Severity
        <select value={severity} onChange={(e) => setSeverity(e.target.value)}>
          {["DEBUG", "INFO", "WARN", "ERROR"].map((s) => (
            <option key={s}>{s}</option>
          ))}
        </select>
      </label>
      <label>
        Pattern
        <input value={pattern} onChange={(e) => setPattern(e.target.value)} />
      </label>
      <label>
        Lines
        <input
          type="number"
          min="1"
          max="100000"
          value={count}
          onChange={(e) => setCount(Number(e.target.value))}
        />
      </label>
      <label>
        Interval between lines: {intervalMs} ms
        <input
          type="range"
          min="0"
          max="1000"
          step="10"
          value={intervalMs}
          onChange={(e) => setIntervalMs(Number(e.target.value))}
        />
      </label>
      <div className="btn-row">
        <button
          disabled={busy}
          onClick={() =>
            run(() =>
              api("/logs/storm", {
                method: "POST",
                body: { severity, pattern, count, interval_ms: intervalMs },
              })
            )
          }
        >
          Unleash storm
        </button>
      </div>
      <ResultLine error={error} result={result} />
    </Panel>
  );
}
