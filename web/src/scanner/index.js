// CutieFarm live scanner. Contract (see web/PRODUCT.md):
//   mountScanner(rootEl, options?) -> { destroy() }
//   dispatches 'cutiefarm:reading' on rootEl with { label, confidence, scores, source }
// options.classifier swaps the colour heuristic for any object with async classify(source).
import './scanner.css';
import { createColorClassifier, confidenceLevel, centerRoi, VIEW_ASPECT, LABELS } from './classifier.js';
import { createSmoother } from './smoothing.js';
import { getCameraSupport, queryCameraPermission, openCamera, describeCameraError, stopStream } from './camera.js';
import { SAMPLES, SAMPLE_WIDTH, SAMPLE_HEIGHT, renderSample } from './samples.js';

const ANALYSIS_SIZE = 128;
const FRAME_INTERVAL_MS = 160; // about six readings a second
const ANNOUNCE_DELAY_MS = 600;

const STATE_TEXT = {
  unripe: { title: 'Unripe', advice: 'Leave it on the tree.' },
  ripening: { title: 'Ripening', advice: 'Check again in a few days.' },
  ripe: { title: 'Ready to pick', advice: 'Harvest it.' },
  mold: { title: 'Possible mold', advice: 'Remove it before the mold spreads.' },
  none: { title: 'No orange in the frame', advice: '' },
};
const CONFIDENCE_TEXT = { high: 'High confidence', medium: 'Medium confidence', low: 'Low confidence' };

const PANELS = {
  idle: {
    title: 'Start the camera and hold up an orange, or pick a sample orange.',
    body: 'Frames stay on this device.',
    actions: ['start', 'samples'],
  },
  starting: { title: 'Starting the camera…', actions: ['samples'] },
  pending: { title: 'Allow camera access in the browser prompt.', actions: ['samples'] },
  insecure: {
    title: 'The camera needs a secure page.',
    body: 'Open this site over HTTPS or on localhost to use it. The samples work here.',
    actions: ['samples'],
  },
  unsupported: {
    title: 'This browser can’t open a camera.',
    body: 'Try a current version of Chrome, Edge, Firefox or Safari, or use the samples.',
    actions: ['samples'],
  },
  denied: {
    title: 'Camera access is blocked.',
    body: 'Click the camera or lock icon in the address bar, allow the camera for this site, then try again.',
    actions: ['retry', 'samples'],
  },
  blocked: {
    title: 'This page isn’t allowed to use the camera.',
    body: 'The page embedding the scanner blocks camera access. The samples still work.',
    actions: ['samples'],
  },
  notfound: { title: 'No camera found.', body: 'Connect a camera and try again, or use the samples.', actions: ['retry', 'samples'] },
  busy: {
    title: 'The camera is in use by another app.',
    body: 'Close the other app, then try again.',
    actions: ['retry', 'samples'],
  },
  ended: {
    title: 'The camera stopped.',
    body: 'It may have been disconnected or taken by another app.',
    actions: ['retry', 'samples'],
  },
  error: { title: 'The camera couldn’t start.', body: (err) => (err && err.name ? `Error: ${err.name}.` : ''), actions: ['retry', 'samples'] },
  classifier: { title: 'The reading failed.', body: (err) => (err && err.message) || '', actions: ['retry', 'samples'] },
};

const CAMERA_NOTE = {
  insecure: 'Camera needs HTTPS or localhost.',
  unsupported: 'No camera support in this browser.',
  blocked: 'This page blocks the camera.',
};

const mounted = new WeakMap();
let instanceCount = 0;

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (v == null || v === false) continue;
    if (k === 'class') node.className = v;
    else if (k === 'text') node.textContent = v;
    else if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v === true ? '' : String(v));
  }
  for (const c of children.flat()) if (c != null && c !== false) node.append(c);
  return node;
}

const round2 = (x) => Math.round(x * 100) / 100;

