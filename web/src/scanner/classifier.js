/*
 * CutieFarm classifier.
 *
 * Interface: a classifier is any object with
 *   async classify(source) -> { label, confidence, scores: { unripe, ripening, ripe, mold }, regions? }
 * plus an optional `description` string the scanner shows under the reading.
 * `source` is an ImageData, a canvas, or a plain { data, width, height } RGBA buffer that holds only
 * the region of interest (the scanner crops the centre square before calling). `label` is one of
 * 'unripe' | 'ripening' | 'ripe' | 'mold' | 'none', `confidence` is 0..1, `scores` sum to about 1,
 * and `regions` is an optional list of { x, y, w, h, label } boxes in 0..1 coordinates of the source.
 *
 * A CNN would implement the same interface. Its factory loads the model once (TF.js
 * `tf.loadGraphModel(url)` or ONNX Runtime Web `ort.InferenceSession.create(url)`), and its
 * classify() resizes the source to the model's input size, normalises it into a tensor, runs
 * inference, applies softmax and maps the outputs onto the four `scores` keys. It returns 'none'
 * when a background class wins or the top score is too low. The scanner UI does not change: pass
 * the object as `mountScanner(root, { classifier })`.
 *
 * The default below is a colour heuristic on HSV values. Everything except the factory is a pure
 * function on { data, width, height } so it runs in Node (see classifier.test.mjs).
 */

export const LABELS = ['unripe', 'ripening', 'ripe', 'mold'];

/** Aspect ratio of the scanner's viewport. The region of interest is a centred square inside it. */
export const VIEW_ASPECT = 4 / 3;
export const ROI_FRACTION = 0.6;

export const THRESHOLDS = {
  darkV: 0.2, // darker pixels are shadow or background
  glare: { minV: 0.965, maxS: 0.12 }, // clipped specular highlights, never counted as mold
  fruit: { minS: 0.33, minV: 0.22, hueMin: 5, hueMax: 145 },
  white: { maxS: 0.2, minV: 0.62 }, // white fuzz
  blueGreen: { hueMin: 150, hueMax: 235, minS: 0.1, maxS: 0.65, minV: 0.25, maxV: 0.92 },
  // YCbCr box for skin (and brown wood). Saturated orange peel has Cb < 77, so it falls outside.
  skin: { cbMin: 77, cbMax: 127, crMin: 133, crMax: 173, maxS: 0.72, maxHue: 50 },
  // Hue breakpoints in degrees: orange up to ripeFull, yellow between yellowFull and yellowEnd,
  // green from greenFull. Linear blends between them, so the three weights always sum to 1.
  hue: { ripeFull: 36, yellowFull: 48, yellowEnd: 60, greenFull: 76 },
  coverage: { none: 0.1, full: 0.4 }, // share of the ROI that must be fruit
  grid: 16, // the ROI is split into grid x grid cells for the mold search
  fruitCell: 0.35,
  moldCell: 0.25,
  enclosureRays: 5, // of 8 rays from a mold cell, this many must reach fruit
  mold: { evidenceStart: 0.03, evidenceFull: 0.1, blueWeight: 2.5 },
};

const DARK = 0, GLARE = 1, WHITE = 2, BLUE = 3, FRUIT = 4, SKIN = 5, OTHER = 6;
export const PIXEL_CLASS = { DARK, GLARE, WHITE, BLUE, FRUIT, SKIN, OTHER };

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
  if (s <= T.white.maxS && v >= T.white.minV) return WHITE;
  const bg = T.blueGreen;
  if (h >= bg.hueMin && h <= bg.hueMax && s >= bg.minS && s <= bg.maxS && v >= bg.minV && v <= bg.maxV) return BLUE;
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

const RAYS = [[1, 0], [-1, 0], [0, 1], [0, -1], [1, 1], [-1, -1], [1, -1], [-1, 1]];

