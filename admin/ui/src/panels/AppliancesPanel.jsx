import { useEffect, useState } from "react";
import { api } from "../api";
import Panel, { ResultLine, useRun } from "./Panel";

const EMPTY = { name: "", url: "", target_host: "", token: "" };

export default function AppliancesPanel({ onOpen, onAction }) {
  const [items, setItems] = useState([]);
  const [form, setForm] = useState(EMPTY);
  const [adding, setAdding] = useState(false);
  const { busy, error, result, run } = useRun(onAction);

  const refresh = () => api("/appliances").then(setItems).catch(() => setItems([]));

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 20_000);
    return () => clearInterval(id);
  }, []);

  const add = () =>
    run(() => api("/appliances", { method: "POST", body: form })).then((r) => {
      if (r) {
        setForm(EMPTY);
        setAdding(false);
        refresh();
      }
    });

  const remove = (id) =>
    run(() => api(`/appliances/${id}`, { method: "DELETE" })).then(refresh);

  return (
    <Panel
      title="Appliances"
      desc="Every Motadata instance this Studio can configure and feed. Open one to work on it."
    >
      <div className="appl-list">
        {items.map((a) => (
          <div key={a.id} className="appl-card">
            <div className="appl-main" onClick={() => onOpen(a)} role="button" tabIndex={0}>
              <strong>{a.name || a.url}</strong>
              <span className="appl-url">{a.url}</span>
              <span className="appl-meta">
                monitors {a.target_host || "—"}
                <span className={`chip ${a.has_token ? "active" : "not_configured"}`}>
                  {a.has_token ? "token set" : "no token"}
                </span>
              </span>
            </div>
            <div className="appl-actions">
              <button onClick={() => onOpen(a)}>Open</button>
              <button className="ghost" onClick={() => remove(a.id)} disabled={busy}>
                Remove
              </button>
            </div>
          </div>
        ))}
        {!items.length && <p className="panel-desc">No appliances yet — add one below.</p>}
      </div>

      {adding ? (
        <div className="mota-settings">
          <label>
            Name
            <input
              placeholder="Lab appliance"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </label>
          <label>
            Appliance URL
            <input
              placeholder="https://172.16.14.71  or  http://172.16.12.186"
              value={form.url}
              onChange={(e) => setForm({ ...form, url: e.target.value })}
            />
          </label>
          <label>
            Monitored host
            <input
              placeholder="172.20.21.25"
              value={form.target_host}
              onChange={(e) => setForm({ ...form, target_host: e.target.value })}
            />
          </label>
          <label>
            Personal Access Token
            <input
              type="password"
              placeholder="Settings → User Settings → Personal Access Token"
              value={form.token}
              onChange={(e) => setForm({ ...form, token: e.target.value })}
            />
          </label>
          <div className="mota-settings-actions">
            <button onClick={add} disabled={busy || !form.url}>
              Add appliance
            </button>
            <button className="ghost" onClick={() => setAdding(false)} disabled={busy}>
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <button onClick={() => setAdding(true)}>Add appliance</button>
      )}

      <ResultLine error={error} result={result} />
    </Panel>
  );
}
