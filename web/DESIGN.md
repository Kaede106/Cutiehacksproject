# CutieFarm landing: design decisions (v1)

Mode: Persuade. Light only, chosen for the use scene (judges on laptops in a bright hall); the hero supplies the one dark field.

## World
The canopy of a citrus tree, seen by the camera. The hero is a full-bleed photograph with corner brackets that show the camera runner’s ripeness readings. The brackets appear on load when motion is enabled. Everything after the hero stays quiet: a pale leaf-tinted ground, dark green ink and orange buttons.

## The daily message (hero, right column)
The example 9:00 Telegram message sits next to the headline on desktop and below the scanner button on phones. A pale chat bubble holds a photo of ripe oranges on a tree, the example from PRODUCT.md and a 9:00 timestamp. The caption names the example, and the line below explains what the laptop and OpenAI process.

## Telegram examples

The section directly below the hero uses the same chat-bubble shape for short example exchanges on demo data. Bot messages align left on white and grower messages align right on the existing muted canopy tint. Dividers group the exchanges. The Telegram link is an outlined button beside the QR code, which is hidden on phones where the link opens the app directly.

## Tokens (src/styles.css, :root)
| Token | Value | Note |
|---|---|---|
| --cf-bg | #F3F6EE | leaf-tinted off-white (cool, not cream) |
| --cf-surface | #FFFFFF | |
| --cf-ink | #15301F | 14.2:1 on surface |
| --cf-ink-muted | #4A5E50 | 7.0:1 on surface |
| --cf-line | #82978A | 3.1:1 on surface (OK for control borders) |
| --cf-accent | #F2871C | peel orange; fill only, edge #B85A00 on page buttons |
| --cf-accent-ink | #15301F | 5.6:1 on accent |
| --cf-unripe | #22501A | 9.4:1 on surface, darkest state |
| --cf-ripening | #B08F00 | 3.1:1 on surface, lightest state: use for marks/fills, not text |
| --cf-ripe | #BB3A0E | 5.6:1 |
| --cf-font-body / --cf-font-display | "Recursive" | one family, two voices |
| --cf-radius-s / -m | 6px / 16px | buttons are pills (999px) |
| --cf-focus | #1450C8 | the hero and footer override it to #FFD84A |

The state colours are separated by lightness as well as hue (unripe dark, ripe mid, ripening light), so they stay apart under protan/deutan simulation. Always pair them with the text label.

Page-only: --canopy #1F5A35, --canopy-ink #F7FAF3, --canopy-muted #C9DCCB (5.7:1 on canopy), --line-soft #D5DED3.

## Type
Recursive (Google Fonts, axes wght 300–900 and CASL 0–1). Headings, the button and the "What you do" cells use the casual axis (`font-variation-settings: "CASL" 1`, weight 600–700), which reads like a hand-painted fruit-stand sign. Body text uses the linear axis (CASL 0) at 18px/1.55. h1 clamps from 38 to 56px and h2 from 32 to 48px. Weights stay at 700 or below. The scanner gets only the family through the token; to use the casual voice it must also set `font-variation-settings: "CASL" 1`.

## Layout
12-column feel, max 1240px, gutters of 16px on phones, 32px on tablets and 48px on desktop. Sections below the hero use a 4/8 split (heading left, content right) on wide screens and stack on phones. There are no cards. The states are a real table, which turns into rows with a fruit photo beside the text on phones.

## Rules for later iterations
- The corner bracket is the camera motif (hero; the scanner draws its own). Do not nest a second set around the scanner.
- No eyebrows, no all-caps labels, no arrows on buttons, no gradient text, no glows.
- Product name appears in: <title>, og:title, the masthead wordmark and the footer (all in index.html).
- All sensor-board copy lives in the single `[data-board-note]` block in "How it's built".
- Keep the hero’s detection boxes aligned with the photo crop documented in `public/CREDITS.md`.
