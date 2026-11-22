import type { SceneDef } from 'beatdeck';

/**
 * CutieFarm, about 6 minutes at a relaxed pace. One click = one beat.
 * `ref` = the section of the brief (reference/brief.md) it comes from, `note` = what the presenter says.
 */
export const SCENES: SceneDef[] = [
  {
    id: 'OPEN', title: 'OPEN',
    beats: [
      { name: 'standby', note: 'Calm screen while people sit down. The first click starts the talk.' },
      { name: 'title', ref: 'Name, tagline', note: 'Hi, we are the CutieFarm team. CutieFarm tells a grower which oranges to pick, which are sick, and when to water.' },
    ],
  },
  {
    id: 'THE PROBLEM', title: 'THE PROBLEM',
    beats: [
      { name: 'minecraft', ref: 'Inspiration', note: 'We love the automatic sugar cane farms in Minecraft. You build the farm once, and from then on it grows and harvests itself.' },
      { name: 'real groves', ref: 'Inspiration', note: "Real orange groves don't work like that. And we are in Riverside, where California's navel orange industry began, so this felt close to home." },
      { name: 'walk the rows', ref: 'Inspiration', note: "Think of a grower's week. Someone has to walk the rows, one tree at a time, and look at every tree themselves." },
      { name: 'ripeness', ref: 'Inspiration; follow-up brief', note: 'At each tree they judge ripeness: is this fruit ready, or does it need another week?' },
      { name: 'disease', ref: 'Follow-up brief', note: 'They look for sick fruit. And when you only see a tree on your walk, disease is often caught late.' },
      { name: 'watering', ref: 'Follow-up brief', note: 'And watering usually runs on a fixed schedule, whatever the soil and the weather are doing that week.' },
      { name: 'three questions', ref: 'Inspiration', note: 'So every tree, every week, comes down to three questions answered by hand. Ready to pick? Sick? Needs water? We wanted the grove to answer them itself.' },
    ],
  },
  {
    id: 'THREE ANSWERS', title: 'THREE ANSWERS',
    beats: [
      { name: 'ripe?', ref: 'What it does · 1', note: 'First question: is it ripe? A laptop webcam points at the tree.' },
      { name: 'YOLO', ref: 'What it does · 1', note: 'YOLO, an object detector, finds each orange in the frame and draws a box around it.' },
      { name: 'peel colour', ref: 'What it does · 1', note: 'Then a peel-colour check on each box labels the orange unripe, ripening, or ready to pick.' },
      { name: 'healthy?', ref: 'What it does · 1; follow-up brief', note: 'Second question: is it healthy? For this we trained our own model.' },
      { name: 'CNN', ref: 'What it does · 1; follow-up brief', note: 'A PyTorch CNN, trained on citrus images, labels each orange healthy, citrus canker, or melanose.' },
      { name: 'canker message', ref: 'Follow-up brief', note: 'So instead of finding it weeks later, the bot can say: one orange may have citrus canker, take a look before it spreads. This is an example message.' },
      { name: 'water?', ref: 'What it does · 2', note: 'Third question: does it need water?' },
      { name: 'inputs', ref: 'What it does · 2', note: 'An Arduino reads soil moisture, temperature and humidity. We add the weather forecast from Open-Meteo.' },
      { name: 'formula', ref: 'What it does · 2; follow-up brief', note: 'Evapotranspiration, times a citrus crop coefficient, minus the rain, tells us how often to water and when the next watering is due.' },
      { name: 'pump limits', ref: 'What it does · 2', note: 'The Arduino also drives a motor and a pump, so it can water by itself. But only within safety limits: a maximum run time, a cooldown, a daily cap, and never on wet soil.' },
    ],
  },
  {
    id: 'THE BOT', title: 'THE BOT',
    beats: [
      { name: 'one chat', ref: 'What it does · 3', note: 'All three answers land in one place the grower already uses: a Telegram bot, CutieFarmGroveBot.' },
      { name: '9:00 summary', ref: 'What it does · 3', note: 'Every morning at nine it sends a summary like this. These bubbles are examples; the bot currently runs on clearly labelled demo data.' },
      { name: 'ready alert', ref: 'What it does · 3', note: 'During the day, it pings you as soon as more oranges are ready.' },
      { name: 'spanish', ref: 'What it does · 3', note: 'You can just ask it things, in your own language, by text or by voice. Here a grower asks in Spanish about the trees on the left. You can also send a photo of an orange and get its state.' },
      { name: '/week', ref: 'What it does · 3', note: 'And you log what you do with /picked and /watered. /week gives you the week back, with a harvest forecast.' },
    ],
  },
  {
    id: 'DEMO', title: 'DEMO',
    beats: [
      { name: 'camera + dashboard', ref: 'What it does · 1, 4', note: 'SWITCH TO THE LAPTOP. Show the live camera window with boxes and ripeness labels, then the control room dashboard: ready counts, the watering plan and sensor trends. Come back and press →.' },
      { name: 'telegram', ref: 'What it does · 3', note: 'SWITCH TO TELEGRAM. Show the 9:00 summary, ask a question (try a voice note), send an orange photo, and run /week. Then come back and press →.' },
    ],
  },
  {
    id: 'MARKET', title: 'MARKET',
    beats: [
      { name: 'TAM', ref: 'Market (USDA NASS 2025-26)', note: 'Who is this for? Citrus in the US was a 3.15 billion dollar crop last season, on about 428 thousand bearing acres. That is the value of the crop we watch over, not our revenue.' },
      { name: 'SAM', ref: 'Market (USDA NASS 2025-26)', note: 'California alone grows 2.73 billion dollars of it, on 267 thousand acres. That is the market we can serve with a webcam, an Arduino and a Telegram bot.' },
      { name: 'SOM', ref: 'Market (USDA NASS 2025-26)', note: 'We start with California oranges: a 722 million dollar crop on 133,500 acres, and navel oranges began right here in Riverside. Source on screen: USDA, 2025-26 season.' },
    ],
  },
  {
    id: 'HOW WE BUILT IT', title: 'HOW WE BUILT IT',
    beats: [
      { name: 'shared folder', ref: "How it's built", note: 'How we built it. At the centre there is one shared data folder, full of append-only files.' },
      { name: 'writers', ref: "How it's built", note: 'The camera and ML write their detections there. The Arduino bridge writes its sensor readings there.' },
      { name: 'bot + dashboard', ref: "How it's built", note: 'The bot and the dashboard work from the same folder. No part ever calls another part directly.' },
      { name: 'python -m farm', ref: "How it's built", note: 'One supervisor command, python -m farm, starts them all.' },
      { name: 'four people', ref: "How it's built", note: 'That is what let four of us build in parallel without blocking each other: two on hardware, one on ML, one on software and integration.' },
      { name: 'stack', ref: "How it's built", note: 'The stack: Python with OpenCV, YOLO and PyTorch; python-telegram-bot and OpenAI for chat and voice; an Arduino; and a Vite site on Vercel.' },
    ],
  },
  {
    id: 'WHAT WE LEARNED', title: 'WHAT WE LEARNED',
    beats: [
      { name: 'STM32', ref: 'Follow-up brief · challenges', note: 'What fought back. We started on an STM32 board. It fought us, so we switched to an Arduino to keep moving.' },
      { name: 'colour', ref: 'Follow-up brief · challenges', note: 'Colour on its own is fragile. So YOLO finds the fruit first, and the colour check only judges the orange inside each box.' },
      { name: 'safe bot', ref: 'Follow-up brief · challenges', note: 'A public bot has to be safe: rate limits, no group chats, and no secrets in the logs.' },
      { name: 'honest demo', ref: 'Status; follow-up brief', note: 'And we label demo data as demo data. Until the hardware is wired in for good, the bot tells you when it is showing examples.' },
    ],
  },
  {
    id: "WHAT'S NEXT", title: "WHAT'S NEXT",
    beats: [
      { name: 'wire it in', ref: 'Follow-up brief · next', note: 'Next: wire the live camera and the sensors in permanently, so the demo data can go.' },
      { name: 'STM32 port', ref: 'Follow-up brief · next', note: 'Finish the STM32 port we had to park.' },
      { name: 'auto watering', ref: 'Follow-up brief · next', note: 'And turn automatic watering on, but only after we have tested the pump properly.' },
    ],
  },
  {
    id: 'CLOSE', title: 'CLOSE',
    beats: [
      { name: 'grove watches itself', ref: 'Name, inspiration', tolerance: 1, /* text over the photo antialiases slightly differently when composited mid-transition vs. a fresh load (0.74% px, frames checked by eye: identical) */ note: 'Like those Minecraft farms: build it once. A grove that watches itself.' },
      { name: 'thank you', ref: 'Links', note: 'Scan the code to try the scanner and the watering simulator in your browser, or message the bot. Thank you!' },
    ],
  },
];
