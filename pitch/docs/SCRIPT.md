# CutieFarm: guion del pitch (unos 6 minutos, ritmo pausado)

Cómo leer este guion:
- **[→]** es un clic (flecha derecha o el mando). Cada clic coincide con un *beat* del deck. Habla y **después** pasa: la diapositiva acompaña a la frase, no la anuncia.
- *Las notas en cursiva* son indicaciones para el presentador. No se dicen en voz alta.
- Lo que se dice está en inglés y entre comillas, a unas 120 palabras por minuto, con pausas. Los tiempos son acumulados.
- Hay 10 escenas y 44 clics; el mercado va **después** de la demo. Cuatro bloques seguidos de minuto y medio, uno por persona.
- Ahora hay 10 escenas y 44 clics. Las teclas 1–9 saltan a las escenas 1–9; el cierre se alcanza con → o con End.
- Antes de empezar, abre la ventana del presentador con la tecla **P**. Muestra la nota de cada beat, el siguiente beat y un reloj.

---

## 0 · Antes de subir (no cuenta en el tiempo)

*En el portátil del presentador, por este orden:*
1. *`farm\demo.ps1 -Camera` ya está corriendo. La ventana de la cámara ve las naranjas, el panel está abierto en http://127.0.0.1:8800 y Telegram está abierto en el chat con @CutieFarmGroveBot.*
2. *El deck: `cd pitch && npm run present`, y pantalla completa con **F**.*
3. *Si la CNN de salud ha dado falsas alarmas en el ensayo, arranca con `$env:CUTIEFARM_HEALTH="0"` y salta la frase marcada con ⚠ en la escena 3.*

---

### 🎤 Persona 1 (hardware, la idea de Minecraft): 0:00 → 1:30

## 1 · Open (0:00 → 0:25)

*Pantalla de espera mientras la gente se sienta.*

**[→] Título**
> "Hi, we're the CutieFarm team.
> CutieFarm tells a grower **which oranges to pick, which are sick, and when to water**."

*Pausa de dos segundos. Mira al público, no a la pantalla.*

---

## 2 · The problem (0:25 → 1:30)

**[→] Minecraft**
> "Some of us are big Minecraft players. If you've built an automatic sugar cane farm, you know the feeling: you build it once… and from then on, it grows and harvests itself."

**[→] Real groves**
> "Real orange groves don't work like that. And we're in Riverside, where California's navel orange industry began, so this felt close to home."

**[→] Walk the rows**
> "Think about a grower's week. Someone has to walk the rows, one tree at a time, and look at every tree themselves."

**[→] Ripeness**
> "At each tree they judge ripeness: is this fruit ready, or does it need another week?"

**[→] Disease**
> "They look for sick fruit. And when you only see a tree on your walk, disease is often caught late."

**[→] Watering**
> "And watering usually runs on a fixed schedule, whatever the soil and the weather are doing that week."

**[→] Three questions**
> "So every tree, every week, comes down to three questions answered by hand: **Ready to pick? Sick? Needs water?**
> We wanted the grove to answer them itself."

*Pausa. Es el giro de la charla.*

---

### 🎤 Persona 2 (ML): 1:30 → 3:00

*Entrada:* "…and here's [nombre] with how the grove answers them."

## 3 · Three answers (1:30 → 3:00)

**[→] Ripe?**
> "First question: is it ripe? A laptop webcam points at the tree."

**[→] YOLO**
> "YOLO, an object detector, finds every orange in the frame and draws a box around it."

**[→] Peel colour**
> "Then a peel-colour check on each box labels the orange: unripe, ripening, or ready to pick."

**[→] Healthy?**
> "Second question: is it healthy? For this, we trained our own model today."

**[→] CNN**
> "A PyTorch CNN, trained on citrus images, labels each orange healthy, citrus canker, or melanose."
> ⚠ *Solo si la CNN ha ido bien en el ensayo; si no, sáltala:* "It's an early model, so we treat it as a flag to go and look, not a diagnosis."

**[→] Canker message**
> "So instead of finding it weeks later, the bot can tell you: *one orange may have citrus canker, take a look before it spreads.*"

**[→] Water?**
> "Third question: does the grove need water?"

**[→] Inputs**
> "An Arduino reads soil moisture, temperature and humidity, and we add the weather forecast from Open-Meteo."

**[→] Formula**
> "Evapotranspiration, times a citrus crop coefficient, minus the rain, tells us how often to water and when the next watering is due."

**[→] Pump limits**
> "And the Arduino drives a pump, so the farm can water itself, but only within safety limits: a maximum run time, a cooldown, a daily cap, and never on wet soil."

---

### 🎤 Persona 3 (Pablo, software): 3:00 → 4:30

*Entrada:* "…and all of that lands in one place. [Nombre]?"

## 4 · The bot (3:00 → 3:40)

**[→] One chat**
> "All three answers land in one place the grower already uses: a Telegram bot."

**[→] 9:00 summary**
> "Every morning at nine it sends a summary like this one. These bubbles are examples; for now the bot runs on clearly labelled demo data."

**[→] Ready alert**
> "During the day, it pings you as soon as more oranges are ready."

**[→] Spanish**
> "And you can just ask it things, in your own language, by text or by voice. Here a grower asks, in Spanish, about the trees on the left."

**[→] /week**
> "You log what you did with *picked* and *watered*, and */week* gives you your week back, with a harvest forecast."

