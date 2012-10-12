#include <SdFat.h>
#include <Tetris.h>
#include <AccelStepper.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <EEPROM.h>
#include "fibershoe_pins.h"

#define POWERDOWN_DELAY_US  1000
#define VERSION_STRING "Fibershoe v0.2"
#define DIRECTION_CW  LOW
#define DIRECTION_CCW HIGH
#define N_COMMANDS 25

//#define DEBUG

#define TEMP_UPDATE_INTERVAL_MS 20000
#define DS18B20_10BIT_MAX_CONVERSION_TIME_MS 188
#define DS18B20_12BIT_MAX_CONVERSION_TIME_MS 750

OneWire oneWire(ONE_WIRE_BUS);  // Instantiate a oneWire instance
DallasTemperature tempSensor(&oneWire);  // Instantiate Dallas Temp sensors on oneWire 
float lastTempReading=0;

Tetris tetris[8];
ArduinoOutStream cout(Serial);
char command_buffer[81];
unsigned char command_buffer_ndx=0;
unsigned char command_length=0;
bool have_command_to_parse=false;
bool leave_tetris_on_when_idle=false;

bool tempRetrieved=false;
unsigned long time_of_last_temp_request=0;
unsigned long time_since_last_temp_request=0xFFFFFFFF;

String commands[N_COMMANDS]={
  "AC",//set acceleration
  "AH",//Enable Active Holding (default disabled)
  "BL",//Define backlash
  "DH",//Drive to hardstop
  "DP",//Define current position as X
  "DS",//Disconnect Shoe, power off shoe, saving current position data no further commands will be accepted until shoe is reset
  "GH",//Get AH/PH status
  "MO",//Motor Off
  "PA",//Position absolute move, requires calibration or DP on multimove fails if any are uncalibrated
  "PC",//Print Commands
  "PH",//Passive holding
  "PR",//Position relative move
  "PV",//Print version String
  "SD",//Slit Defined Position, get the defined position of slit
  "SG",//Slit get Get the current slit for tetris 1-7,UNKNOWN,INTERMEDIATE,MOVING
  "SH",//turn motor on
  "SL",//Slit, move to position of slit, requires calibration or DP on multimove fails if any are uncalibrated
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
  DScommand,
  GHcommand,//Get AH/PH status
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
  powerUpTetrisShield,
  powerDownTetrisShield
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
  tempSensor.begin();
  tempSensor.setResolution(12);  //configure for 10bit, conversions take 187.5 ms max
  tempSensor.setWaitForConversion(false);
  
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
  
  loadMotorPositionsFromEEPROM();
  
  // Start serial connection
  Serial.begin(115200);
  
  //Boot assuming locking nut is disengaged
  boolean locking_screw_disengaged=true;
    
}

