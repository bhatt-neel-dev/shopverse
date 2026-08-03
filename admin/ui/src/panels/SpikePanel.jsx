import { useEffect, useState } from "react";
import { api } from "../api";
import Panel, { ResultLine, useRun } from "./Panel";

export default function SpikePanel({ onAction }) {
  const [magnitude, setMagnitude] = useState(3);
  const [durationS, setDurationS] = useState(120);
  const [status, setStatus] = useState(null);
  const { busy, error, result, run } = useRun(onAction);

  useEffect(() => {
    let cancelled = false;
    const load = () =>
      api("/load/spike")
        .then((s) => !cancelled && setStatus(s))
        .catch(() => {});
    load();
    const id = setInterval(load, 5000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [result]);

  const spiking = status?.state === "spiking";

  return (
    <Panel
      title="Load spike"
      desc="Ramp Locust to baseline × magnitude for a fixed window, then restore."
    >
      <label>
        Magnitude: {magnitude}×
        <input
          type="range"
          min="1.5"
          max="10"
          step="0.5"
          value={magnitude}
          onChange={(e) => setMagnitude(Number(e.target.value))}
        />
      </label>
      <label>
        Duration: {durationS}s
        <input
          type="range"
          min="30"
          max="900"
          step="30"
          value={durationS}
          onChange={(e) => setDurationS(Number(e.target.value))}
        />
      </label>
      <div className="btn-row">
        <button
          disabled={busy || spiking}
          onClick={() =>
            run(() =>
              api("/load/spike", { method: "POST", body: { magnitude, duration_s: durationS } })
            )
          }
        >
          Start spike
        </button>
        <button
          className="secondary"
          disabled={busy || !spiking}
          onClick={() => run(() => api("/load/spike/stop", { method: "POST" }))}
        >
          Stop early
        </button>
      </div>
      {spiking && (
        <p className="live-line">
          ⚡ {status.baseline_users} → {status.target_users} users · {status.remaining_s}s left
        </p>
      )}
      <ResultLine error={error} result={result} />
    </Panel>
  );
}
