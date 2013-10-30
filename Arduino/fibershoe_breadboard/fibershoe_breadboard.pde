#define TETRIS_MOTORS_POWER_ENABLE 12

#define TETRIS_MOTOR_1_RESET       18
#define TETRIS_MOTOR_1_STANDBY     17
#define TETRIS_MOTOR_1_CWCCW       21
#define TETRIS_MOTOR_1_CK          20
#define TETRIS_MOTOR_1_ENABLE      19
#define TETRIS_MOTOR_1_PHASE_HOME  14  //input, requires pullup enabled

#define DIRECTION_CW  LOW
#define DIRECTION_CCW HIGH

/*
#define smillis() ((long)millis())
timeout=smillis()+1000;
boolean after(long timeout)
{
  return (smillis()-timeout)>0;
}
*/


#include <AccelStepper.h>

AccelStepper stepper1(1, TETRIS_MOTOR_1_CK, TETRIS_MOTOR_1_CWCCW);
int dir=1;



void setup() {
  
  //Vm power control pin
  digitalWrite(TETRIS_MOTORS_POWER_ENABLE, LOW);
  pinMode(TETRIS_MOTORS_POWER_ENABLE, OUTPUT);
  
  //Per TB6608 datasheet: STBY must be low @ pwr on/off 
  digitalWrite(TETRIS_MOTOR_1_STANDBY, LOW);
  digitalWrite(TETRIS_MOTOR_1_ENABLE, LOW);
  digitalWrite(TETRIS_MOTOR_1_RESET, LOW);

//  digitalWrite(TETRIS_MOTOR_1_CWCCW, DIRECTION_CW);  //don't care
//  digitalWrite(TETRIS_MOTOR_1_CK, LOW);
//  pinMode(TETRIS_MOTOR_1_CWCCW, OUTPUT);
//  pinMode(TETRIS_MOTOR_1_CK, OUTPUT);

  pinMode(TETRIS_MOTOR_1_ENABLE, OUTPUT);
  pinMode(TETRIS_MOTOR_1_RESET, OUTPUT);
  pinMode(TETRIS_MOTOR_1_STANDBY, OUTPUT);
  
  digitalWrite(TETRIS_MOTOR_1_PHASE_HOME, HIGH); //enable pullup
  pinMode(TETRIS_MOTOR_1_PHASE_HOME, INPUT);
  
  
  //These settings depend on the motor and the driver chip
  //Relevant info: 
  //  ADM0620 resonant freq (no load) - 170Hz
  //  Max driver step freq - 10kHz
  //  
  stepper1.setMinPulseWidth(50);   // in us 
  stepper1.setMaxSpeed(1000.0);    // steps/second
  stepper1.setSpeed(60.0);         // steps/second 
  stepper1.setAcceleration(100000.0); //
  
  Serial.begin(57600);
  establishContact();
}

boolean phaseStatus=LOW;
boolean oldPhaseStatus=LOW;
void loop() {
  char inByte;

  
  // if we get a valid byte, act accordingly
  if (Serial.available() > 0) {
    // get incoming byte:
    inByte = Serial.read();
    Serial.flush();
    switch(inByte) {
      case 'M':
        stepper1.move(dir*1280);
        break;
      case 'm':
        stepper1.move(dir*128);
        break;
      case '1':
        stepper1.move(dir);
        break;
      case 'O':
        stepper1.move(dir*24800);
        break;
      case 'R':
        toggleReset();
        printResetStatus();
        break;
      case 'E':
        toggleEnable();
        printEnableStatus();
        break;
      case 'S':
        toggleStandby();
        printStandbyStatus();
        break;
      case 'D':
        toggleDir();
        break;
      case 'V':
        toggleVm();
        printVmStatus();
        break;
      case 'X':
        stepper1.move(0);
        stepper1.setCurrentPosition(0);
        break;
      case 'C':
        printCommands();
        break;
      default:
        break;
    } 
  }
  

  phaseStatus=digitalRead(TETRIS_MOTOR_1_PHASE_HOME);
  if (phaseStatus != oldPhaseStatus) {
    //printPhaseHomeStatus();
    oldPhaseStatus=phaseStatus;
  }
  
  stepper1.run();
  
}


void toggleDir() {
  dir=-dir;
}

void toggleReset() {
  togglePin(TETRIS_MOTOR_1_RESET);
}

void toggleEnable() {
  togglePin(TETRIS_MOTOR_1_ENABLE);
}


void toggleStandby() {
  togglePin(TETRIS_MOTOR_1_STANDBY);
}

//Returns true if Vm was toggled
//Toggles Vm only if safeToToggleVm() is true
boolean toggleVm() {
  if (safeToToggleVm()) {
    togglePin(TETRIS_MOTORS_POWER_ENABLE);
    return true;
  }
  else 
    return false;
}


//Returns true if it is safe to enable/disable Vm
boolean safeToToggleVm() {
  if (standbyIsLow())
    return true;
  else
    return false; 
}


//Is the standby pin set low
boolean standbyIsLow() {
  return digitalRead(TETRIS_MOTOR_1_STANDBY)==LOW;
}

//Print the commands and wait for a response
void establishContact() {
  printCommands(); 
  while (Serial.available() <= 0);
}

//Print the command list
void printCommands() {
  Serial.println("Commands:");
  Serial.println("1280 steps:     M");
  Serial.println("128 steps:      m");
  Serial.println("1 step:         1");
  Serial.println("1 Revolution:   O");
  Serial.println("Toggle Reset:   R");
  Serial.println("Toggle Enable:  E");
  Serial.println("Toggle Standby: S");
  Serial.println("Toggle Dir:     D");
  Serial.println("Toggle Vm:      V");
  Serial.println("Cancel Move:    X");
  Serial.println("Reprint This:   C");
}


void printVmStatus() {
  Serial.print("Vm is ");
  if (digitalRead(TETRIS_MOTORS_POWER_ENABLE)==HIGH)
    Serial.println("HIGH.");
  else
    Serial.println("LOW.");
}

void printStandbyStatus() {
  Serial.print("STANDBY is ");
  if (digitalRead(TETRIS_MOTOR_1_STANDBY)==HIGH) 
    Serial.println("HIGH.");
  else
    Serial.println("LOW.");
}

void printEnableStatus() {
  Serial.print("ENABLE is ");
  if (digitalRead(TETRIS_MOTOR_1_ENABLE)==HIGH) 
    Serial.println("HIGH.");
  else
    Serial.println("LOW.");
}

void printResetStatus() {
  Serial.print("RESET is ");
  if (digitalRead(TETRIS_MOTOR_1_RESET)==HIGH) 
    Serial.println("HIGH.");
  else
    Serial.println("LOW.");
}

void printPhaseHomeStatus() {
  if (phaseStatus==HIGH) 
    Serial.println("Phase is not at home.");
  else
    Serial.println("Phase is at home.");
}

//Toggle the value of a pin
void togglePin(unsigned char pin) {
  digitalWrite(pin, !digitalRead(pin));
}
