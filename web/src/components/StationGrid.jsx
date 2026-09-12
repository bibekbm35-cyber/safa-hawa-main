import { bandColor } from "../lib/aqi";

export default function StationGrid({ stations, selected, onSelect }) {
  return (
    <div className="stations">
      {stations.map((entry) => {
        const aqi = entry.reading?.us_aqi;
        const color = bandColor(entry.reading?.band);
        const isSelected = entry.station.slug === selected;

        return (
          <button
            key={entry.station.slug}
            className="station"
            aria-pressed={isSelected}
            style={{ borderLeftColor: color }}
            onClick={() => onSelect(entry.station.slug)}
          >
            <div className="name">{entry.station.name}</div>
            <div className="district">{entry.station.district}</div>
            <div className="aqi" style={{ color }}>
              {aqi ?? "—"} <small>{entry.band_label ?? "no data"}</small>
            </div>
          </button>
        );
      })}
    </div>
  );
}
