import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import ChaosPanel from "./panels/ChaosPanel";
import HistoryPanel from "./panels/HistoryPanel";
import InjectionPanel from "./panels/InjectionPanel";
import Scorecard from "./panels/Scorecard";
import SpikePanel from "./panels/SpikePanel";
import StormPanel from "./panels/StormPanel";
import TracesPanel from "./panels/TracesPanel";

export default function App() {
  const [historyTick, setHistoryTick] = useState(0);
  const [apiDown, setApiDown] = useState(false);

  // Any panel action bumps the tick so HistoryPanel refetches immediately.
  const onAction = useCallback(() => setHistoryTick((t) => t + 1), []);

  useEffect(() => {
    let cancelled = false;
    const probe = () =>
      api("/health")
        .then(() => !cancelled && setApiDown(false))
        .catch(() => !cancelled && setApiDown(true));
    probe();
    const id = setInterval(probe, 10_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  return (
    <div className="studio">
      <header className="topbar">
        <h1>
          ShopVerse <span>Scenario Studio</span>
        </h1>
        <span className={`api-dot ${apiDown ? "down" : "up"}`}>
          studio-api {apiDown ? "unreachable" : "connected"}
        </span>
      </header>

      <Scorecard />

      <div className="panel-grid">
        <InjectionPanel onAction={onAction} />
        <TracesPanel onAction={onAction} />
        <SpikePanel onAction={onAction} />
        <StormPanel onAction={onAction} />
        <ChaosPanel onAction={onAction} />
      </div>

      <HistoryPanel tick={historyTick} />
    </div>
  );
}
