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

export default function MotadataPanel({ onAction }) {
  const [board, setBoard] = useState(null);
  const [token, setToken] = useState("");
  const [url, setUrl] = useState("");
  const [targetHost, setTargetHost] = useState("");
  const [editing, setEditing] = useState(false);
  const [loading, setLoading] = useState(false);
  const { busy, error, result, run } = useRun(onAction);

  const refresh = useCallback(() => {
    setLoading(true);
    api("/motadata/status")
      .then(setBoard)
      .catch(() => setBoard(null))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 15_000);
    return () => clearInterval(id);
  }, [refresh]);

  const saveSettings = () =>
    run(() =>
      api("/motadata/settings", {
        method: "POST",
        body: {
          ...(token ? { token } : {}),
          ...(url ? { url } : {}),
          ...(targetHost ? { target_host: targetHost } : {}),
        },
      }),
    ).then(() => {
      setToken("");
      setUrl("");
      setTargetHost("");
      setEditing(false);
      refresh();
    });

  const resetSettings = () =>
    run(() => api("/motadata/settings", { method: "POST", body: { reset: true } })).then(() => {
      setEditing(false);
      refresh();
    });

  const configureAll = () =>
    run(() => api("/motadata/configure", { method: "POST", body: {} })).then(refresh);

  const configureOne = (key) =>
    run(() => api("/motadata/configure", { method: "POST", body: { only: key } })).then(refresh);

  const runDiscovery = (label) =>
    run(() => api(`/motadata/discovery/${encodeURIComponent(label)}/run`, { method: "POST" }))
      .then(refresh);

  const summary = board?.summary || {};
  const grouped = (board?.items || []).reduce((acc, item) => {
    (acc[item.group] = acc[item.group] || []).push(item);
    return acc;
  }, {});
  const groups = GROUP_ORDER.filter((g) => grouped[g]);

  return (
    <Panel
      title="Motadata Configuration"
      desc="Everything the ecosystem needs on the appliance. Configure it all in one click, or fix one row at a time."
    >
      <div className="mota-appliance">
        <span>
          <strong>{board?.appliance?.url || "appliance"}</strong>
          {board?.appliance?.target_host ? ` → monitors ${board.appliance.target_host}` : ""}
          {board?.appliance?.overridden?.length ? (
            <em className="mota-overridden"> (custom)</em>
          ) : null}
        </span>
        <span>
          <span className={`api-dot ${board?.appliance?.has_token ? "up" : "down"}`}>
            {board?.appliance?.has_token ? "token set" : "no token"}
          </span>
          <button className="ghost" onClick={() => setEditing((v) => !v)}>
            {editing ? "Close" : "Settings"}
          </button>
        </span>
      </div>

      {(editing || !board?.appliance?.has_token) && (
        <div className="mota-settings">
          <label>
            Appliance URL
            <input
              placeholder={board?.appliance?.url || "https://172.16.14.71"}
              value={url}
              onChange={(e) => setUrl(e.target.value)}
            />
          </label>
          <label>
            Monitored host
            <input
              placeholder={board?.appliance?.target_host || "172.20.21.25"}
              value={targetHost}
              onChange={(e) => setTargetHost(e.target.value)}
            />
          </label>
          <label>
            Personal Access Token
            <input
              type="password"
              placeholder={board?.appliance?.has_token ? "•••••• (set)" : "Settings → User Settings"}
              value={token}
              onChange={(e) => setToken(e.target.value)}
            />
          </label>
          <div className="mota-settings-actions">
            <button onClick={saveSettings} disabled={busy || (!token && !url && !targetHost)}>
              Save
            </button>
            <button className="ghost" onClick={resetSettings} disabled={busy}>
              Reset to defaults
            </button>
          </div>
          <p className="mota-hint">Blank fields keep their current value. Saved settings persist across restarts.</p>
        </div>
      )}

      <div className="mota-summary">
        {["active", "configured", "not_configured", "error", "unknown"].map((s) =>
          summary[s] ? (
            <span key={s} className={`chip ${s}`}>
              {summary[s]} {STATE_LABEL[s]}
            </span>
          ) : null,
        )}
        <button onClick={configureAll} disabled={busy || !board?.appliance?.has_token}>
          {busy ? "Configuring…" : "Configure everything"}
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
                      <button className="ghost" onClick={() => runDiscovery(item.label)} disabled={busy}>
                        Run
                      </button>
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
