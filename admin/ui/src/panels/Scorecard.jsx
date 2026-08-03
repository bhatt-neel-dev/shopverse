import { useEffect, useState } from "react";
import { api } from "../api";

export default function Scorecard() {
  const [card, setCard] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    const load = () =>
      api("/coverage")
        .then((data) => {
          if (!cancelled) {
            setCard(data);
            setError(null);
          }
        })
        .catch((err) => !cancelled && setError(err.message));
    load();
    const id = setInterval(load, 5000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  return (
    <section className="panel scorecard">
      <h2>
        Pipeline scorecard{" "}
        {card && (
          <span className={card.healthy ? "badge ok" : "badge bad"}>
            {card.up}/{card.total} up
          </span>
        )}
      </h2>
      {error && <p className="result error">✗ {error}</p>}
      {card && (
        <>
          <div className="score-row">
            {Object.entries(card.checks).map(([name, check]) => (
              <div key={name} className={`score-cell ${check.ok ? "up" : "down"}`} title={check.error || ""}>
                <span className="dot" />
                {name}
                {name === "locust" && check.user_count != null && (
                  <em> {check.user_count}u</em>
                )}
                {name === "rabbitmq" && check.queue_depth != null && (
                  <em> q{check.queue_depth}</em>
                )}
              </div>
            ))}
          </div>
          {Object.keys(card.active_injection_flags || {}).length > 0 && (
            <p className="flags-line">
              ⚠ active injection:{" "}
              {Object.entries(card.active_injection_flags)
                .map(
                  ([svc, f]) =>
                    `${svc} (${Object.entries(f)
                      .filter(([, v]) => v > 0)
                      .map(([k, v]) => `${k}=${v}`)
                      .join(", ")})`
                )
                .join(" · ")}
            </p>
          )}
        </>
      )}
    </section>
  );
}
