import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import Panel, { ResultLine, useRun } from "./Panel";

const DEFAULT_COUNT = 100;
const DEFAULT_TIMEFRAME = "5m";
const DEFAULT_RATE = 60;

export default function IngestPanel({ onAction }) {
  const [board, setBoard] = useState(null);
  const [form, setForm] = useState({});
  const { busy, error, result, run } = useRun(onAction);

  const refresh = useCallback(() => {
    api("/ingest").then(setBoard).catch(() => setBoard(null));
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 5_000);
    return () => clearInterval(id);
  }, [refresh]);

  const field = (key, name, fallback) => form[key]?.[name] ?? fallback;
  const setField = (key, name, value) =>
    setForm((f) => ({ ...f, [key]: { ...f[key], [name]: value } }));

  const burst = (key) =>
    run(() =>
      api("/ingest/burst", {
        method: "POST",
        body: {
          type: key,
          count: Number(field(key, "count", DEFAULT_COUNT)),
          timeframe: field(key, "timeframe", DEFAULT_TIMEFRAME),
        },
      }),
    ).then(refresh);

  const toggleContinuous = (key, enabled) =>
    run(() =>
      api("/ingest/continuous", {
        method: "POST",
        body: { type: key, enabled, per_minute: Number(field(key, "rate", DEFAULT_RATE)) },
      }),
    ).then(refresh);

  const timeframes = board?.timeframes || ["instant", "1m", "5m", "15m", "1h"];

  return (
    <Panel
      title="Ingestion"
      desc="Push telemetry into this appliance. Burst sends a fixed amount spread over a window; continuous keeps a steady rate running."
    >
      {(board?.types || []).map((t) => {
        const cont = t.continuous;
        const on = cont?.enabled;
        return (
          <div key={t.key} className="ing-row">
            <div className="ing-head">
              <div>
                <strong>{t.label}</strong>
                <span className="ing-pipeline">{t.pipeline}</span>
                <p className="ing-desc">{t.desc}</p>
              </div>
              {on && (
                <span className="chip active">
                  live · {cont.per_minute}/min · {cont.produced} sent
                </span>
              )}
            </div>

            <div className="ing-controls">
              <label>
                Amount
                <input
                  type="number"
                  min="1"
                  value={field(t.key, "count", DEFAULT_COUNT)}
                  onChange={(e) => setField(t.key, "count", e.target.value)}
                />
              </label>
              <label>
                Over
                <select
                  value={field(t.key, "timeframe", DEFAULT_TIMEFRAME)}
                  onChange={(e) => setField(t.key, "timeframe", e.target.value)}
                >
                  {timeframes.map((tf) => (
                    <option key={tf} value={tf}>
                      {tf}
                    </option>
                  ))}
                </select>
              </label>
              <button onClick={() => burst(t.key)} disabled={busy}>
                Ingest
              </button>

              <span className="ing-divider" />

              <label>
                Rate /min
                <input
                  type="number"
                  min="1"
                  value={field(t.key, "rate", cont?.per_minute ?? DEFAULT_RATE)}
                  onChange={(e) => setField(t.key, "rate", e.target.value)}
                />
              </label>
              <button
                className={on ? "ghost" : ""}
                onClick={() => toggleContinuous(t.key, !on)}
                disabled={busy}
              >
                {on ? "Stop continuous" : "Start continuous"}
              </button>
            </div>

            {cont?.error && <p className="result error">✗ {cont.error}</p>}
          </div>
        );
      })}

      {!!board?.jobs?.length && (
        <div className="mota-group">
          <h3>Recent bursts</h3>
          <table className="mota-table">
            <tbody>
              {board.jobs.slice(0, 8).map((j) => (
                <tr key={j.id}>
                  <td className="mota-name">
                    <strong>{j.type}</strong>
                    <span>
                      {j.count} over {j.timeframe}
                    </span>
                  </td>
                  <td>
                    <span
                      className={`chip ${
                        j.state === "done"
                          ? "active"
                          : j.state === "running"
                            ? "configured"
                            : j.state === "error"
                              ? "error"
                              : "not_configured"
                      }`}
                    >
                      {j.state}
                    </span>
                    <span className="mota-detail">
                      {j.produced}/{j.count} sent
                      {j.error ? ` — ${j.error}` : ""}
                    </span>
                  </td>
                  <td className="mota-actions">
                    {j.state === "running" && (
                      <button
                        className="ghost"
                        onClick={() => run(() => api(`/ingest/burst/${j.id}/stop`, { method: "POST" })).then(refresh)}
                      >
                        Stop
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <ResultLine error={error} result={result} />
    </Panel>
  );
}