/** Count pixel classes over the whole buffer and find mold cells enclosed by fruit. */
export function analyzeBuffer(buf, T = THRESHOLDS) {
  const { data, width, height } = buf;
  const gw = Math.max(1, Math.min(T.grid, width));
  const gh = Math.max(1, Math.min(T.grid, height));
  const cells = gw * gh;
  const cTotal = new Int32Array(cells);
  const cFruit = new Int32Array(cells);
  const cWhite = new Int32Array(cells);
  const cBlue = new Int32Array(cells);
  const counts = new Int32Array(7);
  let wRipe = 0, wYellow = 0, wGreen = 0;
  const scratch = { h: 0 };

  for (let y = 0; y < height; y++) {
    const row = Math.floor((y * gh) / height) * gw;
    for (let x = 0; x < width; x++) {
      const i = (y * width + x) * 4;
      const cls = classifyPixel(data[i], data[i + 1], data[i + 2], scratch, T);
      const c = row + Math.floor((x * gw) / width);
      counts[cls]++;
      cTotal[c]++;
      if (cls === FRUIT) {
        cFruit[c]++;
        const [wr, wy, wg] = hueWeights(scratch.h, T);
        wRipe += wr;
        wYellow += wy;
        wGreen += wg;
      } else if (cls === WHITE) cWhite[c]++;
      else if (cls === BLUE) cBlue[c]++;
    }
  }

  const isFruitCell = new Uint8Array(cells);
  const isMoldCand = new Uint8Array(cells);
  for (let c = 0; c < cells; c++) {
    if (!cTotal[c]) continue;
    isFruitCell[c] = cFruit[c] / cTotal[c] >= T.fruitCell ? 1 : 0;
    isMoldCand[c] = (cWhite[c] + cBlue[c]) / cTotal[c] >= T.moldCell ? 1 : 0;
  }

  // A mold candidate counts only when fruit surrounds it: cast 8 rays through other candidate
  // cells and require most of them to reach a fruit cell. A white wall or table next to the fruit
  // reaches fruit in at most three or four directions, so it is ignored.
  const enclosed = new Uint8Array(cells);
  for (let cy = 0; cy < gh; cy++) {
    for (let cx = 0; cx < gw; cx++) {
      const c = cy * gw + cx;
      if (!isMoldCand[c]) continue;
      let hits = 0;
      for (const [dx, dy] of RAYS) {
        let x = cx + dx, y = cy + dy;
        while (x >= 0 && y >= 0 && x < gw && y < gh) {
          const n = y * gw + x;
          if (isFruitCell[n]) { hits++; break; }
          if (!isMoldCand[n]) break;
          x += dx;
          y += dy;
        }
      }
      if (hits >= T.enclosureRays) enclosed[c] = 1;
    }
  }

  let moldWhite = 0, moldBlue = 0;
  for (let c = 0; c < cells; c++) {
    if (enclosed[c]) {
      moldWhite += cWhite[c];
      moldBlue += cBlue[c];
    }
  }

  return {
    width, height, gw, gh,
    total: width * height,
    fruit: counts[FRUIT],
    skin: counts[SKIN],
    glare: counts[GLARE],
    weights: { ripe: wRipe, yellow: wYellow, green: wGreen },
    moldWhite, moldBlue,
    enclosed,
  };
}

function moldRegions(stats) {
  const { enclosed, gw, gh } = stats;
  const seen = new Uint8Array(enclosed.length);
  const regions = [];
  for (let start = 0; start < enclosed.length; start++) {
    if (!enclosed[start] || seen[start]) continue;
    let minX = gw, minY = gh, maxX = -1, maxY = -1, size = 0;
    const stack = [start];
    seen[start] = 1;
    while (stack.length) {
      const c = stack.pop();
      const x = c % gw, y = (c - x) / gw;
      size++;
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;
      const next = [x > 0 ? c - 1 : -1, x < gw - 1 ? c + 1 : -1, y > 0 ? c - gw : -1, y < gh - 1 ? c + gw : -1];
      for (const n of next) {
        if (n >= 0 && enclosed[n] && !seen[n]) { seen[n] = 1; stack.push(n); }
      }
    }
    regions.push({ x: minX / gw, y: minY / gh, w: (maxX - minX + 1) / gw, h: (maxY - minY + 1) / gh, label: 'mold', size });
  }
  return regions.sort((a, b) => b.size - a.size).slice(0, 4).map(({ size, ...r }) => r);
}

/** Turn pixel statistics into a reading. */
export function scoreAnalysis(stats, T = THRESHOLDS) {
  const moldArea = stats.moldWhite + stats.moldBlue;
  const fruitArea = stats.fruit + moldArea;
  const coverage = stats.total ? fruitArea / stats.total : 0;

  let o = 0, y = 0, g = 0;
  if (stats.fruit) {
    o = stats.weights.ripe / stats.fruit;
    y = stats.weights.yellow / stats.fruit;
    g = stats.weights.green / stats.fruit;
  }
  // Green and orange on the same fruit is the ripening signal, so the smaller of the two shares
  // moves into "ripening" with extra weight.
  const mix = Math.min(g, o);
  const evidence = fruitArea ? (stats.moldWhite + T.mold.blueWeight * stats.moldBlue) / fruitArea : 0;
  const moldScore = smoothstep(T.mold.evidenceStart, T.mold.evidenceFull, evidence);
  const keep = 1 - moldScore;
  const scores = {
    unripe: (g - 0.75 * mix) * keep,
    ripening: (y + 1.5 * mix) * keep,
    ripe: (o - 0.75 * mix) * keep,
    mold: fruitArea ? moldScore : 0,
  };

  if (coverage < T.coverage.none) {
    return {
      label: 'none',
      confidence: 1 - coverage / T.coverage.none,
      scores,
      regions: [],
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
    regions: moldScore > 0 ? moldRegions(stats) : [],
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
    description: 'Colour-based estimate, a stand-in for the planned CNN.',
    async classify(source) {
      return classifyBuffer(toBuffer(source), thresholds);
    },
  };
}
