/*
  Dimmer
 
 Demonstrates the sending data from the computer to the Arduino board,
 in this case to control the brightness of an LED.  The data is sent
 in individual bytes, each of which ranges from 0 to 255.  Arduino
 reads these bytes and uses them to set the brightness of the LED.
 
 The circuit:
 LED attached from digital pin 9 to ground.
 Serial connection to Processing, Max/MSP, or another serial application
 
 created 2006
 by David A. Mellis
 modified 30 Aug 2011
 by Tom Igoe and Scott Fitzgerald
 
 This example code is in the public domain.
 
 http://www.arduino.cc/en/Tutorial/Dimmer
 
 */

#define LED_PIN 9
#define RELAY_PIN 7
byte brightness;

void setup()
{
  // initialize the serial communication:
  Serial.begin(115200);
  // initialize the ledPin as an output:
  pinMode(LED_PIN, OUTPUT);
  pinMode(RELAY_PIN, OUTPUT);
  brightness=0;
}

void loop() {

  // check if data has been sent from the computer:
  if (Serial.available()) {
    // read the most recent byte (which will be from 0 to 255):
    brightness = Serial.read();
    if (brightness == 0) digitalWrite(RELAY_PIN, LOW);
    else digitalWrite(RELAY_PIN, HIGH);
    // set the brightness of the LED:
    analogWrite(LED_PIN, brightness);
  }
}
