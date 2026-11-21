# CutieFarm — product brief (v1 landing)

Working name: **CutieFarm** (provisional; keep it easy to rename: one place in the HTML title/header/footer).

## What it is

A hackathon prototype (Cutiehacks) of an automated orange grove, in the spirit of an "automated farm" from sandbox games: the grove watches itself and tells you when to act. A camera looks at the oranges, a small vision model runs **locally**, and each orange gets a state:

| State | Visual cue | What the grower does |
|---|---|---|
| Unripe | mostly green peel | wait |
| Ripening | green turning yellow/orange | check again in a few days |
| Ready to pick | even, deep orange peel | harvest |
| Possible mold | white fuzz or blue-green patches (citrus green/blue mold) | remove it before it spreads |

## Pipeline (what is true today vs. planned)

- Hardware: the sensor board is an **Arduino** for now. The team started on an STM32 Nucleo (STM32L476, UART test firmware in `/embedded`), but it was not working, so they switched. They may move back to the STM32 later if time allows. On the page, call it "an Arduino" or "a microcontroller board". Do not mention the STM32.
- Plan: the CNN is **trained on one of the team's laptops**. A **laptop webcam** then runs it locally to classify ripeness and mold. The **Arduino board reads the grove's sensors**: a soil sensor (being wired up now), wind, temperature and humidity. It does not train or run the model. Today the firmware in `/embedded` is only a UART test, so present the sensors as being connected, not as live data. **Future** (mention at most once, as "next", without detail): the board will trigger irrigation and a picking arm. Keep sentences about the board in one place so they are easy to edit.
- v1 of this site ships a **colour-heuristic scanner in the browser** (HSV analysis of webcam frames). It is a stand-in for the CNN, and the page must say so plainly. The classifier sits behind an interface so the real model (TF.js / ONNX Runtime Web) can replace it later.
- Frames never leave the device. No upload, no backend. This is a true claim for v1 and worth stating.

## Outcome: the daily message (planned, approved by the team)

The point of the system is a decision for the grower. Every morning at **9:00** a **Telegram bot** sends a short status of their oranges, based on the vision model's results. Example: "3 ready to pick, 5 ripening, 1 possible mold (photo attached): remove it today." Once the Arduino sensors work, it will add a line with soil, humidity and temperature. There will be a `/status` command to get the message on demand, for demos. Later, the grower may be able to reply with questions, but do not feature that.

**Irrigation advice** (planned, approved by the team): from the soil moisture, temperature, humidity and wind readings, plus a weather forecast, the message also says how often to water (for example twice a week, weekly, every two weeks, or hold off) and when the next watering is due. Soil moisture comes first; the forecast and the other sensors set the cadence. It is a rule of thumb, not agronomic certainty. Example line: "Water on Thursday. Hot, dry week ahead, so twice a week for now." Automatic valves come later.

- Status: planned and **not built yet**. Any message shown on the page is labelled as an example. No fake phone UI that pretends to be live.
- Privacy wording: the image analysis runs on the device. Only the summary (and a photo of a fruit flagged for mold) is sent through Telegram. The in-browser demo sends nothing at all.

Do **not** invent numbers (accuracy, yield, acres, users, latency, cost savings), testimonials, partner logos or press. If a claim is not in this file, leave it out.

## Audience and job

- Primary: hackathon judges and visitors, on a laptop, often in a bright hall, with ~60 seconds of attention. They should understand the idea, then **try the scanner with their own camera** (or with sample images if they have no camera or say no).
- Secondary: small growers, later.
- Surface mode: **Persuade**, with one live, working demo as the proof.
- Language: **English**.

## Constraints

- Stack: Vite + vanilla HTML/CSS/JS in `/web`. No framework. Structured so it can later move to Next.js/React without rewriting the scanner (the scanner is a framework-agnostic ES module).
- Must work at phone width (16px side gutters, no horizontal scroll), keyboard accessible, `prefers-reduced-motion` respected, good contrast.
- Do not copy the name, characters, textures, fonts, sounds or look of any existing game (no Minecraft name, blocks textures or UI). The "automated farm" idea is the inspiration, not a visual reference to reproduce.
- External resources: Google Fonts allowed; everything else local. No trackers.

## Interface contract between page and scanner

Files:
- Page owner: `index.html`, `src/main.js`, `src/styles.css`, any `public/` page assets.
- Scanner owner: everything under `src/scanner/` (its own `scanner.css` is imported by `src/scanner/index.js`).

Mounting: `index.html` contains `<div id="scanner-root"></div>` inside the demo section. `src/main.js` does:

```js
import './styles.css';
import { mountScanner } from './scanner/index.js';
const root = document.getElementById('scanner-root');
if (root) mountScanner(root);
```

`mountScanner(rootEl, options?) -> { destroy(): void }`. It renders all its own UI inside `rootEl`, never touches anything outside it, and stops the camera on `destroy()` and on `pagehide`.

Events: after each classified reading the scanner dispatches on `rootEl`:
`new CustomEvent('cutiefarm:reading', { bubbles: true, detail: { label, confidence, scores, source } })`
where `label` is one of `'unripe' | 'ripening' | 'ripe' | 'mold' | 'none'` and `source` is `'camera' | 'sample'`. The page may listen; it must not depend on it.

Design tokens: the page defines these CSS custom properties on `:root` in `src/styles.css` (including any dark-mode values). The scanner styles itself **only** through them (with `var(--x, fallback)` fallbacks so it renders standalone):

```
--cf-bg  --cf-surface  --cf-ink  --cf-ink-muted  --cf-line
--cf-accent  --cf-accent-ink        (primary action colour and text on it)
--cf-unripe  --cf-ripening  --cf-ripe  --cf-mold   (state colours)
--cf-font-body  --cf-font-display
--cf-radius-s  --cf-radius-m
--cf-focus                          (focus ring colour)
```
