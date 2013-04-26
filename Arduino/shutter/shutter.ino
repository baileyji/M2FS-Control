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

#define RED_OPEN_US 1200
#define RED_PARTIAL_US 1900
#define RED_CLOSED_US 1929

#define BLUE_OPEN_US 1300
#define BLUE_PARTIAL_US 1950
#define BLUE_CLOSED_US 1973

//Pins
#define RED_IN_PIN      8  //Input
#define RED_SERVO_PIN   10 //Ouput

#define BLUE_IN_PIN     11  //Input
#define BLUE_SERVO_PIN  9  //Ouput


#include <Servo.h>
#include "position.h"


POSITION red_pos, blue_pos, 
         last_commanded_red, last_commanded_blue;

Servo redshutter, blueshutter;

unsigned long redDebounceTime, blueDebounceTime, redMoveTime, blueMoveTime;




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
}


void loop() {

  bool doBlueMove=false, doRedMove=false;
          
  POSITION commanded_red, commanded_blue;
  unsigned long bounce_time, sampleTime;

  //Sample the TTL lines for the shutters
  //  IN_PIN high -> Open Shutter (if open, do nothing)
  //  IN_PIN low -> Close Shutter (if closed, do nothing)
  sampleTime=millis();
  
  commanded_blue = digitalRead(BLUE_IN_PIN) ? OPEN:CLOSED;
  commanded_red  = digitalRead(RED_IN_PIN)  ? OPEN:CLOSED;

  //Debounce the inputs
  // If the commanded position is different from the last commanded position,
  //   then get the time to debounce the input (just in case).
  //   If the commanded position has remained constant for at least the debounce delay,
  ///then act on the commanded position
  
  bounce_time=sampleTime;
  if (commanded_blue != last_commanded_blue) {
    blueDebounceTime=sampleTime;
    last_commanded_blue=commanded_blue;
  }
  
  if (commanded_red != last_commanded_red) {
    redDebounceTime=sampleTime;
    last_commanded_red=commanded_red;
  }
  
  if (commanded_blue != blue_pos) {
      doBlueMove=(bounce_time - blueDebounceTime > DEBOUNCE_DELAY);
  }
  else {
      doBlueMove=false;
  }
  
  if (commanded_red != red_pos) {
      doRedMove=(bounce_time - redDebounceTime > DEBOUNCE_DELAY);
  }
  else {
      doRedMove=false;
  }
  
  //Move the shutters as requested
  
  if (doBlueMove && commanded_blue==OPEN) open_blue_shutter();
  if (doRedMove && commanded_red==OPEN) open_red_shutter();
  if (doRedMove && doBlueMove &&
      commanded_red==CLOSED && commanded_blue==CLOSED) {
      close_both_shutters();
  }
  else {
    if (doBlueMove && commanded_blue==CLOSED) close_blue_shutter();
    if (doRedMove && commanded_red==CLOSED) close_red_shutter();
  }
  
}

void open_red_shutter() {
    redshutter.writeMicroseconds(RED_OPEN_US);
    red_pos=OPEN;
}

void open_blue_shutter() {
    blueshutter.writeMicroseconds(BLUE_OPEN_US);
    blue_pos=OPEN;
}

void close_red_shutter() {
    redshutter.writeMicroseconds(RED_PARTIAL_US);
    delay(CLOSE_TIME_MS);
    redshutter.writeMicroseconds(RED_CLOSED_US);
    red_pos=CLOSED;
}

void close_blue_shutter() {
    blueshutter.writeMicroseconds(BLUE_PARTIAL_US);
    delay(CLOSE_TIME_MS);
    blueshutter.writeMicroseconds(BLUE_CLOSED_US);
    blue_pos=CLOSED;
}

void close_both_shutters() {
    redshutter.writeMicroseconds(RED_PARTIAL_US);
    blueshutter.writeMicroseconds(BLUE_PARTIAL_US);
    delay(CLOSE_TIME_MS);
    redshutter.writeMicroseconds(RED_CLOSED_US);
    blueshutter.writeMicroseconds(BLUE_CLOSED_US);
    red_pos=CLOSED;
    blue_pos=CLOSED;
}
