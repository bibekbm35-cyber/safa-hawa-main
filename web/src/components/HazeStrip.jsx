import { bandColor, localHour } from "../lib/aqi";

/**
 * The signature element: one block per hour, height and colour both driven by
 * AQI. A line chart tells you the trajectory; this tells you the *shape of the
 * day* at a glance -- the morning and evening traffic peaks in the valley show
 * up as two towers without anyone having to read an axis.
 */
export default function HazeStrip({ readings }) {
  if (!readings?.length) {
    return <p className="placeholder">No readings in this window yet.</p>;
  }

  const peak = Math.max(...readings.map((r) => r.us_aqi ?? 0), 60);

  return (
    <>
      <div className="strip" role="img" aria-label={`Hourly air quality, ${readings.length} hours`}>
        {readings.map((r) => (
          <div
            key={r.observed_at}
            className="hour"
            title={`${localHour(r.observed_at)} — AQI ${r.us_aqi ?? "n/a"}`}
            style={{
              height: `${Math.max(6, ((r.us_aqi ?? 0) / peak) * 100)}%`,
              background: bandColor(r.band),
            }}
          />
        ))}
      </div>
      <div className="strip-axis">
        <span>{localHour(readings[0].observed_at)}</span>
        <span>{localHour(readings[readings.length - 1].observed_at)}</span>
      </div>
    </>
  );
}

/** The same idea shrunk to a sparkline for each station card. */
export function MiniStrip({ readings }) {
  if (!readings?.length) return null;
  return (
    <div className="mini-strip" aria-hidden="true">
      {readings.slice(-12).map((r) => (
        <span key={r.observed_at} style={{ background: bandColor(r.band) }} />
      ))}
    </div>
  );
}
