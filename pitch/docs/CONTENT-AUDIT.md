# Content audit: CutieFarm

Source: `reference/brief.md` (the team brief and its follow-up for the 6-minute version). There is no slide source.
Design reference: beatdeck's neutral dark theme with the accent `#F2871C`.

## Facts (never guess)

| Fact | Value | Source |
| --- | --- | --- |
| Title | CutieFarm | brief |
| Tagline | Know which oranges to pick, which are sick, and when to water. | brief |
| Speaker | The CutieFarm team | brief |
| Event | Cutiehacks 2026, Riverside | brief |
| QR target | https://cutiehacksproject.vercel.app | brief (links) |
| Bot | t.me/CutieFarmGroveBot, shown as text | brief (links) |

## Brief → beat mapping

| Brief section | Beat(s) | Status | Notes |
| --- | --- | --- | --- |
| Name, tagline | 1.2 | kept | |
| Inspiration: Minecraft, groves, Riverside | 2.1–2.2 | kept | |
| A grower's week: ripeness, late disease, fixed schedule | 2.3–2.7 | kept | no statistics added |
| 1 Camera: YOLO, peel colour | 3.1–3.3 | kept | |
| 1 Camera: CNN, canker message | 3.4–3.6 | kept | the message is labelled an example |
| 2 Sensors, forecast, formula, pump limits | 3.7–3.10 | kept | |
| 3 Bot: summary, alert, chat, photo, logging | 4.1–4.5 | kept | every bubble is labelled an example (see below) |
| 4 Dashboard | 5.1 (demo), 6.2–6.3 | kept | shown live, not as a screenshot |
| 5 Website | 9.2 | kept | QR and a description |
| How it's built | 6.1–6.6 | kept | |
| Challenges | 7.1–7.4 | kept | |
| What's next | 8.1–8.3 | kept | |
| Honest status | 3.6, 4.2–4.5 (labels), 7.4, notes | kept | |
| Links | 9.2 | kept | |

## Real artefacts

| Artefact | File | Used in | Rights / credit |
| --- | --- | --- | --- |
| Tangerine grove photo | `deck/assets/grove-1400.webp` | 1.2, 9.1 | Engin Akyurt, Pexels License. Credited on 9.2 |

## Decisions taken on the speaker's behalf

- **Dark theme.** We expect a projector. The accent is CutieFarm orange.
- **One QR only** (the website). The bot is shown as text, because `npm run verify` expects a single QR target.
- **Example bubbles without numbers.** The brief gives example text only for the 9:00 summary and the canker message,
  so those appear word for word. The alert, the Spanish answer and the `/week` reply describe what the bot sends
  and include no numbers, so the deck invents no counts or forecasts.
- **No dashboard screenshot.** `web/public/dashboard/scans/*.jpg` is the same grove photo without overlays, so the
  dashboard is shown live in the demo instead.
- **Beat 9.1 has `tolerance: 1`.** Text over the photo is anti-aliased slightly differently when the beat is reached
  by stepping and when it is loaded directly: 0.74% of pixels differ. The two frames were compared by eye and look the same.

## Open questions

- [ ] Do the presenters want the bot as a second QR? It needs a change to `verify`'s single-QR rule, so it is text for now.
