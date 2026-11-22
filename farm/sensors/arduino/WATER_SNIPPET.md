# Watering code for the team's sketch (`sketch_nov21a`)

The laptop asks for watering by sending one line over USB serial, `WATER=<seconds>` (for example `WATER=8`). The code below reads it **without blocking `loop()`**. It runs the existing motor (E1 = pin 6 PWM, I1 = pin 4 HIGH, I2 = pin 5 LOW) for that many seconds, then stops and prints `#WATER_DONE <seconds>`. The bridge waits for that line before the bot says "Done". Without it, the bot says the board didn't confirm and doesn't log the watering.

Safety on the board: the board refuses any run longer than `WATER_MAX_S` (30 s), whatever the laptop sends. A second `WATER=` is refused while a run is going on, and `WATER=0` stops the pump at once. If the board resets or the USB cable is pulled, the pins go LOW and the pump stops.

## 1. Remove the always-on motor lines

At the end of `loop()`, the sketch currently turns the motor on every time round:

```cpp
  analogWrite(E1, 153);  // Courir à la moitié de la vitesse
  digitalWrite(I1, HIGH);
  digitalWrite(I2, LOW);
```

**Delete these three lines.** Otherwise the pump never stops.

## 2. Paste this block above `setup()`

```cpp
// ---- CutieFarm watering: WATER=<seconds> from the laptop ------------------
const int WATER_MAX_S = 30;    // hard safety cap: longer requests are refused
const int PUMP_SPEED = 153;    // analogWrite on E1, 0..255 (153 = 60%)

bool watering = false;
unsigned long waterStart = 0;
unsigned long waterMs = 0;
int waterSeconds = 0;
char waterBuf[16];
byte waterLen = 0;
bool waterOverflow = false;

void pumpOn() {
  digitalWrite(I1, HIGH);
  digitalWrite(I2, LOW);
  analogWrite(E1, PUMP_SPEED);
}

void pumpOff() {
  analogWrite(E1, 0);
  digitalWrite(I1, LOW);
  digitalWrite(I2, LOW);
}

void waterCommand(const char *cmd) {
  if (strncmp(cmd, "WATER=", 6) != 0) return;  // not for us
  const char *p = cmd + 6;
  if (*p == '\0') { Serial.println(F("#WATER_ERR no seconds")); return; }
  long n = 0;
  for (; *p; p++) {
    if (*p < '0' || *p > '9' || n > 999) { Serial.println(F("#WATER_ERR bad number")); return; }
    n = n * 10 + (*p - '0');
  }
  if (n == 0) {                                  // WATER=0: stop now
    if (watering) { pumpOff(); watering = false; Serial.println(F("#WATER_STOPPED")); }
    return;
  }
  if (n > WATER_MAX_S) { Serial.print(F("#WATER_ERR over cap ")); Serial.println(WATER_MAX_S); return; }
  if (watering) { Serial.println(F("#WATER_ERR busy")); return; }
  waterSeconds = (int)n;
  waterMs = (unsigned long)n * 1000UL;
  waterStart = millis();
  watering = true;
  pumpOn();
  Serial.print(F("#WATER_START "));
  Serial.println(waterSeconds);
}

// Call often: reads any waiting serial bytes and stops the pump on time. Never blocks.
void waterTick() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      waterBuf[waterLen] = '\0';
      if (!waterOverflow) waterCommand(waterBuf);
      waterLen = 0;
      waterOverflow = false;
    } else if (waterLen < sizeof(waterBuf) - 1) {
      waterBuf[waterLen++] = c;
    } else {
      waterOverflow = true;                      // too long to be a command: ignore the line
    }
  }
  if (watering && millis() - waterStart >= waterMs) {
    pumpOff();
    watering = false;
    Serial.print(F("#WATER_DONE "));
    Serial.println(waterSeconds);
  }
}

// Use instead of delay() so the pump still stops on time while the sketch waits.
void waterDelay(unsigned long ms) {
  unsigned long start = millis();
  while (millis() - start < ms) waterTick();
}
// ---------------------------------------------------------------------------
```

## 3. Three small changes in `setup()` and `loop()`

- At the end of `setup()`, after the `pinMode` lines, add `pumpOff();` so the pump starts off.
- Make `waterTick();` the **first line of `loop()`**. It must come before the `Failed to read sensor` check, which returns early.
- Replace both `delay(...)` calls in `loop()` with `waterDelay(...)`: `waterDelay(2000);` in the sensor-failure branch and `waterDelay(1000);` at the end. Then the pump stops within a few milliseconds of its time, and not up to a second late. The stepper's `small_stepper.step(100)` still blocks for a moment, which is fine.

Lines starting with `#` are comments for the bridge, so `#WATER_START` and `#WATER_DONE` don't disturb the sensor readings.

## Try it

Upload, open Serial Monitor at 9600 baud with "Newline" line endings, and type `WATER=3`. You should see `#WATER_START 3`, hear the pump for 3 s, then see `#WATER_DONE 3`. `WATER=99` must print `#WATER_ERR over cap 30` and not start the pump. **Close the Serial Monitor before starting the bridge**, because only one program can hold the port.
