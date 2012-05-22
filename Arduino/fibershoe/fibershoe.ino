#include <SdFat.h>
#include <Tetris.h>
#include <AccelStepper.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include "fibershoe_pins.h"

#define POWERDOWN_DELAY_US  1000
#define VERSION_STRING "Fibershoe v0.1"
#define DIRECTION_CW  LOW
#define DIRECTION_CCW HIGH
#define N_COMMANDS 23

OneWire oneWire(ONE_WIRE_BUS);  // Instantiate a oneWire instance
DallasTemperature tempSensors(&oneWire);  // Instantiate Dallas Temp sensors on oneWire 
float lastTempReading=0;

Tetris tetris[8];
ArduinoOutStream cout(Serial);
char command_buffer[81];
unsigned char command_buffer_ndx=0;
unsigned char command_length=0;
bool have_command_to_parse=false;
bool leave_tetris_on_when_idle=false;


String commands[N_COMMANDS]={
  "AC",//set acceleration
  "AH",//Enable Active Holding
  "BL",//Define backlash
  "DH",//Drive to hardstop
  "DP",//Define current position as X
  "MO",//Motor Off
  "PA",//Position absolute move
  "PC",//Print Commands
  "PH",//Passive holding
  "PR",//position relative move
  "PV",//Print version String
  "SD",//Slit Defined Position, get the defined position of slit
  "SG",//Slit get Get the current slit for tetris 1-7,UNKNOWN,INTERMEDIATE,MOVING
  "SH",//turn motor on
  "SL",//Slit, move to position of slit
  "SP",//set speed
  "SS",//Slit Set, define position of slit
  "ST",//Stop moving
  "TD",//Tell Step Position (# UKNOWN MOVING)
  "TE",//Report temp
  "TS",//Tell Status (e.g. moving vreg, etc)
  "VE",//Vreg Off
  "VO",//Vreg On
  };
bool (*cmdFuncArray[N_COMMANDS])() = {
  ACcommand,//set acceleration
  AHcommand,
  BLcommand,//Define backlash
  DHcommand,//Drive to hardstop
  DPcommand,//Define current position as X
  MOcommand,
  PAcommand,//Position absolute move
  PCcommand,
  PHcommand,
  PRcommand,//position relative move
  PVcommand,//Print version String
  SDcommand,//slit define, define position as slit position
  SGcommand,
  SHcommand,                
  SLcommand,//Slit, move to position of slit, 
  SPcommand,//set speed
  SScommand,
  STcommand,                
  TDcommand,                
  TEcommand,//Report temp
  TScommand,
  powereUpTetrisShield,
  powereDownTetrisShield
  };
  

void serialEvent() {
  char i, n_bytes_to_read;

  if(!have_command_to_parse) {
    n_bytes_to_read=Serial.available();
    if (command_buffer_ndx>79) //Something out of whack, reset buffer so new messages can be received
      command_buffer_ndx=0;
    if (n_bytes_to_read > 80-command_buffer_ndx)
      n_bytes_to_read=80-command_buffer_ndx;
    
    Serial.readBytes(command_buffer+command_buffer_ndx, n_bytes_to_read);
    i=command_buffer_ndx;
    command_buffer_ndx+=n_bytes_to_read;
    while (!have_command_to_parse && i<command_buffer_ndx) {
      have_command_to_parse=command_buffer[i]=='\n';
      i++;
    }
    if (have_command_to_parse) {
      command_length=i; //Length inclusive of null terminator
      command_buffer[command_length]=0;
    }
  }

}

