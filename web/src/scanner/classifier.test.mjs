// Run with: node src/scanner/classifier.test.mjs
import assert from 'node:assert/strict';
import { classifyBuffer, centerRoi, cropResize, confidenceLevel } from './classifier.js';
import { createSmoother } from './smoothing.js';
import { SAMPLES, renderSample } from './samples.js';

const SIZE = 128;

// Deterministic jitter so buffers look like sensor noise rather than flat fills.
let seed = 1;
const rand = () => ((seed = (Math.imul(seed, 1103515245) + 12345) >>> 0) / 4294967296);

function buffer(paint, size = SIZE) {
  seed = 1;
  const data = new Uint8ClampedArray(size * size * 4);
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const [r, g, b] = paint(x, y, size);
      const i = (y * size + x) * 4;
      const n = () => (rand() - 0.5) * 16;
      data[i] = r + n();
      data[i + 1] = g + n();
      data[i + 2] = b + n();
      data[i + 3] = 255;
    }
  }
  return { data, width: size, height: size };
}

const fill = (rgb) => () => rgb;
const inCircle = (x, y, cx, cy, r) => (x - cx) ** 2 + (y - cy) ** 2 < r * r;

const ORANGE = [240, 130, 15];
const GREEN = [95, 160, 50];
const WHITE_FUZZ = [232, 232, 222];
const BLUE_GREEN = [90, 150, 150];

const cases = [
  ['pure green', buffer(fill(GREEN)), 'unripe'],
  ['pale green', buffer(fill([150, 185, 80])), 'unripe'],
  ['yellow', buffer(fill([235, 205, 45])), 'ripening'],
  ['green and orange halves', buffer((x) => (x < SIZE * 0.45 ? GREEN : ORANGE)), 'ripening'],
  ['green-orange blotches', buffer((x, y) => ((Math.floor(x / 10) + Math.floor(y / 10)) % 2 ? [120, 170, 40] : [235, 150, 30])), 'ripening'],
  ['orange', buffer(fill(ORANGE)), 'ripe'],
  ['shaded orange', buffer(fill([165, 82, 28])), 'ripe'],
  ['orange with a clipped highlight', buffer((x, y) => (inCircle(x, y, 45, 40, 8) ? [255, 255, 255] : ORANGE)), 'ripe'],
  ['orange on a white table', buffer((x, y) => (inCircle(x, y, 64, 64, 54) ? ORANGE : [236, 234, 228])), 'ripe'],
  [
    'orange with white and blue-green patches',
    buffer((x, y) => {
      if (inCircle(x, y, 50, 55, 7) || inCircle(x, y, 82, 80, 5)) return BLUE_GREEN;
      if (inCircle(x, y, 50, 55, 16) || inCircle(x, y, 82, 80, 12)) return WHITE_FUZZ;
      return ORANGE;
    }),
    'mold',
  ],
  ['green with white fuzz', buffer((x, y) => (inCircle(x, y, 64, 64, 22) ? WHITE_FUZZ : GREEN)), 'mold'],
  ['grey background', buffer(fill([128, 128, 128])), 'none'],
  ['white wall', buffer(fill([235, 235, 230])), 'none'],
  ['light skin', buffer(fill([224, 172, 140])), 'none'],
  ['medium skin', buffer(fill([190, 130, 100])), 'none'],
  ['darker skin', buffer(fill([120, 80, 60])), 'none'],
  ['brown wood', buffer(fill([150, 100, 60])), 'none'],
  ['small orange far away', buffer((x, y) => (inCircle(x, y, 64, 64, 14) ? ORANGE : [120, 120, 125])), 'none'],
  ['dark room', buffer(fill([20, 18, 16])), 'none'],
];

let failed = 0;
function check(name, fn) {
  try {
    fn();
    console.log(`  ok   ${name}`);
  } catch (err) {
    failed++;
    console.log(`  FAIL ${name}\n       ${err.message}`);
  }
}

const fmt = (r) => `${r.label} (conf ${r.confidence.toFixed(2)}, cover ${r.coverage.toFixed(2)}; ` +
  Object.entries(r.scores).map(([k, v]) => `${k} ${v.toFixed(2)}`).join(', ') + ')';

