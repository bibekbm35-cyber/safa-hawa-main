import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { localDayHour } from "../lib/aqi";

const AXIS = { stroke: "#79808f", fontSize: 11, fontFamily: "IBM Plex Mono, monospace" };

export default function PollutantChart({ readings }) {
  if (!readings?.length) {
    return <p className="placeholder">Nothing to plot for this window.</p>;
  }

  const data = readings.map((r) => ({
    t: localDayHour(r.observed_at),
    "PM2.5": r.pm2_5,
    PM10: r.pm10,
  }));

  // Label every sixth hour so the axis stays readable at 24h and at 720h.
  const tickGap = Math.max(1, Math.floor(data.length / 6));

  return (
    <ResponsiveContainer width="100%" height={260}>
      <LineChart data={data} margin={{ top: 6, right: 8, left: -12, bottom: 0 }}>
        <CartesianGrid stroke="#2a2f3a" vertical={false} />
        <XAxis
          dataKey="t"
          tick={AXIS}
          tickLine={false}
          axisLine={{ stroke: "#2a2f3a" }}
          interval={tickGap}
        />
        <YAxis
          tick={AXIS}
          tickLine={false}
          axisLine={false}
          label={{
            value: "µg/m³",
            angle: -90,
            position: "insideLeft",
            fill: "#79808f",
            fontSize: 11,
          }}
        />
        <Tooltip
          contentStyle={{
            background: "#1e222a",
            border: "1px solid #3a4150",
            borderRadius: 4,
            fontFamily: "IBM Plex Mono, monospace",
            fontSize: 12,
          }}
          labelStyle={{ color: "#a3aab8" }}
        />
        <Legend wrapperStyle={{ fontSize: 12, color: "#a3aab8" }} />
        <Line type="monotone" dataKey="PM2.5" stroke="#e8eaee" strokeWidth={1.8} dot={false} />
        <Line type="monotone" dataKey="PM10" stroke="#79808f" strokeWidth={1.4} dot={false} strokeDasharray="3 3" />
      </LineChart>
    </ResponsiveContainer>
  );
}
