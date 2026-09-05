import { describe, it, expect } from "vitest";
import { bandColor, relativeAge } from "./aqi";

describe("AQI helpers", () => {
  it("returns correct color for AQI bands", () => {
    expect(bandColor("good")).toBe("#5BBF7B");
    expect(bandColor("hazardous")).toBe("#8C4A4A");
    expect(bandColor("unknown")).toBe("#3A404C");
  });

  it("formats relative age properly", () => {
    expect(relativeAge(null)).toBe("no data");
    expect(relativeAge(45)).toBe("45 min ago");
    expect(relativeAge(120)).toBe("2 h ago");
    expect(relativeAge(1440)).toBe("24 h ago");
    expect(relativeAge(2880)).toBe("2 days ago");
  });
});
