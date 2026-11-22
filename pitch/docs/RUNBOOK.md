# Runbook: CutieFarm pitch (Cutiehacks 2026)

```bash
cd pitch && npm install && npm run present
```

That builds the deck and opens `http://127.0.0.1:4173/`. Once `npm install` has run, it all works offline.

**Single HTML file:** `npm run build:html` writes `dist-single/cutiefarm-pitch.html`, one file (fonts and photo
inlined) that opens with a double click, with no server and no internet. Use `npm run present` if you want the presenter window (P),
because a page opened from disk may not connect to it.

## Keys

| Key | Action |
| --- | --- |
| **→** (also ↓, PageDown, click, Space in fullscreen) | next beat |
| **P** | presenter window: current and next beat, speaker notes, timer |
| **O** | overview: click any beat to jump there |
| **F** | fullscreen |
| ← ↑ PageUp | previous beat |
| 1–9 | jump to scenes 1–9 (scene 10, the close, is reachable with → or End) |
| B or . | blackout on/off |

## Before the talk

1. Run `npm run present`. Press **P** and drag the presenter window to the laptop screen. It must say "stage connected".
2. Click the stage window, put it on the projector and press **F**. You start on 1.1 (standby). The first → shows the title.
3. Open the demo windows before you start, so you can switch to them during the talk: the camera window, the
   control room dashboard and Telegram with @CutieFarmGroveBot.

## Shape of the talk (about 6 minutes, 44 beats, no automatic beats)

| Scene | Beats | What |
| --- | --- | --- |
| 1 OPEN | 2 | standby, title |
| 2 THE PROBLEM | 7 | Minecraft farms, then a grower's week: ripeness, disease, watering, three questions |
| 3 THREE ANSWERS | 10 | ripe? (YOLO + peel colour) · healthy? (our CNN + canker message) · water? (sensors, forecast, maths, pump limits) |
| 4 THE BOT | 5 | one chat, 9:00 summary, alert, Spanish question, /week (all labelled as examples) |
| 5 MARKET | 3 | TAM US citrus $3.15B · SAM California citrus $2.73B · SOM California oranges $722M (USDA 2025-26 crop value) |
| 6 DEMO | 2 | **6.1** switch to the camera window and the dashboard · **6.2** switch to Telegram |
| 7 HOW WE BUILT IT | 6 | the shared folder diagram builds node by node, `python -m farm`, four people, the stack |
| 8 WHAT WE LEARNED | 4 | STM32 → Arduino, colour is fragile, a safe public bot, honest demo labels |
| 9 WHAT'S NEXT | 3 | wire it in, STM32 port, automatic watering after pump tests |
| 10 CLOSE | 2 | "A grove that watches itself.", then the QR, links and thanks |

**Demo (scene 6):** on 6.1, Alt+Tab to the camera window, then to the dashboard. Come back to the stage and press →.
On 6.2, switch to Telegram. Come back and press → to continue. If the demo fails, stay on the slides: scene 4
already shows the bot.

## If something goes wrong

- If you lose your place or refresh the page, the URL keeps `#scene.beat`. Reload and you are back on the same beat.
- If the presenter says "no connection", press **resync**, or close it and press **P** again. It must run in the same browser on the same machine.
- As a last resort, copy `dist/` to a USB stick. It runs in any browser on any laptop (`npx serve dist`).

## Config

`deck/deck.config.ts` holds the title, the tagline, `qrUrl` (now `https://cutiehacksproject.vercel.app`), the bot
and the repo. Rebuild after editing.

## Theme decision

The deck uses beatdeck's neutral dark theme with the CutieFarm orange `#F2871C` as the one accent. We chose
dark because hackathon halls use projectors, and projectors favour a dark stage. If the room turns out to be very bright, import
`themes/light.css` after `neutral.css` in `deck/index.tsx` and rebuild.
