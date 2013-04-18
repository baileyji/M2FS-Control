/*
 *  shutter_controller_v1.pde
 *  
 *
 *  Created by John Bailey on 10/28/09.
 *  GNU GPL v2.
 *
 */

#define DEBOUNCE_DELAY      50

#define BLUE_OPEN_ANGLE     58
#define BLUE_CLOSED_ANGLE   140
#define RED_OPEN_ANGLE      65
#define RED_CLOSED_ANGLE    145
 
//Pins
#define RED_IN_PIN      3  //Input
#define RED_SERVO_PIN   11 //Ouput

#define BLUE_IN_PIN     8  //Input
#define BLUE_SERVO_PIN  10  //Ouput


#include <Servo.h>
#include "position.h"


const POSITION BLUE_OPEN = { BLUE_OPEN_ANGLE, HIGH, LOW };
const POSITION BLUE_CLOSED = { BLUE_CLOSED_ANGLE, LOW, HIGH };
const POSITION RED_OPEN = { RED_OPEN_ANGLE, HIGH, LOW };
const POSITION RED_CLOSED = { RED_CLOSED_ANGLE, LOW, HIGH };


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
    
    move_red_shutter(RED_CLOSED);
    move_blue_shutter(BLUE_CLOSED);   

}


void loop() {

  bool red_in_signal, blue_in_signal,
       red_moved=false, blue_moved=false;
          
  POSITION commanded_red, commanded_blue;
  unsigned long bounce_time, sampleTime;

/* Read the signal pins to determine what is being commanded:
    IN_PIN high -> Open Shutter (if open, do nothing)
    IN_PIN low -> Close Shutter (if closed, do nothing)
*/

  blue_in_signal=digitalRead(BLUE_IN_PIN);
  red_in_signal=digitalRead(RED_IN_PIN);
  sampleTime=millis();

  
  if (blue_in_signal) commanded_blue=BLUE_OPEN;
  else                commanded_blue=BLUE_CLOSED;
  
  if (red_in_signal)  commanded_red=RED_OPEN;
  else                commanded_red=RED_CLOSED;

  
/* If the commanded position is different from the last commanded position,
  then get the time to debounce the input (just in case).
  If the commanded position has remained constant for at least the debounce delay,
  then act on the commanded position
*/ 
  if (commanded_blue.angle != last_commanded_blue.angle) {
    blueDebounceTime=sampleTime;
    last_commanded_blue=commanded_blue;
  }
  
  if (commanded_red.angle != last_commanded_red.angle) {
    redDebounceTime=sampleTime;
    last_commanded_red=commanded_red;
  }
  
  bounce_time=sampleTime;

  if (bounce_time - blueDebounceTime > DEBOUNCE_DELAY) {
    if (commanded_blue.angle != blue_pos.angle) {
      move_blue_shutter(commanded_blue);
      blue_moved=true;
    }
  }
  
  if (bounce_time - redDebounceTime > DEBOUNCE_DELAY) {
    if (commanded_red.angle != red_pos.angle) {
      move_red_shutter(commanded_red);
      red_moved=true;
    }
  }
  
}


void move_red_shutter(POSITION pos) {

    //Tell the shutter where to go
    redshutter.write(pos.angle);
    redMoveTime=millis();
    
    //Save the shutter's position
    red_pos=pos;
}

void move_blue_shutter(POSITION pos) {
    
    //Tell the shutter where to go
    blueshutter.write(pos.angle);
    blueMoveTime=millis();
    
    //Save the shutter's position
    blue_pos=pos;
}
