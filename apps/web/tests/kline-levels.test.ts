import { describe, expect, it } from "vitest";
import { analyzeDailyPriceLevels, type KlineCandle } from "../lib/kline-levels";

function candle(index: number, low: number, high: number, close = (low + high) / 2): KlineCandle {
  return {
    time: `D${index}`,
    open: close - 0.5,
    high,
    low,
    close,
    volume: 1_000_000 + index * 1_000
  };
}

describe("daily K-line level analysis", () => {
  it("finds the nearest useful support and resistance levels", () => {
    const candles: KlineCandle[] = [
      candle(1, 96, 104),
      candle(2, 98, 108),
      candle(3, 100, 112),
      candle(4, 95.5, 107),
      candle(5, 101, 116),
      candle(6, 99, 110),
      candle(7, 96.2, 106),
      candle(8, 103, 118),
      candle(9, 101, 111),
      candle(10, 96.1, 108),
      candle(11, 104, 117.8),
      candle(12, 102, 112),
      candle(13, 97, 109),
      candle(14, 105, 118.2),
      candle(15, 103, 113),
      candle(16, 100, 115, 110)
    ];

    const summary = analyzeDailyPriceLevels(candles);

    expect(summary.nearestSupport?.value).toBeGreaterThanOrEqual(95);
    expect(summary.nearestSupport?.value).toBeLessThanOrEqual(110);
    expect(summary.nearestResistance?.value).toBeGreaterThanOrEqual(116);
    expect(summary.supports.length).toBeLessThanOrEqual(2);
    expect(summary.resistances.length).toBeLessThanOrEqual(2);
    expect(summary.levels.some((level) => level.touches >= 2)).toBe(true);
  });

  it("keeps only the most useful separated levels on each side", () => {
    const candles: KlineCandle[] = Array.from({ length: 80 }, (_, index) => {
      const cycle = index % 8;
      const low = cycle === 2 ? 94 : cycle === 5 ? 97.5 : 99 + Math.sin(index / 3);
      const high = cycle === 3 ? 114 : cycle === 6 ? 109.5 : 106 + Math.cos(index / 4);
      const close = index === 79 ? 104 : 101 + Math.sin(index / 5);
      return candle(index + 1, low, high, close);
    });

    const summary = analyzeDailyPriceLevels(candles);

    expect(summary.supports.length).toBeLessThanOrEqual(2);
    expect(summary.resistances.length).toBeLessThanOrEqual(2);
    expect(summary.levels.length).toBeLessThanOrEqual(4);
    expect(summary.supports.every((level) => level.value <= 104 * 1.018)).toBe(true);
    expect(summary.resistances.every((level) => level.value >= 104 * 0.982)).toBe(true);
  });

  it("returns an empty summary when there are not enough candles", () => {
    const summary = analyzeDailyPriceLevels([candle(1, 10, 12), candle(2, 11, 13)]);

    expect(summary.levels).toEqual([]);
    expect(summary.currentClose).toBe(12);
  });
});
