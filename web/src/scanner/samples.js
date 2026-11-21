// Procedural sample images, so the demo works without a camera. Each one is rendered pixel by
// pixel into a plain RGBA buffer (no canvas needed), which keeps them testable in Node.
// Design space is 400 x 300; other sizes scale it.

export const SAMPLES = [
  { id: 'green', name: 'Green', expected: 'unripe' },
  { id: 'turning', name: 'Turning', expected: 'ripening' },
  { id: 'deep', name: 'Deep orange', expected: 'ripe' },
  { id: 'crate', name: 'Empty crate', expected: 'none' },
];

export const SAMPLE_WIDTH = 400;
export const SAMPLE_HEIGHT = 300;

function hash(x, y, seed) {
  let h = (Math.imul(x, 374761393) + Math.imul(y, 668265263) + Math.imul(seed, 1442695041)) | 0;
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  h ^= h >>> 16;
  return (h >>> 0) / 4294967296;
}

function noise(x, y, seed) {
  const xi = Math.floor(x), yi = Math.floor(y);
  const xf = x - xi, yf = y - yi;
  const u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf);
  const a = hash(xi, yi, seed), b = hash(xi + 1, yi, seed);
  const c = hash(xi, yi + 1, seed), d = hash(xi + 1, yi + 1, seed);
  return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v;
}

function fbm(x, y, seed, octaves = 3) {
  let sum = 0, amp = 0.5, freq = 1, norm = 0;
  for (let i = 0; i < octaves; i++) {
    sum += amp * noise(x * freq, y * freq, seed + i * 17);
    norm += amp;
    amp *= 0.5;
    freq *= 2;
  }
  return sum / norm;
}

const clamp01 = (x) => (x < 0 ? 0 : x > 1 ? 1 : x);
const lerp = (a, b, t) => a + (b - a) * t;
const smoothstep = (a, b, x) => {
  const t = clamp01((x - a) / (b - a));
  return t * t * (3 - 2 * t);
};

function hsv(h, s, v) {
  h = ((h % 360) + 360) % 360;
  s = clamp01(s);
  v = clamp01(v);
  const c = v * s, x = c * (1 - Math.abs(((h / 60) % 2) - 1)), m = v - c;
  let r, g, b;
  if (h < 60) [r, g, b] = [c, x, 0];
  else if (h < 120) [r, g, b] = [x, c, 0];
  else if (h < 180) [r, g, b] = [0, c, x];
  else if (h < 240) [r, g, b] = [0, x, c];
  else if (h < 300) [r, g, b] = [x, 0, c];
  else [r, g, b] = [c, 0, x];
  return [(r + m) * 255, (g + m) * 255, (b + m) * 255];
}

const mix = (p, q, t) => [lerp(p[0], q[0], t), lerp(p[1], q[1], t), lerp(p[2], q[2], t)];

// Light from the upper left, towards the viewer.
const L = (() => {
  const v = [-0.5, -0.6, 0.62];
  const n = Math.hypot(...v);
  return v.map((c) => c / n);
})();
const HALF = (() => {
  const v = [L[0], L[1], L[2] + 1];
  const n = Math.hypot(...v);
  return v.map((c) => c / n);
})();

const FRUIT = { cx: 200, cy: 160, rx: 122, ry: 117 };

const PEELS = {
  green: (px, py) => ({ h: 86 + (fbm(px / 22, py / 22, 5) - 0.5) * 10, s: 0.6, v: 0.8 }),
  turning: (px, py, nx, ny) => {
    // Green near the stem, turning orange towards the bottom, with uneven blotches.
    const t = smoothstep(-0.55, 0.55, ny * 0.9 + nx * 0.25 + (fbm(px / 35, py / 35, 9) - 0.5) * 1.1);
    return { h: lerp(80, 33, t), s: lerp(0.6, 0.85, t), v: lerp(0.8, 0.9, t) };
  },
  deep: (px, py) => ({ h: 26 + (fbm(px / 22, py / 22, 5) - 0.5) * 5, s: 0.9, v: 0.93 }),
};

function groveBackground(px, py) {
  if (py < 222 + (noise(px / 30, 0, 2) - 0.5) * 4) {
    // Dark foliage with soft light coming through.
    const f = fbm(px / 40, py / 40, 11);
    const spot = smoothstep(0.62, 0.8, fbm(px / 25, py / 25, 13));
    return mix(hsv(110, 0.42, 0.06 + 0.13 * f), hsv(80, 0.18, 0.5), spot * 0.6);
  }
  // Pale linen tabletop with a soft shadow under the fruit.
  const grain = fbm(px / 3, py / 40, 15, 2);
  const sd = Math.hypot((px - 214) / 130, (py - 282) / 22);
  const shadow = 1 - 0.45 * (1 - smoothstep(0.4, 1.1, sd));
  return hsv(40, 0.08, (0.74 + 0.08 * grain) * shadow);
}