void loop() {

  // If the locking screw reads as disengaged...
  if (digitalRead(DISCONNECT_SHOE_PIN)){ 
    //and this is a state change... 
    if (!locking_screw_disengaged)
      // power down (NB DScommand() sets locking_screw_disengaged=true)
      DScommand();
  }
  else { //the screw reads as engaged
    //If this would be a state change...
    if (locking_screw_disengaged) {
      //debounce switch
      uint8_t i=200;
      while (!digitalRead(DISCONNECT_SHOE_PIN) && (i-- > 0) ) 
        delay(1);
      //If the locking screw is engaged power up and accept commands
      if (i==0) {
        locking_screw_disengaged=false;
        powerUpTetrisShield();
        delay(20); //Wait a short time for the vreg to stabilize
      }
    }
  }
  
  // Request and fetch the temperature regularly
  if (time_since_last_temp_request > TEMP_UPDATE_INTERVAL_MS) {
    tempSensor.requestTemperatures();
    time_of_last_temp_request=millis();
    tempRetrieved=false;
  }
  time_since_last_temp_request=millis()-time_of_last_temp_request;
  if(!tempRetrieved && time_since_last_temp_request > 
                        DS18B20_12BIT_MAX_CONVERSION_TIME_MS) {
    lastTempReading=tempSensor.getTempCByIndex(0);
    tempRetrieved=true;
  }
  
  // Handle command parsing
  if (have_command_to_parse) {
    #ifdef DEBUG
      printCommandBufNfo();
    #endif
    if (locking_screw_disengaged) {
      Serial.write("#Powered Down:\n");
    }
    else {
      bool commandGood=parseAndExecuteCommand();
      if (commandGood) Serial.write(":\n");
      else Serial.write("?\n");
    }
    have_command_to_parse=false;
    command_buffer_ndx=0;
  }
  
  // Call run on each tetris
  #ifdef DEBUG
    uint32_t t=micros();
  #endif
  for(int i=0;i<8;i++) tetris[i].run();
  #ifdef DEBUG
    uint32_t t1=micros();
    if(t%5 ==0) cout<<"Run took "<<t1-t<<" us.\n";
  #endif
  if (!locking_screw_disengaged) {
  
    if (stresscycles>0 && !tetris[0].moving()) {
      stresscycles--;
      if (tetris[0].currentPosition()==stressTopP)
        tetris[0].positionAbsoluteMove(stressBottomP);
      else
        tetris[0].positionAbsoluteMove(stressTopP);
    }
  
  //Do we leave the motors on while idle?
  if (!leave_tetris_on_when_idle) {
    for (unsigned char i=0; i<8; i++) 
      if (!tetris[i].moving()) tetris[i].motorOff();
  }

}

bool parseAndExecuteCommand() {
  if(command_length < 2) return false;
  char ndx=getCallbackNdxForCommand();
  if (ndx == -1 ) return false;
  return cmdFuncArray[ndx]();
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

bool DScommand() {
  //HOME AND HALT EVERYTHING
  powerDownTetrisShield();
  #ifdef DEBUG
    uint32_t t=millis();
  #endif
  saveMotorPositionsToEEPROM();
  #ifdef DEBUG
    uint32_t t1=millis();
    cout<<"Save to EEPROM took "<<t1-t<<" ms.\n";
  #endif
  locking_screw_disengaged=true;
  return true;
} 

void EEPROMwrite32bitval(uint16_t addr, uint32_t val) {
  EEPROM.write(addr++, (uint8_t) ((val)     & 0x000000FF));
  EEPROM.write(addr++, (uint8_t) ((val>>8)  & 0x000000FF));
  EEPROM.write(addr++, (uint8_t) ((val>>16) & 0x000000FF));
  EEPROM.write(addr,   (uint8_t) ((val>>24) & 0x000000FF));
}
uint32_t EEPROMread32bitval(uint16_t addr) {
  uint32_t returnVal=0;
  returnVal |= ((uint32_t) EEPROM.read(addr++));
  returnVal |= ((uint32_t) EEPROM.read(addr++)) <<8;
  returnVal |= ((uint32_t) EEPROM.read(addr++)) <<16;
  returnVal |= ((uint32_t) EEPROM.read(addr))   <<24;
  return returnVal;
}
void saveMotorPositionsToEEPROM() {
  for(uint8_t i=0;i<8;i++) {
    EEPROMwrite32bitval(4*i, tetris[i].currentPosition());
    EEPROMwrite32bitval(128+4*i, tetris[i].currentPosition());
  }
  EEPROM.write(32, 0x81); EEPROM.write(33, 0x81);
}
bool loadMotorPositionsFromEEPROM() {
  if(EEPROM.read(32)==0x81 && EEPROM.read(33)==0x81) {
    for(uint8_t i=0;i<8;i++){
      int32_t v1,v2;
      v1 = (int32_t) EEPROMread32bitval(4*i);
      v2 = (int32_t) EEPROMread32bitval(4*i+128);
      if (v1==v2) tetris[i].definePosition( v1 );;
    }
    EEPROM.write(32, 0);EEPROM.write(33, 0);
  }
}

#ifdef DEBUG
void printCommandBufNfo(){
  cout<<"Command Buffer Info";Serial.write('\n');
  cout<<"Buf ndx: "<<(unsigned int)command_buffer_ndx<<" Cmd len: "<<(unsigned int)command_length;Serial.write('\n');
  cout<<"Contents:";Serial.write((const uint8_t*)command_buffer,command_buffer_ndx);
  Serial.write('\n');
}
#endif

bool tetrisShieldIsPowered() {
  return digitalRead(TETRIS_MOTORS_POWER_ENABLE);
}

bool tetrisShieldIsR(){
  return digitalRead(R_SIDE_POLL_PIN);
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

bool powerDownTetrisShield() {
  if (tetrisShieldIsPowered()) {
    for(int i=0;i<8;i++) tetris[i].motorOff();
    delayMicroseconds(POWERDOWN_DELAY_US);
    digitalWrite(TETRIS_MOTORS_POWER_ENABLE,LOW);
  }
  return true;
}

bool powerUpTetrisShield() {
  if (!tetrisShieldIsPowered()){
    for(int i=0;i<8;i++) tetris[i].motorOff();
    delayMicroseconds(POWERDOWN_DELAY_US);
    digitalWrite(TETRIS_MOTORS_POWER_ENABLE,HIGH);
  }
  return true;
}

//Report whether the tetris are kept on when idle
bool GHcommand() {
  if (leave_tetris_on_when_idle) cout<<"ON";
  else cout<<"OFF";
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
//xxxxxx[shieldR][shieldOn] [t7on]...[t0on] [t7calib]...[t0calib] [t7moving]...[t0moving]
bool TScommand() {
  uint16_t statusBytes[4]={0,0,0,0};
  for (int i=0;i<8;i++) statusBytes[0]|=(tetris[i].moving()<<i);
  for (int i=0;i<8;i++) statusBytes[1]|=(tetris[i].isCalibrated()<<i);
  for (int i=0;i<8;i++) statusBytes[2]|=(tetris[i].motorIsOn()<<i);
  statusBytes[3]=(tetrisShieldIsR()<<1)|tetrisShieldIsPowered();
  cout<<statusBytes[3]<<" "<<statusBytes[2]<<" "<<statusBytes[1]<<" "<<statusBytes[0];
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
  powerUpTetrisShield();
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

  if (command_length==5) {//Set one slit (or all the slits to the same thing)

    unsigned char axis = getAxisForCommand();
    if ( axis >8 ) return false;

    unsigned char slit=convertCharToSlit(command_buffer[3]);
    if ( slit>6 ) return false;

    bool cont=true;
    if(axis==0) for(int i=0;i<8;i++) cont&=tetris[i].isCalibrated();
    else cont=tetris[axis-1].isCalibrated();
    if (!cont) return false;

    if(axis==0) for(int i=0;i<8;i++) if (tetris[i].moving()) return false;
    else if (tetris[axis-1].moving()) return false;

    if(axis==0) for(int i=0;i<8;i++) tetris[i].dumbMoveToSlit(slit);
    else tetris[axis-1].dumbMoveToSlit(slit);
  }
  else if (command_length==11) { //Set all the slits

    unsigned char slit[8];
    for (unsigned char i=0;i<8;i++) {
      slit[i]=convertCharToSlit(command_buffer[2+i]);
      if (slit[i]>6) return false;
    }
    
    bool cont=true;
    for(int i=0;i<8;i++) cont&=tetris[i].isCalibrated();
    if (!cont) return false;
    
    for(int i=0;i<8;i++) if (tetris[i].moving()) return false;

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
    if (!((command_buffer[4] >='0' && command_buffer[4]<='9') || 
      ((command_buffer[4] =='-' || command_buffer[4]=='+') && 
       command_buffer[5] >='0' && command_buffer[5]<='9' ))) return false;  
    long param=atol(command_buffer+4);

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

  if (!((command_buffer[3] >='0' && command_buffer[3]<='9') || 
      ((command_buffer[3] =='-' || command_buffer[3]=='+') && 
       command_buffer[4] >='0' && command_buffer[4]<='9' ))) return false;
  long param=atol(command_buffer+3);

  if(axis==0) for(int i=0;i<8;i++) if (tetris[i].moving()) return false;
  else if (tetris[axis-1].moving()) return false;

  if(axis==0) for(int i=0;i<8;i++) tetris[i].positionRelativeMove(param);
  else tetris[axis-1].positionRelativeMove(param);

  return true;
}

//Start a position absolute move
bool PAcommand() {
  unsigned char axis = getAxisForCommand();
  if ( axis >8 ) return false;

  if (!((command_buffer[3] >='0' && command_buffer[3]<='9') || 
      ((command_buffer[3] =='-' || command_buffer[3]=='+') && 
       command_buffer[4] >='0' && command_buffer[4]<='9' ))) return false;
  long param=atol(command_buffer+3);

  bool cont=false;
  if(axis==0) for(int i=0;i<8;i++) cont&=tetris[i].isCalibrated();
  else cont=tetris[axis-1].isCalibrated();
  if (!cont) return false;
  
  if(axis==0) for(int i=0;i<8;i++) if (tetris[i].moving()) return false;
  else if (tetris[axis-1].moving()) return false;

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

  if (!((command_buffer[3] >='0' && command_buffer[3]<='9') || 
      ((command_buffer[3] =='-' || command_buffer[3]=='+') && 
       command_buffer[4] >='0' && command_buffer[4]<='9' ))) return false;
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
  
  if(axis==0) for(int i=0;i<8;i++) if (tetris[i].moving()) return false;
  else if (tetris[axis-1].moving()) return false;
  
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
