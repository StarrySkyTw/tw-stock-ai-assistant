import { describe, expect, it } from "vitest";
import { formatNumber, scoreClass } from "../lib/format";

describe("format helpers", () => {
  it("formats nullable numbers", () => {
    expect(formatNumber(null)).toBe("-");
    expect(formatNumber(12.345, 1)).toBe("12.3");
  });

  it("maps score classes", () => {
    expect(scoreClass(80)).toBe("text-gain");
    expect(scoreClass(65)).toBe("text-warn");
    expect(scoreClass(30)).toBe("text-loss");
  });
});

