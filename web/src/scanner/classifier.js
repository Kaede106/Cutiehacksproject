/*
 * CutieFarm classifier.
 *
 * Interface: a classifier is any object with
 *   async classify(source) -> { label, confidence, scores: { unripe, ripening, ripe } }
 * plus an optional `description` string the scanner shows under the reading.
 * `source` is an ImageData, a canvas, or a plain { data, width, height } RGBA buffer that holds only
 * the region of interest (the scanner crops the centre square before calling). `label` is one of
 * 'unripe' | 'ripening' | 'ripe' | 'none', `confidence` is 0..1, `scores` sum to about 1 when fruit is present.
 *
 * A CNN would implement the same interface. Its factory loads the model once (TF.js
 * `tf.loadGraphModel(url)` or ONNX Runtime Web `ort.InferenceSession.create(url)`), and its
 * classify() resizes the source to the model's input size, normalises it into a tensor, runs
 * inference, applies softmax and maps the outputs onto the three `scores` keys. It returns 'none'
 * when a background class wins or the top score is too low. The scanner UI does not change: pass
 * the object as `mountScanner(root, { classifier })`.
 *
 * The default below is a colour heuristic on HSV values. Everything except the factory is a pure
 * function on { data, width, height } so it runs in Node (see classifier.test.mjs).
 */

export const LABELS = ['unripe', 'ripening', 'ripe'];

/** Aspect ratio of the scanner's viewport. The region of interest is a centred square inside it. */
export const VIEW_ASPECT = 4 / 3;
export const ROI_FRACTION = 0.6;

export const THRESHOLDS = {
  darkV: 0.2, // darker pixels are shadow or background
  glare: { minV: 0.965, maxS: 0.12 }, // clipped specular highlights
  fruit: { minS: 0.33, minV: 0.22, hueMin: 5, hueMax: 145 },
  // YCbCr box for skin (and brown wood). Saturated orange peel has Cb < 77, so it falls outside.
  skin: { cbMin: 77, cbMax: 127, crMin: 133, crMax: 173, maxS: 0.72, maxHue: 50 },
  // Hue breakpoints in degrees: orange up to ripeFull, yellow between yellowFull and yellowEnd,
  // green from greenFull. Linear blends between them, so the three weights always sum to 1.
  hue: { ripeFull: 36, yellowFull: 48, yellowEnd: 60, greenFull: 76 },
  coverage: { none: 0.1, full: 0.4 }, // share of the ROI that must be fruit
};

const DARK = 0, GLARE = 1, FRUIT = 2, SKIN = 3, OTHER = 4;
export const PIXEL_CLASS = { DARK, GLARE, FRUIT, SKIN, OTHER };

export function rgbToHsv(r, g, b) {
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const d = max - min;
  let h = 0;
  if (d) {
    if (max === r) h = ((g - b) / d) % 6;
    else if (max === g) h = (b - r) / d + 2;
    else h = (r - g) / d + 4;
    h *= 60;
    if (h < 0) h += 360;
  }
  return { h, s: max ? d / max : 0, v: max / 255 };
}

export function isSkinTone(r, g, b, T = THRESHOLDS) {
  const cb = 128 - 0.168736 * r - 0.331264 * g + 0.5 * b;
  const cr = 128 + 0.5 * r - 0.418688 * g - 0.081312 * b;
  return cb >= T.skin.cbMin && cb <= T.skin.cbMax && cr >= T.skin.crMin && cr <= T.skin.crMax;
}

/** Classify one pixel. Writes the hue to `out.h` for fruit pixels. */
export function classifyPixel(r, g, b, out = {}, T = THRESHOLDS) {
  const { h, s, v } = rgbToHsv(r, g, b);
  out.h = h;
  if (v < T.darkV) return DARK;
  if (v > T.glare.minV && s < T.glare.maxS) return GLARE;
  const f = T.fruit;
  if (h >= f.hueMin && h <= f.hueMax && s >= f.minS && v >= f.minV) {
    if (h < T.skin.maxHue && s < T.skin.maxS && isSkinTone(r, g, b, T)) return SKIN;
    return FRUIT;
  }
  return OTHER;
}

/** Split a fruit hue into [ripe, yellow, green] weights that sum to 1. */
export function hueWeights(h, T = THRESHOLDS) {
  const { ripeFull, yellowFull, yellowEnd, greenFull } = T.hue;
  if (h <= ripeFull) return [1, 0, 0];
  if (h < yellowFull) {
    const t = (h - ripeFull) / (yellowFull - ripeFull);
    return [1 - t, t, 0];
  }
  if (h <= yellowEnd) return [0, 1, 0];
  if (h < greenFull) {
    const t = (h - yellowEnd) / (greenFull - yellowEnd);
    return [0, 1 - t, t];
  }
  return [0, 0, 1];
}

const clamp01 = (x) => (x < 0 ? 0 : x > 1 ? 1 : x);
export function smoothstep(a, b, x) {
  const t = clamp01((x - a) / (b - a));
  return t * t * (3 - 2 * t);
}

