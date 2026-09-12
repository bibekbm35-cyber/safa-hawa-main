// The band definitions live on the server; these are the presentation layer's
// view of them. Colour is the only saturated thing in this interface, and it
// always means the same thing: how bad the air is. Nothing decorative is
// allowed to use these values.
export const BAND_COLORS = {
  good: "#5BBF7B",
  moderate: "#D9C15C",
  unhealthy_sensitive: "#DF9445",
  unhealthy: "#D45B54",
  very_unhealthy: "#9A6BC4",
  hazardous: "#8C4A4A",
};

export const BAND_LABELS = {
  good: "Good",
  moderate: "Moderate",
  unhealthy_sensitive: "Unhealthy for sensitive groups",
  unhealthy: "Unhealthy",
  very_unhealthy: "Very unhealthy",
  hazardous: "Hazardous",
};

export const BAND_ORDER = [
  "good",
  "moderate",
  "unhealthy_sensitive",
  "unhealthy",
  "very_unhealthy",
  "hazardous",
];

export function bandColor(band) {
  return BAND_COLORS[band] ?? "#3A404C";
}

const KATHMANDU = { timeZone: "Asia/Kathmandu" };

export function localHour(iso) {
  return new Date(iso).toLocaleTimeString("en-GB", {
    ...KATHMANDU,
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function localDayHour(iso) {
  return new Date(iso).toLocaleString("en-GB", {
    ...KATHMANDU,
    day: "2-digit",
    month: "short",
    hour: "2-digit",
  });
}

export function relativeAge(minutes) {
  if (minutes == null) return "no data";
  if (minutes < 90) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 36) return `${hours} h ago`;
  return `${Math.round(hours / 24)} days ago`;
}