void setup() {


  //Set up R vs. B side detection
  pinMode(R_SIDE_POLL_PIN,INPUT);
  digitalWrite(R_SIDE_POLL_PIN, LOW);
  pinMode(R_SIDE_POLL_DRIVER_PIN,OUTPUT);
  digitalWrite(R_SIDE_POLL_DRIVER_PIN, HIGH);
  
  //Set up shoe removal sensing
  pinMode(DISCONNECT_SHOE_PIN,INPUT);
  digitalWrite(DISCONNECT_SHOE_PIN,HIGH);
  
  //Set up temp sensor
  tempSensors.begin();
  tempSensors.setResolution(10);  //configure for 10bit, conversions take 187.5 ms max
  tempSensors.setWaitForConversion(false);
  
  //Vm power control pin
  digitalWrite(TETRIS_MOTORS_POWER_ENABLE, LOW);
  pinMode(TETRIS_MOTORS_POWER_ENABLE, OUTPUT);
  
  //Tetris Drivers
  tetris[0]=Tetris(TETRIS_1_RESET, TETRIS_1_STANDBY, TETRIS_1_DIR, 
    TETRIS_1_CK, TETRIS_1_PHASE_HOME);
  tetris[1]=Tetris(TETRIS_2_RESET, TETRIS_2_STANDBY, TETRIS_2_DIR, 
    TETRIS_2_CK, TETRIS_2_PHASE_HOME);
  tetris[2]=Tetris(TETRIS_3_RESET, TETRIS_3_STANDBY, TETRIS_3_DIR, 
    TETRIS_3_CK, TETRIS_3_PHASE_HOME);
  tetris[3]=Tetris(TETRIS_4_RESET, TETRIS_4_STANDBY, TETRIS_4_DIR, 
    TETRIS_4_CK, TETRIS_4_PHASE_HOME);
  tetris[4]=Tetris(TETRIS_5_RESET, TETRIS_5_STANDBY, TETRIS_5_DIR, 
    TETRIS_5_CK, TETRIS_5_PHASE_HOME);
  tetris[5]=Tetris(TETRIS_6_RESET, TETRIS_6_STANDBY, TETRIS_6_DIR, 
    TETRIS_6_CK, TETRIS_6_PHASE_HOME);
  tetris[6]=Tetris(TETRIS_7_RESET, TETRIS_7_STANDBY, TETRIS_7_DIR, 
    TETRIS_7_CK, TETRIS_7_PHASE_HOME);
  tetris[7]=Tetris(TETRIS_8_RESET, TETRIS_8_STANDBY, TETRIS_8_DIR, 
    TETRIS_8_CK, TETRIS_8_PHASE_HOME);
  
  Serial.begin(115200);
  
  //PCcommand();
}

void loop() {

  if (have_command_to_parse) {
    //printCommandBufNfo();
    bool commandGood=parseCommand();
    cout<<(commandGood ? ':':'?');
    Serial.write('\n');
    have_command_to_parse=false;
    command_buffer_ndx=0;
  }

  #ifdef DEBUG
    uint32_t t=micros();
  #endif
  
  if (digitalRead(DISCONNECT_SHOE_PIN)) {
    //HOME AND HALT EVERYTHING
    powereDownTetrisShield();
    saveMotorPositionsToEEPROM();
    while(1){
      Serial.print("#Powered Down\n");
      delay(2500);
    }
  }
  
  if (!leave_tetris_on_when_idle) {
    for (unsigned char i=0; i<8; i++) 
      if (!tetris[i].moving()) tetris[i].motorOff();
  }
  
  
  /*
  TODO sort this out
  if (time to update tempSensor) {
    tempSensors.requestTemperatures();
    start timer to read out temp sensor
  }
  if (time to read out temp sensor) {
    lastTempReading=tempSensors.getTempCByIndex(0)
  }
  */
  
  for(int i=0;i<8;i++) tetris[i].run();
  
  #ifdef DEBUG
    uint32_t t1=micros();
    if(t%5 ==0) cout<<"Run took "<<t1-t<<" us.\n";
  #endif
}

void saveMotorPositionsToEEPROM() {
  //TODO
}

void printCommandBufNfo(){
  cout<<"Command Buffer Info";Serial.write('\n');
  cout<<"Buf ndx: "<<(unsigned int)command_buffer_ndx<<" Cmd len: "<<(unsigned int)command_length;Serial.write('\n');
  cout<<"Contents:";Serial.write((const uint8_t*)command_buffer,command_buffer_ndx);
  Serial.write('\n');
}

bool parseCommand() {
  if(command_length >= 2) {
    char ndx;
    ndx=getCallbackNdxForCommand();
    if (ndx !=-1 ) return cmdFuncArray[ndx]();
    else return false;
  }
} 

