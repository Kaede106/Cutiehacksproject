# CutieFarm product brief

CutieFarm is a Cutiehacks prototype for two questions: is this orange ready to pick, and does the grove need water? Mold and disease detection were dropped from the product.

## What judges can try today

- The browser scanner estimates ripeness from peel colour in the centre of a webcam frame or a sample image. It runs entirely on the visitor’s device.
- [@CutieFarmGroveBot](https://t.me/CutieFarmGroveBot?start=landing) runs on a team laptop. It labels demo scans and simulated sensor readings while the team connects the hardware. It sends updates while the laptop is running.
- The watering simulator lets visitors change sample soil and weather inputs and see the suggested schedule.
- A demo snapshot of the control room at `/dashboard/`, made from demo data (see below).

| State | Visual cue | What the grower does |
|---|---|---|
| Unripe | Mostly green peel | Leave it on the tree |
| Ripening | Green turning yellow or orange | Check again in a few days |
| Ready to pick | Even, deep orange peel | Harvest |

## Telegram prototype

- A new scan with more ripe oranges triggers a ready-to-pick alert before the next daily update. The prototype demonstrates alerts with demo scans.
- Ask “¿y las de la izquierda?” or “when should I water?” by text or voice. An OpenAI model answers from the latest farm data only.
- Send a photo for a ripeness check. The bot uses the scanner’s peel-colour check and analyses the photo on the laptop.
- At 9:00 every morning the bot says what to pick and when to water, with buttons for watering details and a reminder. Show the example with a photo of ripe oranges on a tree: “3 ready to pick, 5 ripening. Water on Thursday: hot, dry week ahead, so twice a week for now.”
- Send “picked 3” or “he regado” to log work. The commands are `/picked` and `/watered`. Use `/week` for a 7-day summary and `/stop` to unsubscribe.

The bot analyses photos on the laptop. Chat questions, recent chat context and a text summary of the latest farm data go to OpenAI for answers. Voice notes go to OpenAI for transcription. Photos sent through Telegram stay on the laptop for analysis and are never sent to OpenAI. The browser scanner uploads nothing.

## Control room

The live control room (`python -m farm.dashboard`, in `farm/dashboard/`) is a read-only big-screen page: the latest camera frame with each orange boxed, the count ready to pick, the watering advice with the last 24 hours of soil, temperature and humidity, and an activity feed. It reads the local data folder, so it runs only on the farm laptop and is never exposed to the internet.

The public site cannot link to it. Instead it serves a static demo snapshot at `/dashboard/`, made with `python -m farm.dashboard export` from a demo data folder (`web/public/dashboard/`, see its README). The snapshot page says in a banner that it is demo data from a given date and that the live version runs on the farm laptop. It keeps the demo and simulated labels, and its scan is a sample photo run through the camera program. The landing page links to it in “How it’s built” and in the footer, as a secondary link with “(demo data)” in its text. Refresh the snapshot by re-running the export before publishing.

## Hardware being connected

- Laptop camera: YOLO finds each orange and the colour check estimates ripeness. The team is finishing the camera program.
- Arduino: reads soil moisture, temperature and humidity. The team is connecting the board. The watering advice uses those readings plus the forecast. It checks soil moisture first and uses estimated water demand to set the schedule. Treat the advice as a rule of thumb.

## Audience and constraints

Hackathon judges and visitors should be able to understand the prototype and try it on a laptop or phone. Use English copy and keep the real Spanish examples. Label examples, demo scans and simulated readings. Avoid invented figures for accuracy, yield, adoption, latency or savings, as well as invented testimonials, partners or press.

The Vite page uses vanilla HTML, CSS and JavaScript. Keep it keyboard accessible, with visible focus, reduced-motion support, good contrast and 16px side gutters on phones. Google Fonts is the only external asset source. The Telegram link uses the public username in the committed `web/.env`.

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
where `label` is one of `'unripe' | 'ripening' | 'ripe' | 'none'` and `source` is `'camera' | 'sample'`. The page may listen; it must not depend on it.

Design tokens: the page defines these CSS custom properties on `:root` in `src/styles.css` (including any dark-mode values). The scanner styles itself **only** through them (with `var(--x, fallback)` fallbacks so it renders standalone):

```
--cf-bg  --cf-surface  --cf-ink  --cf-ink-muted  --cf-line
--cf-accent  --cf-accent-ink        (primary action colour and text on it)
--cf-unripe  --cf-ripening  --cf-ripe   (state colours)
--cf-font-body  --cf-font-display
--cf-radius-s  --cf-radius-m
--cf-focus                          (focus ring colour)
```
