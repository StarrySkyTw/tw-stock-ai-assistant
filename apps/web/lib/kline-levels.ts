export type KlineCandle = {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

export type DailyPriceLevelKind = "support" | "resistance";
export type DailyPriceLevelStrength = "strong" | "medium" | "weak";

export type DailyPriceLevel = {
  kind: DailyPriceLevelKind;
  value: number;
  zoneLow: number;
  zoneHigh: number;
  touches: number;
  strength: DailyPriceLevelStrength;
  distancePercent: number;
  score: number;
  lastTouchedIndex: number;
};

export type DailyPriceLevelSummary = {
  currentClose: number | null;
  levels: DailyPriceLevel[];
  supports: DailyPriceLevel[];
  resistances: DailyPriceLevel[];
  nearestSupport: DailyPriceLevel | null;
  nearestResistance: DailyPriceLevel | null;
  volumeRatio: number | null;
  rangeState: "near_support" | "near_resistance" | "balanced" | "extended";
};

type PriceCandidate = {
  kind: DailyPriceLevelKind;
  value: number;
  index: number;
  volume: number;
};

type PriceCluster = {
  kind: DailyPriceLevelKind;
  values: number[];
  indexes: number[];
  volumes: number[];
};

const DEFAULT_LOOKBACK = 120;
const MAX_LEVELS_PER_SIDE = 2;
const MIN_LEVEL_DISTANCE_PERCENT = 0.022;

export function analyzeDailyPriceLevels(candles: KlineCandle[], lookback = DEFAULT_LOOKBACK): DailyPriceLevelSummary {
  const usable = candles.filter(isValidCandle).slice(-lookback);
  const latest = usable.at(-1);
  if (!latest || usable.length < 12) {
    return emptySummary(latest?.close ?? null);
  }

  const currentClose = latest.close;
  const lows = usable.map((item) => item.low);
  const highs = usable.map((item) => item.high);
  const priceRange = Math.max(...highs) - Math.min(...lows);
  const tolerance = Math.max(currentClose * 0.0045, priceRange * 0.012, 0.01);
  const averageVolume = average(usable.slice(-20).map((item) => item.volume).filter((item) => item > 0));
  const latestVolume = latest.volume > 0 ? latest.volume : null;
  const volumeRatio = latestVolume && averageVolume ? latestVolume / averageVolume : null;

  const candidates = collectSwingCandidates(usable);
  addRangeCandidates(candidates, usable, 20);
  addRangeCandidates(candidates, usable, Math.min(60, usable.length));

  const clusters = clusterCandidates(candidates, tolerance);
  const scored = clusters
    .map((cluster) => buildPriceLevel(cluster, currentClose, tolerance, usable.length, averageVolume))
    .filter((level) => {
      const distance = Math.abs(level.distancePercent);
      if (level.touches < 2 && distance > 8) return false;
      if (level.kind === "support") return level.value <= currentClose * 1.018 && distance <= 18;
      return level.value >= currentClose * 0.982 && distance <= 18;
    });

  const supportPool = scored.filter((level) => level.kind === "support");
  const resistancePool = scored.filter((level) => level.kind === "resistance");
  const nearestSupport = nearestBelow(supportPool, currentClose);
  const nearestResistance = nearestAbove(resistancePool, currentClose);
  const supports = mergePriorityLevels(nearestSupport, supportPool, currentClose, supportRank).sort((a, b) => b.value - a.value);
  const resistances = mergePriorityLevels(nearestResistance, resistancePool, currentClose, resistanceRank).sort((a, b) => a.value - b.value);
  const levels = [...supports, ...resistances].sort((a, b) => a.value - b.value);

  return {
    currentClose,
    levels,
    supports,
    resistances,
    nearestSupport,
    nearestResistance,
    volumeRatio: volumeRatio === null ? null : round2(volumeRatio),
    rangeState: getRangeState(currentClose, nearestSupport, nearestResistance)
  };
}

function collectSwingCandidates(candles: KlineCandle[]) {
  const candidates: PriceCandidate[] = [];
  for (let index = 2; index < candles.length - 2; index += 1) {
    const window = candles.slice(index - 2, index + 3);
    const candle = candles[index];
    const isSwingLow = candle.low <= Math.min(...window.map((item) => item.low));
    const isSwingHigh = candle.high >= Math.max(...window.map((item) => item.high));
    if (isSwingLow) {
      candidates.push({ kind: "support", value: candle.low, index, volume: candle.volume });
    }
    if (isSwingHigh) {
      candidates.push({ kind: "resistance", value: candle.high, index, volume: candle.volume });
    }
  }
  return candidates;
}

function addRangeCandidates(candidates: PriceCandidate[], candles: KlineCandle[], windowSize: number) {
  if (candles.length < windowSize) return;
  const start = candles.length - windowSize;
  const window = candles.slice(start);
  const low = window.reduce((best, item, index) => (item.low < best.candle.low ? { candle: item, index } : best), {
    candle: window[0],
    index: 0
  });
  const high = window.reduce((best, item, index) => (item.high > best.candle.high ? { candle: item, index } : best), {
    candle: window[0],
    index: 0
  });
  candidates.push({ kind: "support", value: low.candle.low, index: start + low.index, volume: low.candle.volume });
  candidates.push({ kind: "resistance", value: high.candle.high, index: start + high.index, volume: high.candle.volume });
}

function clusterCandidates(candidates: PriceCandidate[], tolerance: number) {
  const clusters: PriceCluster[] = [];
  const ordered = [...candidates].sort((a, b) => a.value - b.value);
  for (const candidate of ordered) {
    const cluster = clusters.find(
      (item) => item.kind === candidate.kind && Math.abs(average(item.values) - candidate.value) <= tolerance
    );
    if (cluster) {
      cluster.values.push(candidate.value);
      cluster.indexes.push(candidate.index);
      cluster.volumes.push(candidate.volume);
    } else {
      clusters.push({
        kind: candidate.kind,
        values: [candidate.value],
        indexes: [candidate.index],
        volumes: [candidate.volume]
      });
    }
  }
  return clusters;
}

function buildPriceLevel(
  cluster: PriceCluster,
  currentClose: number,
  tolerance: number,
  length: number,
  averageVolume: number
): DailyPriceLevel {
  const value = round2(average(cluster.values));
  const touches = cluster.values.length;
  const lastTouchedIndex = Math.max(...cluster.indexes);
  const recency = lastTouchedIndex / Math.max(1, length - 1);
  const proximity = Math.max(0, 1 - Math.abs(value - currentClose) / Math.max(currentClose * 0.16, tolerance));
  const relativeVolume = averageVolume > 0 ? average(cluster.volumes.filter((item) => item > 0)) / averageVolume : 0;
  const volumeScore = Math.min(1.4, Math.max(0, relativeVolume - 0.8));
  const score = touches * 2.2 + recency * 2 + proximity * 1.8 + volumeScore;

  return {
    kind: cluster.kind,
    value,
    zoneLow: round2(value - tolerance),
    zoneHigh: round2(value + tolerance),
    touches,
    strength: score >= 7 ? "strong" : score >= 4.5 ? "medium" : "weak",
    distancePercent: round2(((value - currentClose) / currentClose) * 100),
    score: round2(score),
    lastTouchedIndex
  };
}

function supportRank(a: DailyPriceLevel, b: DailyPriceLevel, currentClose: number) {
  const aDistance = Math.abs(a.value - currentClose);
  const bDistance = Math.abs(b.value - currentClose);
  return aDistance - bDistance || b.score - a.score || b.value - a.value;
}

function resistanceRank(a: DailyPriceLevel, b: DailyPriceLevel, currentClose: number) {
  const aDistance = Math.abs(a.value - currentClose);
  const bDistance = Math.abs(b.value - currentClose);
  return aDistance - bDistance || b.score - a.score || a.value - b.value;
}

function nearestBelow(levels: DailyPriceLevel[], currentClose: number) {
  return (
    levels
      .filter((level) => level.value <= currentClose)
      .sort((a, b) => supportRank(a, b, currentClose))[0] ?? null
  );
}

function nearestAbove(levels: DailyPriceLevel[], currentClose: number) {
  return (
    levels
      .filter((level) => level.value >= currentClose)
      .sort((a, b) => resistanceRank(a, b, currentClose))[0] ?? null
  );
}

function mergePriorityLevels(
  priority: DailyPriceLevel | null,
  levels: DailyPriceLevel[],
  currentClose: number,
  ranker: (a: DailyPriceLevel, b: DailyPriceLevel, currentClose: number) => number
) {
  const selected: DailyPriceLevel[] = [];
  if (priority) selected.push(priority);
  for (const level of [...levels].sort((a, b) => ranker(a, b, currentClose))) {
    if (!selected.some((item) => item.kind === level.kind && item.value === level.value) && isSeparatedLevel(level, selected, currentClose)) {
      selected.push(level);
    }
    if (selected.length >= MAX_LEVELS_PER_SIDE) break;
  }
  return selected;
}

function isSeparatedLevel(level: DailyPriceLevel, selected: DailyPriceLevel[], currentClose: number) {
  if (!selected.length) return true;
  const minDistance = currentClose * MIN_LEVEL_DISTANCE_PERCENT;
  return selected.every((item) => {
    const zonesOverlap = level.zoneLow <= item.zoneHigh && level.zoneHigh >= item.zoneLow;
    return !zonesOverlap && Math.abs(level.value - item.value) >= minDistance;
  });
}

function getRangeState(
  currentClose: number,
  nearestSupport: DailyPriceLevel | null,
  nearestResistance: DailyPriceLevel | null
): DailyPriceLevelSummary["rangeState"] {
  const supportGap = nearestSupport ? Math.abs(nearestSupport.distancePercent) : null;
  const resistanceGap = nearestResistance ? Math.abs(nearestResistance.distancePercent) : null;
  if (supportGap !== null && supportGap <= 2.5) return "near_support";
  if (resistanceGap !== null && resistanceGap <= 2.5) return "near_resistance";
  if (nearestResistance && currentClose > nearestResistance.zoneHigh) return "extended";
  return "balanced";
}

function emptySummary(currentClose: number | null): DailyPriceLevelSummary {
  return {
    currentClose,
    levels: [],
    supports: [],
    resistances: [],
    nearestSupport: null,
    nearestResistance: null,
    volumeRatio: null,
    rangeState: "balanced"
  };
}

function isValidCandle(candle: KlineCandle) {
  return [candle.open, candle.high, candle.low, candle.close].every(Number.isFinite);
}

function average(values: number[]) {
  if (!values.length) return 0;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function round2(value: number) {
  return Math.round(value * 100) / 100;
}