---

## 5 · Demo (3:40 → 4:30, unos 50 s)

**[→] Camera + dashboard**
> "Let me show you."

*Cambia al portátil (Alt+Tab). Haz esto con calma:*
1. *Ventana de la cámara apuntando a las naranjas:* "Each box is YOLO finding an orange, and the label is the ripeness."
2. *Pulsa **S**:* "I just saved a scan…"
3. *Pasa al panel (127.0.0.1:8800):* "…and here it is in the control room: what's ready, the live camera, the watering plan and the sensor trends."

*Vuelve al deck y pulsa →.*

**[→] Telegram**
*Cambia a Telegram:*
1. *Si llega la alerta "more oranges are ready", señálala:* "And the bot already noticed."
2. *Manda una nota de voz:* "When should I water?" *Lee la respuesta en voz alta.*
3. *Si queda tiempo, escribe `/week`.*

*Vuelve al deck y pulsa →.*

*Plan B: si la cámara o la wifi fallan, quédate en estas dos diapositivas y di:* "The demo gods aren't with us, but the bot is live: scan the QR at the end and try it yourselves." *Y sigue.*

---

### 🎤 Persona 4 (hardware): 4:30 → 6:00

*Entrada:* "So who is this for? [Nombre]."

## 6 · Market (4:30 → 4:55)

**[→] TAM**
> "Who is this for? Citrus in the US was a **3.15 billion dollar** crop last season, on about 428 thousand acres. That's the value of the crop we watch over, not our revenue."

**[→] SAM**
> "California alone grows **2.73 billion** of it. That's the market we can serve with a webcam, an Arduino and a Telegram bot."

**[→] SOM**
> "And we start with California oranges: a **722 million dollar** crop, and navel oranges began right here in Riverside."
> *La fuente sale en pantalla (USDA, temporada 2025-26). Si el jurado pregunta por ingresos, di que estas cifras son el valor de la cosecha y que el modelo de precios por acre está por definir.*

---

## 7 · How we built it (4:55 → 5:25)

**[→] Shared folder**
> "How we built it. In the middle there's one shared data folder, full of append-only files."

**[→] Writers**
> "The camera and the models write their detections there. The Arduino bridge writes its sensor readings there."

**[→] Bot + dashboard**
> "The bot and the dashboard read from the same folder. No part ever calls another part directly."

**[→] python -m farm**
> "One command, *python -m farm*, starts them all and restarts anything that crashes."

**[→] Four people**
> "That's what let four of us build in parallel without blocking each other: two on hardware, one on machine learning, one on software and integration."

**[→] Stack**
> "Python with OpenCV, YOLO and PyTorch, a Telegram bot with OpenAI for chat and voice, an Arduino, and a website on Vercel."

---

## 8 · What we learned (5:25 → 5:45)

**[→] STM32**
> "What fought back: we started on an STM32 board. It fought us, so we switched to an Arduino to keep moving."

**[→] Colour**
> "Colour on its own is fragile, so YOLO finds the fruit first, and colour only judges what's inside each box."

**[→] Safe bot**
> "A public bot has to be safe: rate limits, no group chats, and no secrets in the logs."

**[→] Honest demo**
> "And we label demo data as demo data. The bot always tells you when it's showing examples."

---

## 9 · What's next (5:45 → 5:53)

**[→] Wire it in**
> "Next: wire the camera and sensors in for good,"

**[→] STM32 port**
> "finish the STM32 port,"

**[→] Auto watering**
> "and turn automatic watering on, once the pump has been properly tested."

---

## 10 · Close (5:53 → 6:00)

**[→] A grove that watches itself**
> "Like those Minecraft farms: build it once, and **the grove watches itself.**"

*Pausa.*

**[→] Thank you + QR**
> "Scan the code to try the scanner and the watering simulator, or message the bot. Thank you!"

*Quédate en esta diapositiva durante las preguntas.*

---

## Preguntas probables del jurado (respuestas cortas)

- **"How accurate is it?"**
  > "We haven't measured accuracy on real groves yet. Ripeness is a colour rule on top of YOLO; health is an early CNN, so we treat it as a flag, not a diagnosis."
- **"Does it work outside / in different light?"**
  > "Light shifts colours, which is the weak point of the colour check. That's why YOLO finds the fruit first, and why we'd train on real grove photos next."
- **"Why Telegram?"**
  > "Growers already have it on their phone: no app to install, alerts arrive like any message, and it takes voice."
- **"What happens if the internet drops?"**
  > "Detection and sensors run on the laptop. Only the bot messages and the chat need the internet."
- **"Is the watering safe?"**
  > "There's a maximum run time, a cooldown, a daily cap, and it never waters wet soil. Automatic mode is off by default."

## Tiempos de referencia

| Bloque | Quién | Escenas | Termina en |
|---|---|---|---|
| 1 | Persona 1 (hardware, idea) | Open, Problem | 1:30 |
| 2 | Persona 2 (ML) | Three answers: ripe, healthy, water | 3:00 |
| 3 | Persona 3 (Pablo) | Bot, Demo | 4:30 |
| 4 | Persona 4 (hardware) | Market, How we built it, Learned, Next, Close | 6:00 |

- Una sola persona pasa las diapositivas (Pablo, que también lleva el portátil en la demo).
- Si la demo se alarga, Persona 4 resume "What we learned" en una frase por clic.
