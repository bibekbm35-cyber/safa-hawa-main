import { bandColor, relativeAge } from "../lib/aqi";

export default function CurrentReading({ latest }) {
  if (!latest?.reading) {
    return (
      <div className="panel current">
        <p className="panel-title">Right now</p>
        <p className="placeholder">This station has not reported yet.</p>
      </div>
    );
  }

  const { reading, band_label, advice, age_minutes, station } = latest;
  const color = bandColor(reading.band);

  return (
    <div className="panel current">
      <p className="panel-title">{station.name}</p>
      <p className="value" style={{ color }}>
        {reading.us_aqi ?? "—"}
      </p>
      <p className="band" style={{ color }}>
        {band_label}
      </p>
      <p className="advice">{advice}</p>

      <div className="readout">
        <div>
          <span className="n">{reading.pm2_5?.toFixed(1) ?? "—"}</span>
          PM2.5 µg/m³
        </div>
        <div>
          <span className="n">{reading.pm10?.toFixed(0) ?? "—"}</span>
          PM10 µg/m³
        </div>
      </div>

      <p className="meta">Measured {relativeAge(age_minutes)}</p>
    </div>
  );
}
