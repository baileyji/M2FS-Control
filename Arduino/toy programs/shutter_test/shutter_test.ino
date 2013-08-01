// This example code is in the public domain.


#include <Servo.h> 

#define BLUE_SERVO_PIN  10  //Ouput  Blue is 10 red is 9
#define WAIT_DATA 100

Servo myservo;  // create servo object to control a servo 
                // a maximum of eight servo objects can be created 
 
int pos = 0;    // variable to store the servo position 
 
//s = stop
//c = cycle
unsigned int delayOpen=350;     //m
unsigned int delayClose1=150;   //n
unsigned int delayClose2=500;   //s
unsigned int openPos=1400;      //o
unsigned int closePos1=2080;    //p
unsigned int closePos2=2100;    //q
unsigned int closePos3=2100;    //r


//t stop
//u#### move to 


//B
//n150
//o1400
//p2020
//q2030 needs foam

//q1968


//R


//o1400
//p2060
//q2088

void setup() 
{ 
  pinMode(BLUE_SERVO_PIN, OUTPUT);
  myservo.attach(BLUE_SERVO_PIN);  // attaches the servo on pin 9 to the servo object 
  Serial.begin(115200);
}

void loop() 
{ 

  if (Serial.available() ) {
    if (Serial.peek() == 'c'){
        Serial.read();
        delay(WAIT_DATA);
        int cycles=Serial.parseInt();
        while (cycles > 0) {
            Serial.print("Cycles left: ");
            Serial.println(cycles);
            cycles--;
            //Open
            myservo.writeMicroseconds(openPos);
            delay(delayOpen);
            //Close
            myservo.writeMicroseconds(closePos1);
            delay(delayClose1);
            myservo.writeMicroseconds(closePos2);
            delay(delayClose2);
            myservo.writeMicroseconds(closePos3);
            delay(5000);
            if (Serial.peek() == 't') {
              Serial.read();
              cycles = 0;
            }
        }
    }
    else if (Serial.peek() == 'm'){
        Serial.read();
        delay(WAIT_DATA);
        delayOpen=Serial.parseInt();
        Serial.println(delayOpen);
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
    else if (Serial.peek() == 'r'){
        Serial.read();
        delay(WAIT_DATA);
        closePos3=Serial.parseInt();
    }
    else if (Serial.peek() == 's'){
        Serial.read();
        delay(WAIT_DATA);
        delayClose2=Serial.parseInt();
    }
    else if (Serial.peek() == 'u'){
        Serial.read();
        delay(WAIT_DATA);
        uint16_t moveto=Serial.parseInt();
        Serial.println(moveto);
        myservo.writeMicroseconds(moveto);
    }
    else Serial.read();

  }
  

} 