bool tetrisShieldIsPowered() {
  return digitalRead(TETRIS_MOTORS_POWER_ENABLE);
}

bool tetrisShieldIsR(){
  return digitalRead(R_SIDE_POLL_PIN);
}

// Search through commands for a string that matches c and 
//return the index, -1 if not found
char getCallbackNdxForCommand() {
  String command;
  command+=command_buffer[0];
  command+=command_buffer[1];
  for (char i=0;i<N_COMMANDS;i++) if (commands[i]==command) return i;
  return -1;
}

//Parse the command for the axis designator
// 0 all axes, 1-8, or 0xFF for bad axis ID
unsigned char getAxisForCommand() {
  char axis=command_buffer[2];
  if (axis =='*' || (axis>= 'A' && axis <='H')) {
    axis = (axis =='*') ? 0:(axis-'A'+1);
  }
  else
    axis=0xFF;
  return axis;
}

bool powereDownTetrisShield() {
  for(int i=0;i<8;i++) tetris[i].motorOff();
  delayMicroseconds(POWERDOWN_DELAY_US);
  digitalWrite(TETRIS_MOTORS_POWER_ENABLE,LOW);
  return true;
}

bool powereUpTetrisShield() {
  for(int i=0;i<8;i++) tetris[i].motorOff();
  delayMicroseconds(POWERDOWN_DELAY_US);
  digitalWrite(TETRIS_MOTORS_POWER_ENABLE,HIGH);
  return true;
}

//Disable tetris on when idle
// by setting flag, main loop turns off drivers if motor isnt moving
// tetris turns on motor automatically for move
bool PHcommand() {
  leave_tetris_on_when_idle=false;
  return true;
}

//Keep tetris on when idle
// by setting flag, main loop turns off drivers if motor isnt moving
// tetris turns on motor automatically for move
bool AHcommand() {
  leave_tetris_on_when_idle=true;
  return true;
}

//Report the current slit for specified tetris: 1-7,UNKNOWN,INTERMEDIATE,MOVING
bool SGcommand() {
  unsigned char axis = getAxisForCommand();
  if ( axis >8 ) return false;
  
  if (axis==0) for(int i=0;i<8;i++) {
    
    if(tetris[i].moving()) cout<<"MOVING";
    else if (!tetris[i].isCalibrated()) cout<<"UNKNOWN";
    else {
      char slit=tetris[i].getCurrentSlit();
      if (slit>=0) cout<<slit+1;
      else cout<<"INTERMEDIATE";
    }
    if(i<7) cout<<", ";
  }
  else {
    if(tetris[axis-1].moving()) cout<<"MOVING";
    else if (!tetris[axis-1].isCalibrated()) cout<<"UNKNOWN";
    else {
      char slit=tetris[axis-1].getCurrentSlit();
      if (slit>=0) cout<<slit+1;
      else cout<<"INTERMEDIATE";
    }
  }
  
  
  
  return true;
}


//Report the nominial position of the specified slit
bool SDcommand() {
  unsigned char axis = getAxisForCommand();
  if ( axis >8 ) return false;

  unsigned char slit=convertCharToSlit(command_buffer[3]);
  if ( slit>6 ) return false;

  if (axis==0) for(int i=0;i<8;i++) {
    tetris[i].tellSlitPosition(slit);
    if(i<7) cout<<", ";
  }
  else {
    tetris[axis-1].tellSlitPosition(slit);
  }
  
  return true;
}

//Report the status (e.g vreg, moving, etc)
//xxxxxx[shieldR][shieldOn] [t7on]...[t0on] [t7moving]...[t0moving]
bool TScommand() {
  uint16_t statusBytes[3]={0,0,0};
  for (int i=0;i<8;i++) statusBytes[0]|=(tetris[i].moving()<<i);
  for (int i=0;i<8;i++) statusBytes[1]|=(tetris[i].motorIsOn()<<i);
  statusBytes[2]=(tetrisShieldIsR()<<1)|tetrisShieldIsPowered();
  cout<<statusBytes[2]<<" "<<statusBytes[1]<<" "<<statusBytes[0];
  
  return true;
}