console.log('Synthetic buffers');
for (const [name, buf, expected] of cases) {
  check(`${name} -> ${expected}`, () => {
    const r = classifyBuffer(buf);
    assert.equal(r.label, expected, `got ${fmt(r)}`);
    const sum = Object.values(r.scores).reduce((a, b) => a + b, 0);
    if (r.label !== 'none') assert.ok(Math.abs(sum - 1) < 0.02, `scores sum to ${sum}`);
    assert.ok(r.confidence >= 0 && r.confidence <= 1);
  });
}

check('mold reading returns regions inside the buffer', () => {
  const r = classifyBuffer(cases.find((c) => c[2] === 'mold')[1]);
  assert.ok(r.regions.length >= 1, 'no regions');
  for (const g of r.regions) assert.ok(g.x >= 0 && g.y >= 0 && g.x + g.w <= 1 && g.y + g.h <= 1);
});

check('a clean orange is high confidence', () => {
  assert.equal(confidenceLevel(classifyBuffer(cases.find((c) => c[0] === 'orange')[1]).confidence), 'high');
});

console.log('\nProcedural samples (centre square, 128 px)');
for (const s of SAMPLES) {
  check(`sample "${s.name}" -> ${s.expected}`, () => {
    const img = renderSample(s.id);
    const crop = cropResize(img, centerRoi(img.width, img.height), SIZE);
    const r = classifyBuffer(crop);
    assert.equal(r.label, s.expected, `got ${fmt(r)}`);
    console.log(`       ${fmt(r)}`);
  });
}

console.log('\nRegion of interest');
check('centre square of a 4:3 frame', () => assert.deepEqual(centerRoi(400, 300), { x: 110, y: 60, size: 180 }));
check('centre square of a 16:9 frame shown in 4:3', () => assert.deepEqual(centerRoi(1280, 720), { x: 424, y: 144, size: 432 }));
check('centre square of a portrait frame shown in 4:3', () => assert.deepEqual(centerRoi(720, 960), { x: 198, y: 318, size: 324 }));

console.log('\nSmoothing');
const ripe = { label: 'ripe', confidence: 0.9, scores: { unripe: 0, ripening: 0.1, ripe: 0.9, mold: 0 } };
const ripening = { label: 'ripening', confidence: 0.8, scores: { unripe: 0.1, ripening: 0.8, ripe: 0.1, mold: 0 } };
const none = { label: 'none', confidence: 1, scores: { unripe: 0, ripening: 0, ripe: 0, mold: 0 } };

check('single odd frames do not flip the label', () => {
  const sm = createSmoother();
  let t = 0, out;
  for (let i = 0; i < 12; i++) out = sm.update(i % 4 === 3 ? ripening : ripe, (t += 160));
  assert.equal(out.label, 'ripe');
});
check('a steady new reading takes over within about a second', () => {
  const sm = createSmoother();
  let t = 0, out, at = null;
  for (let i = 0; i < 6; i++) sm.update(ripe, (t += 160));
  for (let i = 1; i <= 10; i++) {
    out = sm.update(ripening, (t += 160));
    if (out.label === 'ripening' && at == null) at = i * 160;
  }
  assert.equal(out.label, 'ripening');
  assert.ok(at <= 1000, `switched after ${at} ms`);
});
check('one empty frame does not drop to none, a run of them does', () => {
  const sm = createSmoother();
  let t = 0;
  for (let i = 0; i < 6; i++) sm.update(ripe, (t += 160));
  assert.equal(sm.update(none, (t += 160)).label, 'ripe');
  let out;
  for (let i = 0; i < 6; i++) out = sm.update(none, (t += 160));
  assert.equal(out.label, 'none');
});
check('changed is true only when the label changes', () => {
  const sm = createSmoother();
  let t = 0;
  const flags = [];
  for (let i = 0; i < 5; i++) flags.push(sm.update(ripe, (t += 160)).changed);
  assert.deepEqual(flags, [true, false, false, false, false]);
});

console.log(failed ? `\n${failed} failed` : '\nAll passed');
process.exitCode = failed ? 1 : 0;