function leafColor(px, py) {
  // A leaf attached at the stem, pointing up and to the right (outside the analysed square).
  const ang = -0.38, cos = Math.cos(ang), sin = Math.sin(ang);
  const dx = px - 262, dy = py - 30;
  const u = dx * cos - dy * sin, v = dx * sin + dy * cos;
  const a = 62, b = 17;
  const half = b * (1 - (u / a) ** 2);
  if (Math.abs(u) > a || Math.abs(v) > half) return null;
  const edge = clamp01((half - Math.abs(v)) / 1.5);
  const vein = Math.abs(v) < 1.2 ? 1 : 0;
  const light = 0.3 + 0.1 * (1 - v / b) + 0.05 * fbm(px / 6, py / 6, 19);
  return { rgb: vein ? hsv(95, 0.4, 0.45) : hsv(108, 0.62, light), alpha: edge };
}

function orangeScene(kind, px, py) {
  let color = groveBackground(px, py);
  const nx = (px - FRUIT.cx) / FRUIT.rx, ny = (py - FRUIT.cy) / FRUIT.ry;
  const d2 = nx * nx + ny * ny;
  if (d2 < 1.03) {
    const d = Math.sqrt(d2);
    const alpha = clamp01((1 - d) * FRUIT.rx / 1.5 + 0.5);
    const nz = Math.sqrt(Math.max(0, 1 - d2));
    const lambert = Math.max(0, nx * L[0] + ny * L[1] + nz * L[2]);
    const shade = Math.min(1.08, 0.28 + 0.8 * lambert);
    const pores = noise(px / 1.7, py / 1.7, 3);
    const { h, s, v } = PEELS[kind](px, py, nx, ny);
    const rgb = hsv(h, s, v * shade * (0.94 + 0.12 * pores));
    const spec = Math.pow(Math.max(0, nx * HALF[0] + ny * HALF[1] + nz * HALF[2]), 45) * 0.55 * (0.7 + 0.3 * pores);
    color = mix(color, mix(rgb, [255, 255, 255], spec), alpha);
  }
  // Calyx at the stem.
  const sd = Math.hypot(px - 204, py - (FRUIT.cy - FRUIT.ry + 6));
  if (sd < 8) color = mix(color, hsv(65, 0.55, 0.3 + 0.06 * noise(px, py, 7)), clamp01(8 - sd));
  const leaf = leafColor(px, py);
  if (leaf) color = mix(color, leaf.rgb, leaf.alpha);
  return color;
}

function crateScene(px, py) {
  // Grey concrete floor.
  let color = hsv(30, 0.04, 0.42 + 0.14 * fbm(px / 30, py / 30, 51) + 0.04 * (hash(px | 0, py | 0, 3) - 0.5));
  if (px >= 58 && px <= 342 && py >= 66 && py <= 252) {
    const post = px < 76 || px > 324;
    const board = Math.floor((py - 66) / 47);
    const within = (py - 66) - board * 47;
    if (!post && within > 40) return hsv(30, 0.3, 0.13); // gap between slats, dark interior
    const grain = fbm(px / 70, py / 3, 53 + board, 3);
    color = hsv(34, 0.22 + 0.06 * grain, (post ? 0.58 : 0.7) + 0.12 * grain);
    const knot = Math.hypot((px - 250) / 9, (py - 140) / 5);
    if (knot < 1) color = mix(color, hsv(25, 0.4, 0.35), 1 - knot);
  }
  // Soft shadow along the bottom of the crate.
  if (py > 252 && py < 270 && px > 50 && px < 350) color = mix(color, [0, 0, 0], 0.25 * (1 - (py - 252) / 18));
  return color;
}

/** Render a sample by id into { data, width, height } (RGBA). */
export function renderSample(id, width = SAMPLE_WIDTH, height = SAMPLE_HEIGHT) {
  if (!SAMPLES.some((s) => s.id === id)) throw new Error(`Unknown sample "${id}"`);
  const data = new Uint8ClampedArray(width * height * 4);
  const scale = SAMPLE_HEIGHT / height;
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const px = (x + 0.5) * scale, py = (y + 0.5) * scale;
      const c = id === 'crate' ? crateScene(px, py) : orangeScene(id, px, py);
      const i = (y * width + x) * 4;
      data[i] = c[0];
      data[i + 1] = c[1];
      data[i + 2] = c[2];
      data[i + 3] = 255;
    }
  }
  return { data, width, height };
}
