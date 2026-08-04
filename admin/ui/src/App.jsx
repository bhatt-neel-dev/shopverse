import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import AppliancesPanel from "./panels/AppliancesPanel";
import ChaosPanel from "./panels/ChaosPanel";
import HistoryPanel from "./panels/HistoryPanel";
import IngestPanel from "./panels/IngestPanel";
import InjectionPanel from "./panels/InjectionPanel";
import MotadataPanel from "./panels/MotadataPanel";
import Scorecard from "./panels/Scorecard";
import SpikePanel from "./panels/SpikePanel";
import StormPanel from "./panels/StormPanel";
import TracesPanel from "./panels/TracesPanel";

const TABS = [
  ["configure", "Configuration"],
  ["ingest", "Ingestion"],
  ["scenarios", "Scenarios"],
];

export default function App() {
  const [historyTick, setHistoryTick] = useState(0);
  const [apiDown, setApiDown] = useState(false);
  const [selected, setSelected] = useState(null);
  const [tab, setTab] = useState("configure");

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

      {!selected ? (
        <AppliancesPanel onOpen={setSelected} onAction={onAction} />
      ) : (
        <>
          <div className="device-bar">
            <button className="ghost" onClick={() => setSelected(null)}>
              ← All appliances
            </button>
            <strong>{selected.name || selected.url}</strong>
            <nav className="device-tabs">
              {TABS.map(([key, label]) => (
                <button
                  key={key}
                  className={tab === key ? "" : "ghost"}
                  onClick={() => setTab(key)}
                >
                  {label}
                </button>
              ))}
            </nav>
          </div>

          {tab === "configure" && <MotadataPanel appliance={selected} onAction={onAction} />}
          {tab === "ingest" && <IngestPanel onAction={onAction} />}
          {tab === "scenarios" && (
            <>
              <Scorecard />
              <div className="panel-grid">
                <InjectionPanel onAction={onAction} />
                <TracesPanel onAction={onAction} />
                <SpikePanel onAction={onAction} />
                <StormPanel onAction={onAction} />
                <ChaosPanel onAction={onAction} />
              </div>
            </>
          )}
        </>
      )}

      <HistoryPanel tick={historyTick} />
    </div>
  );
}