/** Count fruit-coloured pixels and their hue weights over the whole buffer. */
export function analyzeBuffer(buf, T = THRESHOLDS) {
  const { data, width, height } = buf;
  const total = width * height;
  const counts = new Int32Array(5);
  let wRipe = 0, wYellow = 0, wGreen = 0;
  const scratch = { h: 0 };

  for (let i = 0; i < total * 4; i += 4) {
    const cls = classifyPixel(data[i], data[i + 1], data[i + 2], scratch, T);
    counts[cls]++;
    if (cls !== FRUIT) continue;
    const [wr, wy, wg] = hueWeights(scratch.h, T);
    wRipe += wr;
    wYellow += wy;
    wGreen += wg;
  }

  return {
    width, height, total,
    fruit: counts[FRUIT],
    skin: counts[SKIN],
    glare: counts[GLARE],
    weights: { ripe: wRipe, yellow: wYellow, green: wGreen },
  };
}

/** Turn pixel statistics into a reading. */
export function scoreAnalysis(stats, T = THRESHOLDS) {
  const coverage = stats.total ? stats.fruit / stats.total : 0;

  let o = 0, y = 0, g = 0;
  if (stats.fruit) {
    o = stats.weights.ripe / stats.fruit;
    y = stats.weights.yellow / stats.fruit;
    g = stats.weights.green / stats.fruit;
  }
  // Green and orange on the same fruit is the ripening signal, so the smaller of the two shares
  // moves into "ripening" with extra weight.
  const mix = Math.min(g, o);
  const scores = {
    unripe: g - 0.75 * mix,
    ripening: y + 1.5 * mix,
    ripe: o - 0.75 * mix,
  };

  if (coverage < T.coverage.none) {
    return {
      label: 'none',
      confidence: 1 - coverage / T.coverage.none,
      scores,
      coverage,
    };
  }

  const ranked = LABELS.slice().sort((a, b) => scores[b] - scores[a]);
  const margin = scores[ranked[0]] - scores[ranked[1]];
  const coverageFactor = smoothstep(T.coverage.none, T.coverage.full, coverage);
  const confidence = coverageFactor * (0.35 + 0.65 * clamp01(margin / 0.6));
  return {
    label: ranked[0],
    confidence,
    scores,
    coverage,
  };
}

export function classifyBuffer(buf, T = THRESHOLDS) {
  return scoreAnalysis(analyzeBuffer(buf, T), T);
}

export function confidenceLevel(confidence) {
  if (confidence >= 0.7) return 'high';
  if (confidence >= 0.45) return 'medium';
  return 'low';
}

/**
 * The centred square the scanner analyses, in source pixels. The source is shown with
 * `object-fit: cover` in a box of `viewAspect`, so the square is a share of the visible area.
 */
export function centerRoi(srcW, srcH, viewAspect = VIEW_ASPECT, fraction = ROI_FRACTION) {
  let visW = srcW, visH = srcH;
  if (srcW / srcH > viewAspect) visW = srcH * viewAspect;
  else visH = srcW / viewAspect;
  const size = Math.max(1, Math.round(Math.min(visW, visH) * fraction));
  return { x: Math.round((srcW - size) / 2), y: Math.round((srcH - size) / 2), size };
}

/** Box-filter crop and resize of an RGBA buffer, for environments without a canvas. */
export function cropResize(buf, roi, outSize) {
  const out = new Uint8ClampedArray(outSize * outSize * 4);
  const scale = roi.size / outSize;
  for (let oy = 0; oy < outSize; oy++) {
    const y0 = roi.y + Math.floor(oy * scale), y1 = Math.max(y0 + 1, roi.y + Math.floor((oy + 1) * scale));
    for (let ox = 0; ox < outSize; ox++) {
      const x0 = roi.x + Math.floor(ox * scale), x1 = Math.max(x0 + 1, roi.x + Math.floor((ox + 1) * scale));
      let r = 0, g = 0, b = 0, n = 0;
      for (let y = y0; y < y1; y++) {
        for (let x = x0; x < x1; x++) {
          const i = (y * buf.width + x) * 4;
          r += buf.data[i];
          g += buf.data[i + 1];
          b += buf.data[i + 2];
          n++;
        }
      }
      const o = (oy * outSize + ox) * 4;
      out[o] = r / n;
      out[o + 1] = g / n;
      out[o + 2] = b / n;
      out[o + 3] = 255;
    }
  }
  return { data: out, width: outSize, height: outSize };
}

function toBuffer(source) {
  if (source && source.data && source.width && source.height) return source;
  if (source && typeof source.getContext === 'function') {
    const ctx = source.getContext('2d', { willReadFrequently: true });
    return ctx.getImageData(0, 0, source.width, source.height);
  }
  throw new TypeError('classify() needs an ImageData, a canvas or a { data, width, height } buffer');
}

export function createColorClassifier({ thresholds = THRESHOLDS } = {}) {
  return {
    id: 'color-heuristic',
    description: 'Ripeness estimate from peel colour.',
    async classify(source) {
      return classifyBuffer(toBuffer(source), thresholds);
    },
  };
}