//Turn a tetris motor (or all motors) off
bool MOcommand(){
  unsigned char axis = getAxisForCommand();
  if ( axis >8 ) return false;
  
  if(axis==0) for(int i=0;i<8;i++) tetris[i].motorOff();
  else tetris[axis-1].motorOff();
  return true;
}

// Get currrent position/moving/unknown
bool TDcommand(){
  
  unsigned char axis = getAxisForCommand();
  if ( axis >8 ) return false;
  
  if (axis==0) for(int i=0;i<8;i++) {
    if (tetris[i].moving())
      cout<<"MOVING";
    else if (! tetris[i].isCalibrated())
      cout<<"UNKNOWN";
    else
      tetris[i].tellPosition(); 
    if(i<7) cout<<", ";
  }
  else {
    if (tetris[axis-1].moving())
      cout<<"MOVING";
    else if (!tetris[axis-1].isCalibrated())
      cout<<"UNKNOWN";
    else
      tetris[axis-1].tellPosition();
  }
  
  return true;
}

//Stop motion of a tetris
bool STcommand(){
  unsigned char axis = getAxisForCommand();
  if ( axis >8 ) return false;
  if(axis==0) for(int i=0;i<8;i++) tetris[i].stop();
  else tetris[axis-1].stop();
  return true;
}

//Turn on a tetris
bool SHcommand(){
  unsigned char axis = getAxisForCommand();
  if ( axis >8 ) return false;

  if(axis==0) for(int i=0;i<8;i++) tetris[i].motorOn();
  else tetris[axis-1].motorOn();
  return true;
}

//Set the backlash
bool BLcommand() {
  unsigned char axis = getAxisForCommand();
  if ( axis >8 ) return false;

  if (!(command_buffer[3] >='0' && command_buffer[3]<='9')) return false;  
  unsigned long param=atol(command_buffer+3);

  
  if(axis==0) for(int i=0;i<8;i++) tetris[i].setBacklash(param);
  else tetris[axis-1].setBacklash(param);

  return true;
}

//Move to a nominal slit position
bool SLcommand() {

  if (command_length==4) {//Set one slit (or all the slits to the same thing)
    unsigned char axis = getAxisForCommand();
    if ( axis >8 ) return false;
    
    unsigned char slit=convertCharToSlit(command_buffer[3]);
    if ( slit>6 ) return false;

    if(axis==0) for(int i=0;i<8;i++) tetris[i].dumbMoveToSlit(slit);
    else tetris[axis-1].dumbMoveToSlit(slit);
  }
  else if (command_length==10) { //Set all the slits

    unsigned char slit[8];
    for (unsigned char i=0;i<8;i++) {
      slit[i]=convertCharToSlit(command_buffer[2+i]);
      if (slit[i]>6) return false;
    }
    
    for (unsigned char i=0;i<8;i++)
      tetris[i].dumbMoveToSlit(slit[i]);  
  }
  else return false;
  
  return true;
}

//Convert a chanracter to a slit number
unsigned char convertCharToSlit(char c) {
  return c-'0'-1; //(-1 as slit is specified 1-7)
}

//Define a nominal slit position
bool SScommand() {
  unsigned char axis = getAxisForCommand();
  if ( axis>8 ) return false;

  unsigned char slit=convertCharToSlit(command_buffer[3]);
  if ( slit>6 ) return false;

  if (command_length >4){
    if (!(command_buffer[4] >='0' && command_buffer[4]<='9')) return false;  
    unsigned long param=atol(command_buffer+4);

    if(axis==0) for(int i=0;i<8;i++) tetris[i].defineSlitPosition(slit,param);
    else tetris[axis-1].defineSlitPosition(slit,param);
  }
  else {
    if(axis==0) for(int i=0;i<8;i++) tetris[i].defineSlitPosition(slit);
    else tetris[axis-1].defineSlitPosition(slit);
  }
  return true;
}

//Start a position relative move
bool PRcommand() {
  unsigned char axis = getAxisForCommand();
  if ( axis >8 ) return false;

  if (!(command_buffer[3] >='0' && command_buffer[3]<='9')) return false;  
  long param=atol(command_buffer+3);


  if(axis==0) for(int i=0;i<8;i++) tetris[i].positionRelativeMove(param);
  else tetris[axis-1].positionRelativeMove(param);

  return true;
}

