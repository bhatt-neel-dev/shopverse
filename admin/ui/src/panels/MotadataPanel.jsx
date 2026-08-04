import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import Panel, { ResultLine, useRun } from "./Panel";

const STATE_LABEL = {
  active: "Active",
  configured: "Configured",
  not_configured: "Not Configured",
  error: "Error",
  unknown: "Unknown",
};

const GROUP_ORDER = ["Credentials", "Discovery", "Log", "Policies"];

export default function MotadataPanel({ appliance, onAction }) {
  const [board, setBoard] = useState(null);
  const [loading, setLoading] = useState(false);
  const { busy, error, result, run } = useRun(onAction);

  const refresh = useCallback(() => {
    setLoading(true);
    api(`/appliances/${appliance.id}/status`)
      .then(setBoard)
      .catch(() => setBoard(null))
      .finally(() => setLoading(false));
  }, [appliance.id]);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 15_000);
    return () => clearInterval(id);
  }, [refresh]);

  const configureAll = () =>
    run(() => api(`/appliances/${appliance.id}/configure`, { method: "POST", body: {} })).then(refresh);

  const configureOne = (key) =>
    run(() => api(`/appliances/${appliance.id}/configure`, { method: "POST", body: { only: key } })).then(refresh);

  const provisionAll = () =>
    run(() => api(`/appliances/${appliance.id}/provision`, { method: "POST" })).then(refresh);

  const provision = (label) =>
    run(() => api(`/appliances/${appliance.id}/discovery/${encodeURIComponent(label)}/provision`, { method: "POST" }))
      .then(refresh);

  const runDiscovery = (label) =>
    run(() => api(`/appliances/${appliance.id}/discovery/${encodeURIComponent(label)}/run`, { method: "POST" }))
      .then(refresh);

  const summary = board?.summary || {};
  const grouped = (board?.items || []).reduce((acc, item) => {
    (acc[item.group] = acc[item.group] || []).push(item);
    return acc;
  }, {});
  const groups = GROUP_ORDER.filter((g) => grouped[g]);

  return (
    <Panel
      title="Configuration"
      desc="Everything the ecosystem needs on the appliance. Configure it all in one click, or fix one row at a time."
    >
      <div className="mota-appliance">
        <span>
          <strong>{board?.appliance?.url || appliance.url}</strong>
          {` → monitors ${board?.appliance?.target_host || appliance.target_host || "—"}`}
        </span>
        <span className={`api-dot ${board?.appliance?.has_token ? "up" : "down"}`}>
          {board?.appliance?.has_token ? "token set" : "no token"}
        </span>
      </div>

      <div className="mota-summary">
        {["active", "configured", "not_configured", "error", "unknown"].map((s) =>
          summary[s] ? (
            <span key={s} className={`chip ${s}`}>
              {summary[s]} {STATE_LABEL[s]}
            </span>
          ) : null,
        )}
        <button onClick={configureAll} disabled={busy || !board?.appliance?.has_token}>
          {busy ? "Working…" : "Configure everything"}
        </button>
        <button onClick={provisionAll} disabled={busy || !board?.appliance?.has_token}>
          Provision all
        </button>
        <button className="ghost" onClick={refresh} disabled={loading}>
          {loading ? "…" : "Refresh"}
        </button>
      </div>

      {board?.message && <p className="result error">✗ {board.message}</p>}

      {groups.map((group) => (
        <div key={group} className="mota-group">
          <h3>{group}</h3>
          <table className="mota-table">
            <tbody>
              {grouped[group].map((item) => (
                <tr key={item.key}>
                  <td className="mota-name">
                    <strong>{item.label}</strong>
                    <span>{item.desc}</span>
                  </td>
                  <td>
                    <span className={`chip ${item.state}`}>{STATE_LABEL[item.state]}</span>
                    <span className="mota-detail">{item.detail}</span>
                  </td>
                  <td className="mota-actions">
                    {item.state === "not_configured" && (
                      <button onClick={() => configureOne(item.key)} disabled={busy}>
                        Configure
                      </button>
                    )}
                    {group === "Discovery" && item.state !== "not_configured" && (
                      <>
                        <button className="ghost" onClick={() => runDiscovery(item.label)} disabled={busy}>
                          Run
                        </button>
                        <button className="ghost" onClick={() => provision(item.label)} disabled={busy}>
                          Provision
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}

      <ResultLine error={error} result={result} />
    </Panel>
  );
}
