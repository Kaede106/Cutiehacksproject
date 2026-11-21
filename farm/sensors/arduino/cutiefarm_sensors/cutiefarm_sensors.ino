// CutieFarm sensors: reference sketch for an Arduino Uno (or any 5 V AVR board).
//
// Every INTERVAL_MS it sends one line over USB serial, for example
//   SOIL=612;T=22.4;H=55
// SOIL is the raw analogRead() value (0..1023). The laptop bridge turns it into a
// percentage using your calibration. T (deg C) and H (% RH) are only sent when a
// DHT sensor is enabled below and the read succeeds. Lines starting with # are
// comments. Protocol: farm/sensors/README.md.
//
// Flash: Arduino IDE > Tools > Board "Arduino Uno" > pick the port > Upload.
// Then CLOSE the Serial Monitor: only one program can hold the port.

// ---------------------------------------------------------------- settings

const unsigned long BAUD = 9600;
const unsigned long INTERVAL_MS = 2000;  // one line every 2 s (DHT22 needs >= 2 s)

const int SOIL_PIN = A0;        // soil sensor AOUT
const int SOIL_POWER_PIN = -1;  // -1: sensor VCC on the 5V pin, always powered.
                                // Or a digital pin (e.g. 7) feeding sensor VCC, so it is
                                // only powered while reading (slows corrosion of resistive probes).
const int SOIL_SAMPLES = 10;    // analogRead()s averaged per line

// Temperature and humidity: off by default, so the sketch needs no extra library.
// To enable: install "DHT sensor library" by Adafruit (Library Manager), set USE_DHT to 1
// and DHT_TYPE to DHT11 or DHT22 to match the part.
#define USE_DHT 0
#define DHT_TYPE DHT22
const int DHT_PIN = 2;

// Wind: not implemented yet, sends nothing. See readWind() below.
#define USE_WIND 0

// ---------------------------------------------------------------- code

#if USE_DHT
#include <DHT.h>
DHT dht(DHT_PIN, DHT_TYPE);
#endif

void setup() {
  Serial.begin(BAUD);
  if (SOIL_POWER_PIN >= 0) {
    pinMode(SOIL_POWER_PIN, OUTPUT);
    digitalWrite(SOIL_POWER_PIN, LOW);
  }
#if USE_DHT
  dht.begin();
#endif
  Serial.println(F("# cutiefarm_sensors v1"));
  Serial.print(F("# soil=A0 interval_ms="));
  Serial.print(INTERVAL_MS);
  Serial.print(F(" dht="));
  Serial.print(USE_DHT ? F("on") : F("off"));
  Serial.println(F(" wind=off"));
}

int readSoil() {
  if (SOIL_POWER_PIN >= 0) {
    digitalWrite(SOIL_POWER_PIN, HIGH);
    delay(100);  // let the sensor output settle
  }
  long sum = 0;
  for (int i = 0; i < SOIL_SAMPLES; i++) {
    sum += analogRead(SOIL_PIN);
    delay(5);
  }
  if (SOIL_POWER_PIN >= 0) {
    digitalWrite(SOIL_POWER_PIN, LOW);
  }
  return (int)(sum / SOIL_SAMPLES);
}

#if USE_WIND
// TODO(wind): the anemometer model is unknown. Typical options:
//  - pulse/reed-switch cup anemometer: count pulses on an interrupt pin over the
//    interval, then m/s = pulses_per_second * the datasheet factor;
//  - analog 0.4-2 V anemometer: map the voltage to m/s with the datasheet range.
// Return wind speed in m/s, or a negative number if there is no reading.
float readWind() {
  return -1.0;
}
#endif

void loop() {
  Serial.print(F("SOIL="));
  Serial.print(readSoil());

#if USE_DHT
  float t = dht.readTemperature();  // deg C
  float h = dht.readHumidity();     // % RH
  if (!isnan(t)) {
    Serial.print(F(";T="));
    Serial.print(t, 1);
  }
  if (!isnan(h)) {
    Serial.print(F(";H="));
    Serial.print(h, 0);
  }
#endif

#if USE_WIND
  float w = readWind();
  if (w >= 0) {
    Serial.print(F(";W="));
    Serial.print(w, 1);
  }
#endif

  Serial.println();
  delay(INTERVAL_MS);
}