export function mountScanner(rootEl, options = {}) {
  if (!(rootEl instanceof Element)) throw new TypeError('mountScanner(rootEl) needs a DOM element');
  mounted.get(rootEl)?.destroy();

  const classifier = options.classifier ?? createColorClassifier();
  const uid = `cf-scanner-${++instanceCount}`;
  const support = getCameraSupport();
  const smoother = createSmoother();

  let mode = 'idle'; // idle | starting | camera | samples | error
  let stream = null;
  let track = null;
  let cameraGen = 0;
  let sampleGen = 0;
  let selectedSample = null;
  let frameHandle = null;
  let lastAnalysis = -Infinity;
  let busy = false;
  let visible = true;
  let destroyed = false;
  let lastEmit = null;
  let announceTimer = null;
  let cameraUnavailable = support.ok ? null : support.reason;
  const sampleCache = new Map();
  const timers = new Set();

  // ---- DOM ---------------------------------------------------------------------------------
  const video = el('video', { class: 'cf-scanner__frame', 'aria-label': 'Camera preview', hidden: true });
  video.muted = true;
  video.playsInline = true;
  const sampleCanvas = el('canvas', { class: 'cf-scanner__frame', width: SAMPLE_WIDTH, height: SAMPLE_HEIGHT, role: 'img', hidden: true });
  const regionsLayer = el('div', { class: 'cf-scanner__regions' });
  const guide = el(
    'div',
    { class: 'cf-scanner__guide', 'aria-hidden': 'true', hidden: true },
    ['tl', 'tr', 'bl', 'br'].map((c) => el('span', { class: `cf-scanner__corner cf-scanner__corner--${c}` })),
    regionsLayer,
  );
  const media = el('div', { class: 'cf-scanner__media' }, video, sampleCanvas, guide);

  const panelTitle = el('p', { class: 'cf-scanner__panel-title', id: `${uid}-panel`, tabindex: '-1' });
  const panelBody = el('p', { class: 'cf-scanner__panel-body' });
  const panelActions = el('div', { class: 'cf-scanner__actions' });
  const panel = el('div', { class: 'cf-scanner__panel', role: 'group', 'aria-labelledby': panelTitle.id }, panelTitle, panelBody, panelActions);
  const stage = el('div', { class: 'cf-scanner__stage' }, media, panel);

  const button = (text, onclick, variant = 'secondary') =>
    el('button', { type: 'button', class: `cf-scanner__btn cf-scanner__btn--${variant}`, text, onclick });

  const stopBtn = button('Stop camera', () => stopCamera());
  const toSamplesBtn = button('Use sample oranges', () => enterSamples(null, true));
  const cameraBar = el('div', { class: 'cf-scanner__bar' }, stopBtn, toSamplesBtn);

  const radios = new Map();
  const thumbs = new Map();
  const picker = el(
    'fieldset',
    { class: 'cf-scanner__picker' },
    el('legend', { class: 'cf-scanner__legend', text: 'Sample images' }),
    el(
      'div',
      { class: 'cf-scanner__options' },
      SAMPLES.map((s) => {
        const input = el('input', { type: 'radio', name: `${uid}-sample`, value: s.id, class: 'cf-scanner__radio', onchange: onSampleChange });
        const thumb = el('span', { class: 'cf-scanner__thumb', 'aria-hidden': 'true' });
        radios.set(s.id, input);
        thumbs.set(s.id, thumb);
        return el('label', { class: 'cf-scanner__option' }, input, thumb, el('span', { class: 'cf-scanner__option-name', text: s.name }));
      }),
    ),
  );
  const startFromSamplesBtn = button('Start camera', () => startCamera());
  const cameraNote = el('p', { class: 'cf-scanner__note' });
  const sampleBar = el('div', { class: 'cf-scanner__bar cf-scanner__bar--samples' }, picker, el('div', { class: 'cf-scanner__bar-end' }, startFromSamplesBtn, cameraNote));
  const controls = el('div', { class: 'cf-scanner__controls' }, cameraBar, sampleBar);

  const swatch = el('span', { class: 'cf-scanner__swatch', 'aria-hidden': 'true' });
  const titleText = el('span');
  const resultTitle = el('p', { class: 'cf-scanner__title' }, swatch, titleText);
  const resultMeta = el('p', { class: 'cf-scanner__meta' });
  const resultAdvice = el('p', { class: 'cf-scanner__advice' });
  const scoreRows = new Map();
  const scores = el(
    'ul',
    { class: 'cf-scanner__scores', 'aria-label': 'Scores' },
    LABELS.map((k) => {
      const fill = el('span', { class: 'cf-scanner__fill' });
      const value = el('span', { class: 'cf-scanner__sr' });
      const row = el(
        'li',
        { class: 'cf-scanner__score', 'data-label': k },
        el('span', { class: 'cf-scanner__score-name', text: STATE_TEXT[k].title }),
        value,
        el('span', { class: 'cf-scanner__track', 'aria-hidden': 'true' }, fill),
      );
      scoreRows.set(k, { row, fill, value });
      return row;
    }),
  );
  const result = el(
    'div',
    { class: 'cf-scanner__result', role: 'group', 'aria-label': 'Reading' },
    el('div', { class: 'cf-scanner__summary' }, resultTitle, resultMeta, resultAdvice),
    scores,
    classifier.description ? el('p', { class: 'cf-scanner__note', text: classifier.description }) : null,
  );
  const live = el('p', { class: 'cf-scanner__sr', 'aria-live': 'polite', 'aria-atomic': 'true' });

  const container = el(
    'div',
    { class: 'cf-scanner' },
    el('div', { class: 'cf-scanner__layout' }, el('div', { class: 'cf-scanner__viewer' }, stage, controls), result),
    live,
  );
  rootEl.append(container);

  const analysisCanvas = document.createElement('canvas');
  analysisCanvas.width = analysisCanvas.height = ANALYSIS_SIZE;
  const analysisCtx = analysisCanvas.getContext('2d', { willReadFrequently: true });

  // ---- View --------------------------------------------------------------------------------
  function isShown(node) {
    return node.isConnected && node.getClientRects().length > 0 && getComputedStyle(node).visibility !== 'hidden';
  }

  /** Run a DOM update; if it removed or hid the focused element, move focus to `target`. */
  function update(fn, target) {
    const had = container.contains(document.activeElement);
    fn();
    const active = document.activeElement;
    if (had && target && (!container.contains(active) || !isShown(active))) {
      (typeof target === 'function' ? target() : target)?.focus({ preventScroll: true });
    }
  }

  function applyMode() {
    container.dataset.mode = mode;
    video.hidden = mode !== 'camera';
    sampleCanvas.hidden = mode !== 'samples';
    guide.hidden = mode !== 'camera' && mode !== 'samples';
    // Both bars share one grid cell, so switching between them never changes the height.
    cameraBar.classList.toggle('is-active', mode === 'camera');
    sampleBar.classList.toggle('is-active', mode !== 'camera');
    startFromSamplesBtn.hidden = !(mode === 'samples' && !cameraUnavailable);
    cameraNote.hidden = !(mode === 'samples' && cameraUnavailable);
    cameraNote.textContent = CAMERA_NOTE[cameraUnavailable] || '';
    if (mode !== 'samples') for (const r of radios.values()) r.checked = false;
  }

  function showPanel(name, detail) {
    const spec = name && PANELS[name];
    panel.hidden = !spec;
    container.dataset.panel = name || '';
    if (!spec) return;
    panelTitle.textContent = spec.title;
    panelBody.textContent = typeof spec.body === 'function' ? spec.body(detail) : spec.body || '';
    panelBody.hidden = !panelBody.textContent;
    const onlySamples = spec.actions.length === 1 && spec.actions[0] === 'samples';
    panelActions.replaceChildren(
      ...spec.actions.map((a) => {
        if (a === 'start') return button('Start camera', () => startCamera(), 'primary');
        if (a === 'retry') return button('Try again', () => startCamera(), 'primary');
        return button(name === 'starting' || name === 'pending' ? 'Use sample oranges instead' : 'Use sample oranges', () => enterSamples(null, true), onlySamples && name !== 'starting' && name !== 'pending' ? 'primary' : 'secondary');
      }),
    );
  }

  const panelFocus = () => panelActions.querySelector('button') || panelTitle;

  function announce(text, { delay = 0 } = {}) {
    clearTimeout(announceTimer);
    announceTimer = setTimeout(() => {
      live.textContent = '';
      // A fresh text node after clearing makes screen readers repeat identical messages.
      requestAnimationFrame(() => { if (!destroyed) live.textContent = text; });
    }, delay);
  }

  function renderReading(r, source) {
    const label = r ? r.label : null;
    result.dataset.label = label || 'empty';
    if (!r) {
      titleText.textContent = 'No reading yet';
      resultMeta.textContent = '';
      resultAdvice.textContent = 'Start the camera or pick a sample.';
    } else if (label === 'none') {
      titleText.textContent = STATE_TEXT.none.title;
      resultMeta.textContent = '';
      resultAdvice.textContent = source === 'camera' ? 'Hold an orange inside the square.' : 'Nothing in the square reads as orange peel.';
    } else {
      const level = confidenceLevel(r.confidence);
      titleText.textContent = STATE_TEXT[label].title;
      resultMeta.textContent = level === 'low' && source === 'camera'
        ? 'Low confidence. Fill the square with the orange and use even light.'
        : CONFIDENCE_TEXT[level];
      resultAdvice.textContent = STATE_TEXT[label].advice;
    }
    for (const k of LABELS) {
      const { row, fill, value } = scoreRows.get(k);
      const v = r && label !== 'none' ? Math.max(0, Math.min(1, r.scores[k] || 0)) : 0;
      fill.style.transform = `scaleX(${v})`;
      row.toggleAttribute('data-active', k === label);
      value.textContent = r && label !== 'none' ? `, about ${Math.round(v * 10) * 10} percent` : '';
    }
    regionsLayer.replaceChildren(
      ...(label === 'mold' && r.regions ? r.regions : []).map((g) => {
        const box = el('span', { class: 'cf-scanner__region' });
        Object.assign(box.style, { left: `${g.x * 100}%`, top: `${g.y * 100}%`, width: `${g.w * 100}%`, height: `${g.h * 100}%` });
        return box;
      }),
    );
  }

  function spoken(r) {
    if (r.label === 'none') return STATE_TEXT.none.title;
    return `${STATE_TEXT[r.label].title}, ${CONFIDENCE_TEXT[confidenceLevel(r.confidence)].toLowerCase()}`;
  }

  function emit(r, source) {
    const level = r.label === 'none' ? 'none' : confidenceLevel(r.confidence);
    const now = performance.now();
    if (source === 'camera' && lastEmit && lastEmit.source === 'camera' && lastEmit.label === r.label) {
      // Same label: only report a change of confidence level, and not more than every 600 ms.
      if (lastEmit.level === level || now - lastEmit.t < 600) return;
    }
    lastEmit = { label: r.label, level, source, t: now };
    const scoresOut = {};
    for (const k of LABELS) scoresOut[k] = round2(r.scores[k] || 0);
    rootEl.dispatchEvent(
      new CustomEvent('cutiefarm:reading', {
        bubbles: true,
        detail: { label: r.label, confidence: round2(r.confidence), scores: scoresOut, source },
      }),
    );
  }

  // ---- Camera ------------------------------------------------------------------------------
  function shouldRun() {
    return !destroyed && mode === 'camera' && visible && !document.hidden && stream && video.readyState >= 2;
  }

  function scheduleFrame() {
    if (frameHandle || !shouldRun()) return;
    if (typeof video.requestVideoFrameCallback === 'function') {
      frameHandle = { vfc: true, id: video.requestVideoFrameCallback(onFrame) };
    } else {
      frameHandle = { vfc: false, id: requestAnimationFrame(onFrame) };
    }
  }

  function cancelFrame() {
    if (!frameHandle) return;
    if (frameHandle.vfc) video.cancelVideoFrameCallback(frameHandle.id);
    else cancelAnimationFrame(frameHandle.id);
    frameHandle = null;
  }

  function onFrame(now) {
    frameHandle = null;
    if (!shouldRun()) return;
    if (!busy && now - lastAnalysis >= FRAME_INTERVAL_MS) {
      lastAnalysis = now;
      analyzeFrame();
    }
    scheduleFrame();
  }

  async function analyzeFrame() {
    const w = video.videoWidth, h = video.videoHeight;
    if (!w || !h) return;
    const gen = cameraGen;
    busy = true;
    let r;
    try {
      const roi = centerRoi(w, h, VIEW_ASPECT);
      analysisCtx.drawImage(video, roi.x, roi.y, roi.size, roi.size, 0, 0, ANALYSIS_SIZE, ANALYSIS_SIZE);
      r = await classifier.classify(analysisCtx.getImageData(0, 0, ANALYSIS_SIZE, ANALYSIS_SIZE));
    } catch (err) {
      busy = false;
      if (gen !== cameraGen || destroyed) return;
      console.error('[cutiefarm scanner] classify failed', err);
      failWith('classifier', err);
      return;
    }
    busy = false;
    if (gen !== cameraGen || destroyed || mode !== 'camera') return;
    const s = smoother.update(r, performance.now());
    renderReading(s, 'camera');
    emit(s, 'camera');
    if (s.changed) announce(spoken(s), { delay: ANNOUNCE_DELAY_MS });
  }

  function releaseCamera() {
    cameraGen++;
    cancelFrame();
    if (track) track.removeEventListener('ended', onTrackEnded);
    stopStream(stream);
    stream = null;
    track = null;
    video.removeEventListener('loadeddata', scheduleFrame);
    video.srcObject = null;
    busy = false;
  }

  function failWith(panelName, detail) {
    releaseCamera();
    update(() => {
      mode = 'error';
      renderReading(null);
      applyMode();
      showPanel(panelName, detail);
    }, panelFocus);
    announce(`${PANELS[panelName].title} ${panelBody.textContent}`.trim());
  }

  function onTrackEnded() {
    if (!destroyed) failWith('ended');
  }

  async function startCamera() {
    if (destroyed) return;
    if (!support.ok) {
      update(() => { mode = 'error'; applyMode(); showPanel(support.reason); }, panelFocus);
      return;
    }
    releaseCamera();
    const gen = cameraGen;
    sampleGen++;
    update(() => {
      mode = 'starting';
      renderReading(null);
      applyMode();
      showPanel('starting');
    }, panelTitle);

    const permission = await queryCameraPermission();
    if (gen !== cameraGen || destroyed) return;
    if (permission === 'prompt') {
      update(() => showPanel('pending'), panelTitle);
      announce(PANELS.pending.title);
    }

    let s;
    try {
      s = await openCamera();
    } catch (err) {
      if (gen !== cameraGen || destroyed) return;
      const kind = describeCameraError(err);
      if (kind === 'blocked') cameraUnavailable = 'blocked';
      failWith(kind, err);
      return;
    }
    if (gen !== cameraGen || destroyed) {
      stopStream(s);
      return;
    }
    stream = s;
    track = s.getVideoTracks()[0] || null;
    if (track) track.addEventListener('ended', onTrackEnded);
    video.srcObject = s;
    video.addEventListener('loadeddata', scheduleFrame);
    try {
      await video.play();
    } catch (err) {
      if (gen !== cameraGen || destroyed) return;
      if (err && err.name !== 'AbortError') console.warn('[cutiefarm scanner] video.play()', err);
    }
    if (gen !== cameraGen || destroyed) return;

    // Mirror front cameras like a mirror, so moving the orange left moves it left on screen.
    // Rear cameras show the scene as it is. The analysis square is centred, so mirroring
    // never changes what is analysed.
    const facing = track && track.getSettings ? track.getSettings().facingMode : undefined;
    media.classList.toggle('is-mirrored', facing !== 'environment');

    smoother.reset();
    lastEmit = null;
    update(() => {
      mode = 'camera';
      applyMode();
      showPanel(null);
    }, stopBtn);
    announce('Camera on. Hold an orange inside the square.');
    scheduleFrame();
  }

  function stopCamera() {
    releaseCamera();
    update(() => {
      mode = 'idle';
      renderReading(null);
      applyMode();
      showPanel(support.ok ? 'idle' : support.reason);
    }, panelFocus);
    announce('Camera off.');
  }

  // ---- Samples -----------------------------------------------------------------------------
  function sampleImage(id) {
    let canvas = sampleCache.get(id);
    if (!canvas) {
      const img = renderSample(id, SAMPLE_WIDTH, SAMPLE_HEIGHT);
      canvas = document.createElement('canvas');
      canvas.width = img.width;
      canvas.height = img.height;
      canvas.getContext('2d').putImageData(new ImageData(img.data, img.width, img.height), 0, 0);
      sampleCache.set(id, canvas);
    }
    return canvas;
  }

  function drawThumb(id) {
    const thumb = thumbs.get(id);
    if (thumb.firstChild) return;
    const c = document.createElement('canvas');
    c.width = 120;
    c.height = 90;
    c.getContext('2d').drawImage(sampleImage(id), 0, 0, 120, 90);
    thumb.append(c);
  }

  // Render the samples one per task after mount, so the page never blocks on them.
  SAMPLES.forEach((s, i) => {
    const t = setTimeout(() => {
      timers.delete(t);
      if (!destroyed) drawThumb(s.id);
    }, 50 + i * 30);
    timers.add(t);
  });

  function enterSamples(id, focusPicker = false) {
    if (destroyed) return;
    if (mode === 'camera' || mode === 'starting') releaseCamera();
    const target = id || selectedSample || SAMPLES[0].id;
    update(() => {
      mode = 'samples';
      applyMode();
      showPanel(null);
      radios.get(target).checked = true;
    }, () => radios.get(target));
    if (focusPicker) radios.get(target).focus({ preventScroll: true });
    selectSample(target);
  }

  function onSampleChange(e) {
    if (!e.target.checked) return;
    if (mode !== 'samples') enterSamples(e.target.value);
    else selectSample(e.target.value);
  }

  async function selectSample(id) {
    selectedSample = id;
    const gen = ++sampleGen;
    const meta = SAMPLES.find((s) => s.id === id);
    const src = sampleImage(id);
    drawThumb(id);
    sampleCanvas.getContext('2d').drawImage(src, 0, 0);
    sampleCanvas.setAttribute('aria-label', `Sample image: ${meta.name}`);
    const roi = centerRoi(src.width, src.height, VIEW_ASPECT);
    analysisCtx.drawImage(src, roi.x, roi.y, roi.size, roi.size, 0, 0, ANALYSIS_SIZE, ANALYSIS_SIZE);
    let r;
    try {
      r = await classifier.classify(analysisCtx.getImageData(0, 0, ANALYSIS_SIZE, ANALYSIS_SIZE));
    } catch (err) {
      if (gen !== sampleGen || destroyed) return;
      console.error('[cutiefarm scanner] classify failed', err);
      failWith('classifier', err);
      return;
    }
    if (gen !== sampleGen || destroyed || mode !== 'samples') return;
    renderReading(r, 'sample');
    emit(r, 'sample');
    announce(spoken(r));
  }

  // ---- Lifecycle ---------------------------------------------------------------------------
  const onVisibility = () => (document.hidden ? cancelFrame() : scheduleFrame());
  const onPageHide = () => { if (stream) stopCamera(); };
  document.addEventListener('visibilitychange', onVisibility);
  window.addEventListener('pagehide', onPageHide);

  let observer = null;
  if (typeof IntersectionObserver === 'function') {
    observer = new IntersectionObserver((entries) => {
      visible = entries[entries.length - 1].isIntersecting;
      if (visible) scheduleFrame();
      else cancelFrame();
    });
    observer.observe(container);
  }

  renderReading(null);
  applyMode();
  showPanel(support.ok ? 'idle' : support.reason);

  function destroy() {
    if (destroyed) return;
    destroyed = true;
    releaseCamera();
    sampleGen++;
    clearTimeout(announceTimer);
    for (const t of timers) clearTimeout(t);
    timers.clear();
    observer?.disconnect();
    document.removeEventListener('visibilitychange', onVisibility);
    window.removeEventListener('pagehide', onPageHide);
    sampleCache.clear();
    container.remove();
    if (mounted.get(rootEl) === api) mounted.delete(rootEl);
  }

  const api = { destroy };
  mounted.set(rootEl, api);
  return api;
}
