import { useCallback, useEffect, useState } from "react";
import CurrentReading from "./components/CurrentReading";
import DailyBars from "./components/DailyBars";
import HazeStrip from "./components/HazeStrip";
import PipelinePanel from "./components/PipelinePanel";
import PollutantChart from "./components/PollutantChart";
import StationGrid from "./components/StationGrid";
import { api } from "./lib/api";
import { BAND_COLORS, BAND_LABELS, BAND_ORDER } from "./lib/aqi";

const WINDOWS = [
  { label: "24h", hours: 24 },
  { label: "3d", hours: 72 },
  { label: "7d", hours: 168 },
];

const REFRESH_MS = 60_000;

export default function App() {
  const [latest, setLatest] = useState([]);
  const [status, setStatus] = useState(null);
  const [selected, setSelected] = useState(null);
  const [readings, setReadings] = useState([]);
  const [daily, setDaily] = useState([]);
  const [hours, setHours] = useState(24);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  const loadOverview = useCallback(async () => {
    const [latestRows, ingest] = await Promise.all([api.latest(), api.ingestStatus()]);
    setLatest(latestRows);
    setStatus(ingest);
    return latestRows;
  }, []);

  // Initial load. Picks the worst-affected station by default rather than the
  // first alphabetically -- if one part of the valley is in trouble, that is
  // the thing worth putting on screen.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [rows, worst] = await Promise.all([
          loadOverview(),
          api.worst().catch(() => null),
        ]);
        if (cancelled) return;
        setSelected(worst?.station?.slug ?? rows[0]?.station?.slug ?? null);
      } catch (err) {
        if (!cancelled) setError(err.message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [loadOverview]);

  // Detail for the selected station and window.
  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    (async () => {
      try {
        const [rows, days] = await Promise.all([
          api.readings(selected, hours),
          api.summary(selected, 14),
        ]);
        if (cancelled) return;
        setReadings(rows);
        setDaily(days);
        setError(null);
      } catch (err) {
        if (!cancelled) setError(err.message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selected, hours]);

  // Poll for fresh data. The upstream is hourly, so this only ever finds
  // something new once an hour -- but it keeps the staleness clock honest.
  useEffect(() => {
    const timer = setInterval(() => {
      loadOverview().catch((err) => setError(err.message));
    }, REFRESH_MS);
    return () => clearInterval(timer);
  }, [loadOverview]);

  const current = latest.find((r) => r.station.slug === selected);

  return (
    <div className="shell">
      <header className="masthead">
        <div>
          <h1 className="wordmark">
            safa<span>·</span>Hawa
          </h1>
          <p className="strapline">Hourly air quality across the Kathmandu Valley</p>
        </div>
        <span className={`pill ${status?.stale ? "stale" : ""}`}>
          <span className="dot" />
          {status?.stale ? "data is stale" : "live"}
        </span>
      </header>

      {status?.stale && (
        <div className="banner">
          <strong>These readings are out of date.</strong>
          <p>
            The ingest poller has not stored a new reading recently, so what you see below
            is the last known state of the valley — not the current one.
          </p>
        </div>
      )}

      {error && (
        <div className="banner error" role="alert">
          <strong>Could not reach the API.</strong>
          <p>
            The dashboard is showing whatever it loaded last. <code>{error}</code>
          </p>
        </div>
      )}

      {loading ? (
        <p className="placeholder">Loading the valley…</p>
      ) : (
        <>
          <div className="hero">
            <CurrentReading latest={current} />
            <div className="panel">
              <div className="panel-head">
                <p className="panel-title">Hour by hour</p>
                <div className="controls">
                  {WINDOWS.map((w) => (
                    <button
                      key={w.hours}
                      aria-pressed={hours === w.hours}
                      onClick={() => setHours(w.hours)}
                    >
                      {w.label}
                    </button>
                  ))}
                </div>
              </div>
              <HazeStrip readings={readings} />
              <div className="legend">
                {BAND_ORDER.map((band) => (
                  <div key={band}>
                    <i style={{ background: BAND_COLORS[band] }} />
                    {BAND_LABELS[band]}
                  </div>
                ))}
              </div>
            </div>
          </div>

          <section>
            <p className="panel-title">Across the valley</p>
            <StationGrid stations={latest} selected={selected} onSelect={setSelected} />
          </section>

          <div className="split">
            <div className="panel">
              <p className="panel-title">Particulate concentration</p>
              <PollutantChart readings={readings} />
            </div>
            <div className="panel">
              <p className="panel-title">Ingest pipeline</p>
              <PipelinePanel status={status} />
            </div>
          </div>

          <section className="panel">
            <p className="panel-title">Daily average, last 14 days</p>
            <DailyBars days={daily} />
          </section>
        </>
      )}

      <footer>
        <span>Source: Open-Meteo air quality reanalysis. Times shown in Nepal Standard Time.</span>
        <span className="mono">{status?.total_readings?.toLocaleString() ?? 0} readings stored</span>
      </footer>
    </div>
  );
}
