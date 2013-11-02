/*
 *  shutter_controller_v1.pde
 *  
 *
 *  Created by John Bailey on 10/28/09.
 *  GNU GPL v2.
 *
 */

#define DEBOUNCE_DELAY   50

#define CLOSE_TIME_MS 350

#define CLOSED 0
#define OPEN 1

#define RED_OPEN_US 1400
#define RED_PARTIAL_US 2080
#define RED_CLOSED_US 2100

#define BLUE_OPEN_US 1250
#define BLUE_PARTIAL_US 2000
#define BLUE_CLOSED_US 2025

//Pins
#define RED_IN_PIN      11  //Input
#define RED_SERVO_PIN   9 //Ouput

#define BLUE_IN_PIN     8  //Input
#define BLUE_SERVO_PIN  10  //Ouput


#include <Servo.h>
#include "position.h"


POSITION red_pos, blue_pos, commanded_red, commanded_blue;

Servo redshutter, blueshutter;


bool redPinValue, bluePinValue, redPinValueLast, bluePinValueLast;


void setup() {
   
    pinMode(RED_IN_PIN, INPUT);
    pinMode(BLUE_IN_PIN, INPUT);
    digitalWrite(RED_IN_PIN, LOW);
    digitalWrite(BLUE_IN_PIN, LOW);
          
    pinMode(RED_SERVO_PIN, OUTPUT);
    pinMode(BLUE_SERVO_PIN, OUTPUT);
    
    redshutter.attach(RED_SERVO_PIN);
    blueshutter.attach(BLUE_SERVO_PIN);
    
    close_both_shutters();
    
    bluePinValue=digitalRead(BLUE_IN_PIN);
    redPinValue=digitalRead(RED_IN_PIN);
    bluePinValueLast=bluePinValue;
    redPinValueLast=redPinValue;
    
    Serial.begin(115200);
}


void loop() {

  bool doBlueMove=false, doRedMove=false;
  
  //Sample the TTL lines for the shutters, debounceing the inputs
  
  redPinValue=digitalRead(RED_IN_PIN);
  bluePinValue=digitalRead(BLUE_IN_PIN);
  if ( (bluePinValue != bluePinValueLast || redPinValue != redPinValueLast) &&
      !(bluePinValue != bluePinValueLast && redPinValue != redPinValueLast)) {
      delay(25);
      redPinValue=digitalRead(RED_IN_PIN);
      bluePinValue=digitalRead(BLUE_IN_PIN);
  }
  if (bluePinValue != bluePinValueLast ||
      redPinValue != redPinValueLast) {
      
      delay(DEBOUNCE_DELAY);
    
      bluePinValueLast=bluePinValue;
      redPinValueLast=redPinValue;
      bluePinValue=digitalRead(BLUE_IN_PIN);
      redPinValue=digitalRead(RED_IN_PIN);
    
      if (bluePinValueLast==bluePinValue )
        commanded_blue = bluePinValue ? OPEN:CLOSED;
      if (redPinValueLast==redPinValue )
        commanded_red = redPinValue ? OPEN:CLOSED;
      
  }

  //Do we need to move
  doBlueMove=(commanded_blue != blue_pos);
  doRedMove=(commanded_red != red_pos);

  //Move the shutters as requested
    if (doRedMove) {
        if (commanded_red==CLOSED) Serial.println("Close R");
        else Serial.println("Open R");
    }
    if (doBlueMove) {
        if (commanded_blue==CLOSED) Serial.println("Close B");
        else Serial.println("Open B");
    }
  
  if (doBlueMove && commanded_blue==OPEN) open_blue_shutter();
  if (doRedMove  && commanded_red==OPEN) open_red_shutter();
  if (doRedMove  && commanded_red==CLOSED &&
      doBlueMove && commanded_blue==CLOSED) {
      close_both_shutters();
  }
  else {
    if (doBlueMove && commanded_blue==CLOSED) close_blue_shutter();
    if (doRedMove && commanded_red==CLOSED) close_red_shutter();
  }

}

void open_red_shutter() {
Serial.println("opening R");
    redshutter.writeMicroseconds(RED_OPEN_US);
    red_pos=OPEN;
}

void open_blue_shutter() {
Serial.println("opening B");
    blueshutter.writeMicroseconds(BLUE_OPEN_US);
    blue_pos=OPEN;
}

void close_red_shutter() {
Serial.println("closing R");
    redshutter.writeMicroseconds(RED_PARTIAL_US);
    delay(CLOSE_TIME_MS);
    redshutter.writeMicroseconds(RED_CLOSED_US);
    red_pos=CLOSED;
}

void close_blue_shutter() {
Serial.println("closing B");
    blueshutter.writeMicroseconds(BLUE_PARTIAL_US);
    delay(CLOSE_TIME_MS);
    blueshutter.writeMicroseconds(BLUE_CLOSED_US);
    blue_pos=CLOSED;
}

void close_both_shutters() {
Serial.println("closing both");
    redshutter.writeMicroseconds(RED_PARTIAL_US);
    blueshutter.writeMicroseconds(BLUE_PARTIAL_US);
    delay(CLOSE_TIME_MS);
    redshutter.writeMicroseconds(RED_CLOSED_US);
    blueshutter.writeMicroseconds(BLUE_CLOSED_US);
    red_pos=CLOSED;
    blue_pos=CLOSED;
}
