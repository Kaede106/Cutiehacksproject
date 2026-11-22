#include <DHT11.h>
#include <DHT.h>

#define DHTPIN 13
#define DHTTYPE DHT11

#define STEPS 32  // Number of steps per revolution of Internal shaft
#define E1 6      // Activer la broche pour le moteur
#define I1 4      // Axe de commande 1 pour moteur
#define I2 5      // Broche de commande 2 pour moteur
#define TEMP_SENSOR A1
#define LED 2
#define LEFTLED 12
#define RIGHTLED 3
#define MOTOR 4
#include "Stepper.h"
int Steps2Take;  // 2048 = 1 Revolution

const int SENSOR_PIN = A0;

// Replace these after calibrating your specific sensor:
const int DRY_VALUE = 590;  // Value read in open dry air
const int WET_VALUE = 280;  // Value read submerged in a cup of water

Stepper small_stepper(STEPS, 8, 10, 9, 11);

//DHT11 dht11(12);
DHT dht(DHTPIN, DHTTYPE);

void setup() {
  Serial.begin(9600);
  pinMode(LED, OUTPUT);
  pinMode(LEFTLED, OUTPUT);
  pinMode(RIGHTLED, OUTPUT);
  pinMode(MOTOR, OUTPUT);
  pinMode(E1, OUTPUT);
  pinMode(I1, OUTPUT);
  pinMode(I2, OUTPUT);
  dht.begin();
}

void loop() {
  int rawValue = analogRead(SENSOR_PIN);
  /*int temperature = dht11.readTemperature();

  // Check the result of the reading.
  // If there's no error, print the temperature value.
  // If there's an error, print the appropriate error message.
  if (temperature != DHT11::ERROR_CHECKSUM && temperature != DHT11::ERROR_TIMEOUT) {
    Serial.print("Temperature: ");
    Serial.print(temperature);
    Serial.println(" °C");
  } else {
    // Print error message based on the error code.
    Serial.println(DHT11::getErrorString(temperature));
  }
  Serial.print(temperature);*/

  float humidity = dht.readHumidity();
  float temperature = dht.readTemperature();

  if (isnan(humidity) || isnan(temperature)) {
    //Serial.println("Failed to read sensor");
    //delay(2000);
  } else {
    Serial.print("Temperature: ");
    Serial.print(temperature);
    Serial.println(" C");

    Serial.print("Humidity: ");
    Serial.print(humidity);
    Serial.println(" %");
  }


  // Convert raw value to a 0% - 100% scale and constrain bounds
  int moisturePercent = map(rawValue, DRY_VALUE, WET_VALUE, 0, 100);
  moisturePercent = constrain(moisturePercent, 0, 100);
  Serial.println(moisturePercent);
  if (moisturePercent > 50) {
    //digitalWrite(LED, LOW);
  } else {
    //digitalWrite(LED, HIGH);
  }
  small_stepper.setSpeed(500);  //Max seems to be 500
  Steps2Take = 100;             // Rotate CW
  small_stepper.step(Steps2Take);
  analogWrite(E1, 153);  // Courir à la moitié de la vitesse
  digitalWrite(I1, HIGH);
  digitalWrite(I2, LOW);

  if (Serial.available()) {
    String message = Serial.readStringUntil('\n');

    int separator = message.indexOf('|');

    String first = message.substring(0, separator);
    String second = message.substring(separator + 1);

    int prediction = first.toInt();
    int motorPosition = second.toInt();

    // Handle irrigation prediction
    if (prediction == 50) {
      // Turn on irrigation
      digitalWrite(LED, LOW);
      digitalWrite(MOTOR, LOW);
    } else {
      // Turn off irrigation
      digitalWrite(LED, HIGH);
      digitalWrite(MOTOR, HIGH);
    }

    if (motorPosition == 0) {
      // Move motor left
      digitalWrite(LEFTLED, HIGH);
      digitalWrite(RIGHTLED, LOW);
    } else if (motorPosition == 1) {
      // Move motor to middle
      digitalWrite(LEFTLED, LOW);
      digitalWrite(RIGHTLED, LOW);
    } else if (motorPosition == 2) {
      // Move motor right
      digitalWrite(LEFTLED, LOW);
      digitalWrite(RIGHTLED, HIGH);
    }
  }
  delay(1000);
}

/*#if 0
void loop()
{
  PORTF &= ~_BV(DHT11_PIN); //pull-down i/o pin from 18ms
  delay(18);
  PORTF |= _BV(DHT11_PIN);
  delay(40);
}
#endif
#if 1
void loop() {
  byte dht11_dat[5];
  byte dht11_in;
  byte i;
  // start condition
  // 1. pull-down i/o pin from 18ms
  PORTF &= ~_BV(DHT11_PIN);  // pull-down i/o pin from 18ms
  delay(18);
  PORTF |= _BV(DHT11_PIN);
  delayMicroseconds(40);
  DDRF &= ~_BV(DHT11_PIN);  //Set to input
  delayMicroseconds(40);
  dht11_in = PINF & _BV(DHT11_PIN);  //Read data line is high
  voltage if (dht11_in) {
    Serial.println("dht11 start condition 1 not met");
    return;
  }
  delayMicroseconds(80);
  dht11_in = PINF & _BV(DHT11_PIN);
  if (!dht11_in) {
    Serial.println("dht11 start condition 2 not met");
    return;
  }
  delayMicroseconds(80);
  // now ready for data reception
  for (i = 0; i < 5; i++)
    dht11_dat[i] = read_dht11_dat();
  DDRF |= _BV(DHT11_PIN);
  PORTF |= _BV(DHT11_PIN);
  byte dht11_check_sum = dht11_dat[0] + dht11_dat[1] + dht11_dat[2] + dht11_dat[3];
  // check check_sum
  if (dht11_dat[4] != dht11_check_sum) {
    Serial.println("DHT11 checksum error");
  }
  Serial.print("Current humdity = ");
  Serial.print(dht11_dat[0], DEC);
  Serial.print(".");
  Serial.print(dht11_dat[1], DEC);
  Serial.print("% ");
  Serial.print("temperature = ");
  Serial.print(dht11_dat[2], DEC);
  Serial.print(".");
  Serial.print(dht11_dat[3], DEC);
  Serial.println("C ");
  delay(2000);
}
#endif*/