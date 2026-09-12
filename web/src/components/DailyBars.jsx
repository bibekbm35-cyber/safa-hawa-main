import { bandColor } from "../lib/aqi";

/**
 * Daily AQI, derived server-side from each day's mean concentration rather
 * than by averaging hourly AQI values -- see the API's summary endpoint for
 * why those two are not the same number.
 */
export default function DailyBars({ days }) {
  if (!days?.length) return <p className="placeholder">No daily history yet.</p>;

  const peak = Math.max(...days.map((d) => d.max_aqi ?? 0), 60);

  return (
    <div>
      <div className="strip" style={{ height: 100, gap: 6 }}>
        {days.map((d) => (
          <div
            key={d.day}
            className="hour"
            title={`${d.day} — average AQI ${d.avg_aqi}, peak ${d.max_aqi} (${d.hours_recorded} h recorded)`}
            style={{
              height: `${Math.max(8, ((d.avg_aqi ?? 0) / peak) * 100)}%`,
              background: bandColor(d.band),
            }}
          />
        ))}
      </div>
      <div className="strip-axis">
        <span>{days[0].day}</span>
        <span>{days[days.length - 1].day}</span>
      </div>
    </div>
  );
}
