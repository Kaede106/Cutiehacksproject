// Smooths per-frame readings so the label does not flicker. Pure and model-agnostic: it only reads
// { label, confidence, scores, regions } from each frame, so it works for any classifier.
import { LABELS } from './classifier.js';

export function createSmoother({ tau = 0.4, switchMargin = 0.08, enterNone = 0.65, exitNone = 0.35, staleMs = 1000 } = {}) {
  let scores = null;
  let confidence = 0;
  let noneEma = 0;
  let label = null;
  let lastT = null;
  let lastFruitT = -Infinity;
  let regions = [];

  function reset() {
    scores = null;
    confidence = 0;
    noneEma = 0;
    label = null;
    lastT = null;
    lastFruitT = -Infinity;
    regions = [];
  }

  /** Feed one frame's result at time `t` (ms). Returns the smoothed reading. */
  function update(result, t) {
    // Exponential moving average with a time constant, so the frame rate does not matter.
    const a = lastT == null ? 1 : 1 - Math.exp(-Math.max(0, t - lastT) / 1000 / tau);
    lastT = t;
    const noneFrame = result.label === 'none';
    noneEma += a * ((noneFrame ? 1 : 0) - noneEma);

    if (!noneFrame) {
      const snap = !scores || t - lastFruitT > staleMs;
      if (snap) {
        scores = { ...result.scores };
        confidence = result.confidence;
      } else {
        for (const k of LABELS) scores[k] += a * ((result.scores[k] ?? 0) - scores[k]);
        confidence += a * (result.confidence - confidence);
      }
      lastFruitT = t;
      regions = result.regions ?? [];
    }

    const wasNone = label == null || label === 'none';
    const none = !scores || (wasNone ? noneEma > exitNone : noneEma > enterNone);
    let next;
    if (none) next = 'none';
    else {
      const top = LABELS.reduce((best, k) => (scores[k] > scores[best] ? k : best), LABELS[0]);
      // Hysteresis: switch only when the new leader is clearly ahead of the current label.
      next = wasNone || top === label || scores[top] - scores[label] > switchMargin ? top : label;
    }
    const changed = next !== label;
    label = next;
    return {
      label,
      confidence: label === 'none' ? noneEma : confidence,
      scores: scores ? { ...scores } : { unripe: 0, ripening: 0, ripe: 0, mold: 0 },
      regions: label === 'mold' ? regions : [],
      changed,
    };
  }

  return { update, reset };
}