//Start a position absolute move
bool PAcommand() {
  unsigned char axis = getAxisForCommand();
  if ( axis >8 ) return false;

  if (!(command_buffer[3] >='0' && command_buffer[3]<='9')) return false;  
  long param=atol(command_buffer+3);


  if(axis==0) for(int i=0;i<8;i++) tetris[i].positionAbsoluteMove(param);
  else tetris[axis-1].positionAbsoluteMove(param);

  return true;
}

//Report the version string
bool PVcommand() {
  cout<<VERSION_STRING;
  return true;
}

//Report the last temp reading
bool TEcommand() {
  cout<<lastTempReading;
  return true;
}

//Define the nominal position
bool DPcommand() {
  unsigned char axis = getAxisForCommand();
  if ( axis >8 ) return false;

  if (!(command_buffer[3] >='0' && command_buffer[3]<='9')) return false;  
  long param=atol(command_buffer+3);


  if(axis==0) for(int i=0;i<8;i++) tetris[i].definePosition(param);
  else tetris[axis-1].definePosition(param);

  return true;
}

//Define the step speed
bool SPcommand() {
  unsigned char axis = getAxisForCommand();
  if ( axis >8 ) return false;

  if (!(command_buffer[3] >='0' && command_buffer[3]<='9')) return false;  
  unsigned long param=atol(command_buffer+3);


  if(axis==0) for(int i=0;i<8;i++) tetris[i].setSpeed(param);
  else tetris[axis-1].setSpeed(param);

  return true;
}


//Define the acceleration rate
bool ACcommand() {
  unsigned char axis = getAxisForCommand();
  if ( axis >8 ) return false;
  
  if (!(command_buffer[3] >='0' && command_buffer[3]<='9')) return false;  
  unsigned long param=atol(command_buffer+3);

  if(axis==0) for(int i=0;i<8;i++) tetris[i].setAcceleration(param);
  else tetris[axis-1].setAcceleration(param);

  return true;
}


//Calibrate the tetris
bool DHcommand() {
  unsigned char axis = getAxisForCommand();
  if ( axis >8 ) return false;
 
  if(axis==0) for(int i=0;i<8;i++) tetris[i].calibrateToHardStop();
  else tetris[axis-1].calibrateToHardStop();

  return true;
}


//Print the commands
bool PCcommand() {
  cout<<"#PC   Print Commands - Print the list of commands";Serial.write('\n');
  cout<<"#VO   Voltage Off - Power down the tetris motors";Serial.write('\n');
  cout<<"#VE   Voltage Enable - Power up the motor supply";Serial.write('\n');
  cout<<"#TS   Tell Status - Tell the status bytes";Serial.write('\n');
  
  cout<<"#TDx  Tell Position - Tell position of tetris x in microsteps";Serial.write('\n');
  cout<<"#SHx  Servo Here - Turn on tetris x";Serial.write('\n');
  cout<<"#MOx  Motor Off - Turn off motor in tetris x";Serial.write('\n');
  cout<<"#STx  Stop - Stop motion of tetris x";Serial.write('\n');
  
  cout<<"#DPx# Define Position - Define the current position of tetris x to be #";Serial.write('\n');
  cout<<"#PAx# Position Absolute - Command tetris x to move to position #";Serial.write('\n');
  cout<<"#PRx# Position Relative - Command tetris x to move #";Serial.write('\n');
  cout<<"#SPx# Speed - Set the movement speed of tetris x to # (usteps/s)";Serial.write('\n');
  cout<<"#ACx# Acceleration - Set the acceleration rate of tetris x to # (usteps/s^2)";Serial.write('\n');
  cout<<"#SLx# Slit - Command tetris x to go to the position of slit #";Serial.write('\n');
  cout<<"#SDx# Slit Define - Set slit # for tetris x to be at the current position";Serial.write('\n');
  cout<<"#BLx# Backlash - Set the amount of backlash of tetris x to # (usteps)";Serial.write('\n');
  return true;
}
