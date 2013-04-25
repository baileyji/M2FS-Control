// Sweep
// by BARRAGAN <http://barraganstudio.com> 
// This example code is in the public domain.


#include <Servo.h> 
 
Servo myservo;  // create servo object to control a servo 
                // a maximum of eight servo objects can be created 
 
int pos = 0;    // variable to store the servo position 
 
void setup() 
{ 
  myservo.attach(10);  // attaches the servo on pin 9 to the servo object 
  Serial.begin(115200);
}

#define WAIT_DATA 100
//s = stop
//c = cycle
unsigned int delayOpen=350;     //m
unsigned int delayClose1=350;   //n
unsigned int openPos=1400;      //o
unsigned int closePos1=2000;    //p
unsigned int closePos2=2090;    //q

//B 1973

void loop() 
{ 

  if (Serial.available() ) {
    if (Serial.peek() == 'c'){
        Serial.read();
        delay(WAIT_DATA);
        int cycles=Serial.parseInt();
        while (cycles > 0) {
            cycles--;
            //Open
            myservo.writeMicroseconds(openPos);
            delay(delayOpen);
            //Close
            myservo.writeMicroseconds(closePos1);
            delay(delayClose1);
            myservo.writeMicroseconds(closePos2);
            
            delay(1000);
            if (Serial.peek() == 's') {
              Serial.read();
              cycles = 0;
            }
        }
    }
    else if (Serial.peek() == 'm'){
        Serial.read();
        delay(WAIT_DATA);
        delayOpen=Serial.parseInt();
    }
    else if (Serial.peek() == 'n'){
        Serial.read();
        delay(WAIT_DATA);
        delayClose1=Serial.parseInt();
    }
    else if (Serial.peek() == 'o'){
        Serial.read();
        delay(WAIT_DATA);
        openPos=Serial.parseInt();
    }
    else if (Serial.peek() == 'p'){
        Serial.read();
        delay(WAIT_DATA);
        closePos1=Serial.parseInt();
    }
    else if (Serial.peek() == 'q'){
        Serial.read();
        delay(WAIT_DATA);
        closePos2=Serial.parseInt();
    }
    else Serial.read();

  }
  

} 
