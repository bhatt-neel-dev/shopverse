import { useEffect, useState } from "react";
import { api } from "../api";

export default function HistoryPanel({ tick }) {
  const [entries, setEntries] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    const load = () =>
      api("/history?n=100")
        .then((data) => {
          if (!cancelled) {
            setEntries(data);
            setError(null);
          }
        })
        .catch((err) => !cancelled && setError(err.message));
    load();
    const id = setInterval(load, 10_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [tick]);

  return (
    <section className="panel history">
      <h2>Scenario history</h2>
      <p className="panel-desc">
        What did I break and when — validate Motadata alerts against these timestamps.
      </p>
      {error && <p className="result error">✗ {error}</p>}
      {entries.length === 0 && !error && <p className="panel-desc">No scenarios run yet.</p>}
      {entries.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>When (UTC)</th>
              <th>Action</th>
              <th>Params</th>
              <th>Result</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((e, i) => (
              <tr key={`${e.ts}-${i}`}>
                <td className="mono">{e.ts}</td>
                <td>
                  <strong>{e.action}</strong>
                </td>
                <td className="mono small">{JSON.stringify(e.params)}</td>
                <td className="mono small">{JSON.stringify(e.result)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
