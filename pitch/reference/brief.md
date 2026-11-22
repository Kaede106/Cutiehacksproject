# CutieFarm pitch brief (source of every fact in the deck)

The deck may use only these facts. It must not invent numbers, users, accuracy figures or quotes.

## Name and tagline
CutieFarm. "Know which oranges to pick, which are sick, and when to water."

## Inspiration
The team loves Minecraft's automatic sugar cane farms: build it once and it grows and harvests itself. Real orange
groves still need someone to walk the rows, one tree at a time, to judge ripeness, spot sick fruit and decide when
to water. Cutiehacks is in Riverside, where California's navel orange industry began.

A grower's week: walking the rows to judge ripeness, catching disease late, watering on a fixed schedule.

## What it does
1. Camera: a laptop webcam. YOLO finds each orange. A peel-colour check labels it unripe / ripening / ready to pick.
   The team's own PyTorch CNN, trained on citrus images, labels each orange healthy, citrus canker or melanose.
   Example bot message: "1 orange may have citrus canker: take a look before it spreads."
2. Sensors: an Arduino reads soil moisture, temperature and humidity. With the forecast (Open-Meteo),
   evapotranspiration × a citrus crop coefficient, minus rain, gives the watering cadence and the next watering.
   The Arduino drives a motor and pump within safety limits: max seconds, cooldown, daily cap, never on wet soil.
3. Telegram bot @CutieFarmGroveBot: a 9:00 summary (e.g. "3 ready to pick, 5 ripening. Water on Thursday: hot, dry
   week ahead, so twice a week for now."), instant alerts when more oranges are ready, chat by text or voice in the
   grower's language (e.g. "¿y las de la izquierda?"), a photo check, and logging with /picked, /watered and /week
   (a summary with a harvest forecast).
4. Control room dashboard: camera boxes, ready counts, the watering plan and sensor trends.
5. Website: an in-browser scanner (frames never leave the device) and a watering simulator.
   https://cutiehacksproject.vercel.app

## How it's built
Python (OpenCV, Ultralytics YOLO, PyTorch CNN, python-telegram-bot, OpenAI for chat and voice); an Arduino plus a
serial bridge; a Vite web app on Vercel. Every part writes append-only files to one shared data folder and never
calls another part directly. One supervisor command, `python -m farm`, runs them all. Four people built it in parallel:
2 on hardware, 1 on ML, 1 on software and integration.

## Challenges and lessons
The STM32 board fought us, so we switched to Arduino. Colour is fragile, so YOLO finds the fruit first. Making a
public bot safe: rate limits, no group chats, no secrets in logs. Honest demo labelling.

## What's next
Wire the live camera and sensors in permanently. Finish the STM32 port. Turn automatic watering on after pump testing.

## Honest status
The bot runs on a team laptop. Until the camera and sensors are wired in permanently, it uses clearly labelled demo
data. No deployments, users or accuracy figures are claimed.

## Links
Website https://cutiehacksproject.vercel.app · Bot https://t.me/CutieFarmGroveBot ·
Repo https://github.com/Kaede106/Cutiehacksproject

## Assets
`deck/assets/grove-1400.webp`, copied from `web/public/grove-1400.webp`: "Ripening Tangerines on the Tree Branches"
by Engin Akyurt, Pexels License (see `web/public/CREDITS.md`).
