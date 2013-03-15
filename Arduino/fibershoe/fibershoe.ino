#include <SdFat.h>
#include <Tetris.h>
#include <AccelStepper.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <EEPROMEx.h>
#include "fibershoe_pins.h"

#define POWERDOWN_DELAY_US  1000
#define LOCKING_SCREW_ENGAGE_DEBOUNCE_TIME_MS 200
#define VERSION_STRING "Fibershoe v0.7"
#define DIRECTION_CW  LOW
#define DIRECTION_CCW HIGH
#define N_COMMANDS 27

//#define DEBUG
//#define DEBUG_EEPROM
//#define DEBUG_RUN_TIME

#define TEMP_UPDATE_INTERVAL_MS 20000
#define DS18B20_10BIT_MAX_CONVERSION_TIME_MS 188
#define DS18B20_12BIT_MAX_CONVERSION_TIME_MS 750

//EEPROM Addresses
#define EEPROM_LAST_SAVED_POSITION_CRC16_ADDR       0x0000
#define EEPROM_LAST_SAVED_POSITION_ADDR             0x0002

#define EEPROM_SLIT_POSITIONS_CRC16_ADDR            0x0080
#define EEPROM_SLIT_POSITIONS_ADDR                  0x0082
#define N_SLIT_POSITIONS                            (N_TETRI*7)

#pragma mark Globals

OneWire oneWire(ONE_WIRE_BUS);  // Instantiate a oneWire instance
DallasTemperature tempSensor(&oneWire);  //Instantiate temp sensor on oneWire 
ArduinoOutStream cout(Serial);

//The tetri
#define N_TETRI 8
Tetris tetris[N_TETRI];

//Command buffer
char command_buffer[81];
unsigned char command_buffer_ndx=0;
unsigned char command_length=0;
bool have_command_to_parse=false;

//Temp monitoring
float lastTempReading=0;
bool tempRetrieved=false;
unsigned long time_of_last_temp_request=0;
unsigned long time_since_last_temp_request=0xFFFFFFFF;

//Stress testing
unsigned long stresscycles=0;
long stressBottomP=0;
long stressTopP=0;

//Power state management
bool locking_screw_disengaged=true; //Boot assuming locking nut is disengaged
bool shoeOnline=false; //Always boot in offline mode

//Defaults
bool leave_tetris_on_when_idle=true; //Activehold default

//Commands
typedef struct {
    String name;
    bool (*callback)();
    const bool allowOffline;
} Command;

const Command commands[N_COMMANDS]={
    //Set acceleration
    {"AC", ACcommand, true},
    //Enable active holding (default is set by leave_tetris_on_when_idle)
    {"AH", AHcommand, false},
    //Define backlash
    {"BL", BLcommand, true},
    //Connect Shoe restore slit positions and eanble all commands
    {"CS", CScommand, true},
    //Cycle tetris A N times from stressBottomP to stressTopP
    {"CY", CYcommand, false},
    //Drive to hardstop
    {"DH", DHcommand, false},
    //Define current position as X
    {"DP", DPcommand, false},
    //Disconnect Shoe, power off tetris shield save current position data
    //  and disable motion & shield power commands
    {"DS", DScommand, true},
    //Get activehold status
    {"GH", GHcommand, true},
    //Turn motor(s) off
    {"MO", MOcommand, false},
    //Position absolute move, 
    {"PA", PAcommand, false},
    //Print Commands
    {"PC", PCcommand, true},
    //Passive holding
    {"PH", PHcommand, false},
    //Position relative move
    {"PR", PRcommand, false},
    //Print version String
    {"PV", PVcommand, true},
    //Slit Defined Position, get the defined position of slit
    {"SD", SDcommand, true},
    //Slit Get. Get the current slit for tetris(i) 1-7,UNKNOWN,INTERMEDIATE,MOVING
    {"SG", SGcommand, false},
    //Turn motor(s) on
    {"SH", SHcommand, false},
    //Slit, move to position of slit, requires tetris be calibrated with DH or DP
    // If moving multiple, fails for all if any are uncalibrated
    {"SL", SLcommand, false},
    //set speed
    {"SP", SPcommand, false},
    //Slit Set, define position of slit
    {"SS", SScommand, true},
    //Stop moving
    {"ST", STcommand, false},
    //Tell Step Position (# UKNOWN MOVING)
    {"TD", TDcommand, false},
    //Report temperature
    {"TE", TEcommand, true},
    //Tell Status (e.g. moving vreg, etc)
    {"TS", TScommand, true},
    //Tetris shield Vreg on
    {"VE", enableTetrisVreg, false},
    //Tetris shield Vreg off
    {"VO",disableTetrisVreg, false}
};

#pragma mark Serial Event Handler

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

#pragma mark Setup & Loop

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
    tempSensor.setResolution(12);
    tempSensor.setWaitForConversion(false);

    //Define shield power supply enable/disable control pin
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

    //Restore the nominal slit positions from EEPROM

    
    // Start serial connection
    Serial.begin(115200);
    
    loadSlitPositionsFromEEPROM();

}

//Main loop, funs forever at full steam ahead
void loop() {

    monitorLockingNutState();
    
    monitorTemperature();

    //If the command received flag is set
    if (have_command_to_parse) {
        #ifdef DEBUG
            printCommandBufNfo();
        #endif

        //Find command in commands
        int8_t ndx=getCallbackNdxForCommand();
        
        //If not a command respond error
        if (ndx == -1 ) Serial.write("?\n");
        else {
            //Ensure stresscycles=0 if command is not CY
            if (commands[ndx].name == "CY")
                stresscycles=0;
            
            #ifdef DEBUG
                cout<<"Shoe is "<<(shoeOnline ? "ON":"OFF")<<endl;
                cout<<"Command is ";Serial.println(commands[ndx].name);
            #endif
            
            //Execute the command or respond shoe is offline
            if (!shoeOnline && !commands[ndx].allowOffline) {
                cout<<"Powered Down"<<endl<<":";
            }
            else {
                bool commandGood;
                
                commandGood=commands[ndx].callback();
                
                if (commandGood) Serial.write(":");
                else Serial.write("?");
            }
        }
        //Reset the command buffer and the command received flag
        have_command_to_parse=false;
        command_buffer_ndx=0;
    }
  
    if (shoeOnline) {
        shoeOnlineMain();
    }

}

#pragma mark Helper Functions


//Search through command names for a name that matches the first two
// characters received return the index of that command.
// Return -1 if not found or fewer than two characters received. 
int8_t getCallbackNdxForCommand() {
    //Extract the command from the command_buffer
    String name;
    if(command_length >= 2) {
        name+=command_buffer[0];
        name+=command_buffer[1];
        for (uint8_t i=0; i<N_COMMANDS;i++)
            if (commands[i].name==name)
                return i;
    }
    return -1;
}

//Convert a character to a slit number. '1' becomes 0, '2' 1, ...
unsigned char convertCharToSlit(char c) {
    return c-'0'-1; //(-1 as slit is specified 1-7)
}

//Request and fetch the temperature regularly, ignore rollover edgecase
void monitorTemperature() {
    
    if (time_since_last_temp_request > TEMP_UPDATE_INTERVAL_MS) {
        tempSensor.requestTemperatures();
        time_of_last_temp_request=millis();
        tempRetrieved=false;
    }
    
    time_since_last_temp_request=millis()-time_of_last_temp_request;
    
    if(!tempRetrieved &&
       time_since_last_temp_request >
                        DS18B20_12BIT_MAX_CONVERSION_TIME_MS) {
        lastTempReading=tempSensor.getTempCByIndex(0);
        tempRetrieved=true;
    }
}

/* 
Read the digital input for the locking nut,
If the state changes to engaged, debounce the pin (routine will block for
LOCKING_SCREW_ENGAGE_DEBOUNCE_TIME_MS) and update the locking nut state.
If the state changes to disengaged, update the state immediately and put
the shoe into offline mode by calling DScommand.
*/
void monitorLockingNutState() {
    locking_screw_disengaged=false;return;
    // If the locking screw reads as disengaged...
    if (digitalRead(DISCONNECT_SHOE_PIN)){
        if (!locking_screw_disengaged) { //and this is a state change...
            //Enter offline mode
            DScommand();
            locking_screw_disengaged=true;
            #ifdef DEBUG
                cout<<"Locking screw disengaged.\n";
            #endif
        }
    }
    else { //the screw reads as engaged
        if (locking_screw_disengaged) { //and this is a state change...
            //Debounce switch
            uint8_t i=LOCKING_SCREW_ENGAGE_DEBOUNCE_TIME_MS;
            while (!digitalRead(DISCONNECT_SHOE_PIN) && (i-- > 1) ) delay(1);
            //If the locking screw is engaged power up and accept commands
            if (i==0) {
                locking_screw_disengaged=false;
                #ifdef DEBUG
                    cout<<"Locking screw reingaged.\n";
                #endif
            }
        }
    }
}


//Tasks to execute every main loop iteration when the shoe is online 
void shoeOnlineMain() {
    //Stress testing code
    if (stresscycles>0 && !tetris[0].moving()) {
        stresscycles--;
        for (char i=0;i<8;i++) {
          if (tetris[i].currentPosition()==stressTopP)
              tetris[i].positionAbsoluteMove(stressBottomP);
          else
              tetris[i].positionAbsoluteMove(stressTopP);
        }
    }
    //Call run on each tetris
    #ifdef DEBUG_RUN_TIME
        uint32_t t=micros();
    #endif
    for(int i=0;i<8;i++) tetris[i].run();
    #ifdef DEBUG_RUN_TIME
        uint32_t t1=micros();
        if((t1-t)>80) cout<<"Run took "<<t1-t<<" us.\n";
    #endif
    //More stress testing code
    if (stresscycles>0 && !tetris[0].moving() &&
        tetris[0].currentPosition()==stressBottomP) {
        cout<<"Cycle "<<(stresscycles+1)/2<<" finished.\n";
        delay(100);
    }
    //Do we leave the motors on while idle?
    if (!leave_tetris_on_when_idle) {
        for (unsigned char i=0; i<8; i++) {
            if (!tetris[i].moving())
                tetris[i].motorOff();
        }
    }
}



#ifdef DEBUG
void printCommandBufNfo(){
  cout<<"Command Buffer Info";Serial.write('\n');
  cout<<"Buf ndx: "<<(unsigned int)command_buffer_ndx<<" Cmd len: "<<(unsigned int)command_length;Serial.write('\n');
  cout<<"Contents:";Serial.write((const uint8_t*)command_buffer,command_buffer_ndx);
  cout<<"Axis:"<<(unsigned int)getAxisForCommand();
  Serial.write('\n');
}
#endif

bool tetrisVregIsEnabled() {
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

bool disableTetrisVreg() {
  if (tetrisVregIsEnabled()) {
    for(int i=0;i<8;i++) tetris[i].motorOff();
    delayMicroseconds(POWERDOWN_DELAY_US);
    digitalWrite(TETRIS_MOTORS_POWER_ENABLE,LOW);
  }
  return true;
}

bool enableTetrisVreg() {
  if (!tetrisVregIsEnabled()){
    for(int i=0;i<8;i++) tetris[i].motorOff();
    delayMicroseconds(POWERDOWN_DELAY_US);
    digitalWrite(TETRIS_MOTORS_POWER_ENABLE,HIGH);
  }
  return true;
}

#pragma mark Command Handlers

bool CScommand() {
    //Come online if the locking nut is engaged
    if (locking_screw_disengaged)
        return false;
    else {
        if (!shoeOnline) {
            shoeOnline=true;
            loadMotorPositionsFromEEPROM();
            enableTetrisVreg();
            delay(20); //Wait a short time for the vreg to stabilize
        }
        return true;
    }
}

bool DScommand() {
    //Powerdown and store positions (if online)
    if (shoeOnline) {
        disableTetrisVreg();
        saveMotorPositionsToEEPROM();
        shoeOnline=false;
    }
    return true;
}


//Report whether the tetris are kept on when idle
bool GHcommand() {
  if (leave_tetris_on_when_idle) cout<<"ON"<<endl;
  else cout<<"OFF"<<endl;
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
    else if (!tetris[i].isCalibrated()) { cout<<"UNKNOWN"; }
    else {
      char slit=tetris[i].getCurrentSlit();
      if (slit>=0) cout<<slit+1;
      else cout<<"INTERMEDIATE";
    }
    if(i<7) cout<<", ";
  }
  else {
    if(tetris[axis-1].moving()) cout<<"MOVING";
    else if (!tetris[axis-1].isCalibrated()) { cout<<"UNKNOWN"; }
    else {
      char slit=tetris[axis-1].getCurrentSlit();
      if (slit>=0) cout<<slit+1;
      else cout<<"INTERMEDIATE";
    }
  }
  cout<<endl;
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
  cout<<endl;
  return true;
}

//Report the 4 status bytes (e.g vreg, moving, etc)
//xxxxx[shoeOnline][shieldR][shieldOn]
//[t7on]...[t0on]
//[t7calib]...[t0calib]
//[t7moving]...[t0moving]
bool TScommand() {
  uint16_t statusBytes[4]={0,0,0,0};
  for (int i=0;i<8;i++) statusBytes[0]|=(tetris[i].moving()<<i);
  for (int i=0;i<8;i++) statusBytes[1]|=(tetris[i].isCalibrated()<<i);
  for (int i=0;i<8;i++) statusBytes[2]|=(tetris[i].motorIsOn()<<i);
  statusBytes[3]=(shoeOnline<<2)|(tetrisShieldIsR()<<1)|tetrisVregIsEnabled();
  cout<<statusBytes[3]<<" "<<statusBytes[2]<<" ";
  cout<<statusBytes[1]<<" "<<statusBytes[0]<<endl;
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
  
  if (axis==0) {for(int i=0;i<8;i++) {
    if (tetris[i].moving())
      cout<<"MOVING";
    else if (! tetris[i].isCalibrated())
      cout<<"UNKNOWN";
    else
      tetris[i].tellPosition(); 
    if(i<7) cout<<", ";
  }}
  else {
    if (tetris[axis-1].moving())
      cout<<"MOVING";
    else if (!tetris[axis-1].isCalibrated())
      cout<<"UNKNOWN";
    else
      tetris[axis-1].tellPosition();
  }
  cout<<endl;
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
  enableTetrisVreg();
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
    
    if(axis==0) for(int i=0;i<8;i++) {if (!tetris[i].isCalibrated()) return false;}
    else if (!tetris[axis-1].isCalibrated()) return false;

    if(axis==0) for(int i=0;i<8;i++) {if (tetris[i].moving()) return false;}
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
    
    for(int i=0;i<8;i++) {if (!tetris[i].isCalibrated()) return false;}
    
    for(int i=0;i<8;i++) if (tetris[i].moving()) return false;

    for (unsigned char i=0;i<8;i++) tetris[i].dumbMoveToSlit(slit[i]);  
  }
  else return false;

  return true;
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
  saveSlitPositionsToEEPROM();
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

  if(axis==0)  for(int i=0;i<8;i++) {if (tetris[i].moving()) return false;}
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

  if(axis==0) for(int i=0;i<8;i++) {if (!tetris[i].isCalibrated()) return false;}
  else if (!tetris[axis-1].isCalibrated()) return false;
  
  if(axis==0) for(int i=0;i<8;i++) {if (tetris[i].moving()) return false;}
  else if (tetris[axis-1].moving()) return false;

  if(axis==0) for(int i=0;i<8;i++) tetris[i].positionAbsoluteMove(param);
  else tetris[axis-1].positionAbsoluteMove(param);

  return true;
}

//Report the version string
bool PVcommand() {
  cout<<VERSION_STRING<<endl;
  return true;
}

//Report the last temp reading
bool TEcommand() {
    Serial.print(lastTempReading, 4);
    cout<<endl;
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
  
  if(axis==0) for(int i=0;i<8;i++) {if (tetris[i].moving()) return false;}
  else if (tetris[axis-1].moving()) return false;
  
  if(axis==0) for(int i=0;i<8;i++) tetris[i].calibrateToHardStop();
  else tetris[axis-1].calibrateToHardStop();

  return true;
}

//Print the commands
bool PCcommand() {
    cout<<pstr("#PC   Print Commands - Print the list of commands");Serial.write('\r');
    cout<<pstr("#VO   Voltage Off - Power down the tetris motors");Serial.write('\r');
    cout<<pstr("#VE   Voltage Enable - Power up the motor supply");Serial.write('\r');
    cout<<pstr("#TS   Tell Status - Tell the status bytes");Serial.write('\r');
    cout<<pstr("#AH   Active Hold - Enable active holding of the motor position");Serial.write('\r');
    cout<<pstr("#PH   Passive Hold - Disable active holding of the motor position");Serial.write('\r');
    cout<<pstr("#GH   Get Hold - Tell if active or passive holding is enabled");Serial.write('\r');
    cout<<pstr("#CS   Connect Shoe - Restore slit positions & enable all commands if locking nut engaged");Serial.write('\r');
    cout<<pstr("#DS   Disconnect Shoe - If online, power off shield, save positions, and online only commands");Serial.write('\r');
    cout<<pstr("#PV   Print Version - Print the version string");Serial.write('\r');
    cout<<pstr("#TE   Temperature - Report the shoe temperature");Serial.write('\r');
  
    cout<<pstr("#TDx  Tell Position - Tell position of tetris x in microsteps");Serial.write('\r');
    cout<<pstr("#SGx  Slit Get - Get the current slit for tetris x");Serial.write('\r');
    cout<<pstr("#SHx  Servo Here - Turn on tetris x");Serial.write('\r');
    cout<<pstr("#MOx  Motor Off - Turn off motor in tetris x");Serial.write('\r');
    cout<<pstr("#STx  Stop - Stop motion of tetris x");Serial.write('\r');
    cout<<pstr("#DHx  Drive Hardstop - Drive tetris x to the hardstop");Serial.write('\r');

    cout<<pstr("#DPx# Define Position - Define the current position of tetris x to be #");Serial.write('\r');
    cout<<pstr("#PAx# Position Absolute - Command tetris x to move to position #");Serial.write('\r');
    cout<<pstr("#PRx# Position Relative - Command tetris x to move #");Serial.write('\r');
    cout<<pstr("#SPx# Speed - Set the movement speed of tetris x to # (usteps/s)");Serial.write('\r');
    cout<<pstr("#ACx# Acceleration - Set the acceleration rate of tetris x to # (usteps/s^2)");Serial.write('\r');
    cout<<pstr("#SLx# Slit - Command tetris x to go to the position of slit #");Serial.write('\r');
    cout<<pstr("#SDx# Slit Defined - Get step position for slit # for tetris x");Serial.write('\r');
    cout<<pstr("#BLx# Backlash - Set the amount of backlash of tetris x to # (usteps)");Serial.write('\r');
  
    cout<<pstr("#CY # low# high# Cycle - Cycl tetris A # times from low# to high#. low# must be > high#");Serial.write('\r');
    
    cout<<pstr("#SSx#[#] Slit Set - Set the step position of slit # for tetris x to the current position. If given the second number is used to define the position.");Serial.write('\r');
  
    return true;
}

bool CYcommand() {
  
  int command_offset=3;
  char * searchstr=" ";
  
  if (command_offset >= command_length) return false;
    
  stresscycles=2*atol(command_buffer+command_offset);
  
  command_offset+=strcspn(command_buffer+command_offset, searchstr)+1;
  if (command_offset >= command_length) return false;
  
  stressBottomP=atol(command_buffer+command_offset);
  
  command_offset+=strcspn(command_buffer+command_offset, searchstr)+1;
  if (command_offset >= command_length) return false;
  
  stressTopP=atol(command_buffer+command_offset);

  #ifdef DEBUG
    cout<<stresscycles/2<<" "<<stressTopP<<"  "<<stressBottomP;Serial.write('\n');  
  #endif

  if (stressTopP>=stressBottomP || stressTopP<-8000 || stressBottomP>1000) {
    stressBottomP=stressTopP=0;
    return false;
  }

  return true;
}

#pragma mark EEPROM Commands

//Load the nominal slits positions for all the slits from EEPROM
bool loadSlitPositionsFromEEPROM() {
    uint16_t crc, saved_crc;
    uint32_t positions[N_TETRI*7];
    bool ret=false;
    #ifdef DEBUG_EEPROM
        uint32_t t=millis();
    #endif
    //Fetch the stored slit positions & CRC16
    EEPROM.readBlock<uint32_t>(EEPROM_SLIT_POSITIONS_ADDR, positions, N_SLIT_POSITIONS);
    saved_crc=EEPROM.readInt(EEPROM_SLIT_POSITIONS_CRC16_ADDR);
    crc=OneWire::crc16((uint8_t*) positions, N_SLIT_POSITIONS*4);
    //If the CRC matches, restore the positions
    if (crc == saved_crc) {
        for (uint8_t i=0; i<N_TETRI; i++) {
            for (uint8_t j=0; j<7; j++) {
                tetris[i].defineSlitPosition(j, positions[i*7+j]);
            }
        }
        ret=true;
    }
    #ifdef DEBUG_EEPROM
        uint32_t t1=millis();
        cout<<"loadSlitPositionsFromEEPROM took "<<t1-t<<" ms.\n";
    #endif
    return ret;
}

//Store the nominal slits positions for all the slits to EEPROM
void saveSlitPositionsToEEPROM() {
    uint16_t crc;
    uint32_t positions[N_TETRI*7];
    #ifdef DEBUG_EEPROM
        uint32_t t=millis();
    #endif
    //Fetch the defined slit positions
    for (uint8_t i=0; i<N_TETRI; i++) {
        for (uint8_t j=0; j<7; j++) {
            positions[i*7+j]=tetris[i].getSlitPosition(j);
        }
    }
    //Store them with their CRC16
    EEPROM.updateBlock<uint32_t>(EEPROM_SLIT_POSITIONS_ADDR, positions, N_SLIT_POSITIONS);
    crc=OneWire::crc16((uint8_t*) positions, N_SLIT_POSITIONS*4);
    EEPROM.writeInt(EEPROM_SLIT_POSITIONS_CRC16_ADDR, crc);
    #ifdef DEBUG_EEPROM
        uint32_t t1=millis();
        cout<<"saveSlitPositionsToEEPROM took "<<t1-t<<" ms.\n";
    #endif
}

//Load the saved motor positions for the Tetri from EEPROM, butcher the CRC
//  so it doesn't match, this way to force recalibration if there is an
//  improper shutdown
bool loadMotorPositionsFromEEPROM() {
    uint16_t crc, saved_crc;
    uint32_t positions[N_TETRI];

    #ifdef DEBUG_EEPROM
        uint32_t t=millis();
    #endif    
    EEPROM.readBlock<uint32_t>(EEPROM_LAST_SAVED_POSITION_ADDR, positions, N_TETRI);
    saved_crc=EEPROM.readInt(EEPROM_LAST_SAVED_POSITION_CRC16_ADDR);
    crc=OneWire::crc16((uint8_t*) positions, N_TETRI*4);
    if (saved_crc ==  crc)
    {
        for (uint8_t i=0; i<N_TETRI; i++)
            tetris[i].definePosition( positions[i] );
        EEPROM.writeInt(EEPROM_LAST_SAVED_POSITION_CRC16_ADDR, ~crc);
    }
    #ifdef DEBUG_EEPROM
        uint32_t t1=millis();
        cout<<"loadMotorPositionsFromEEPROM took "<<t1-t<<" ms.\n";
    #endif
    return crc == saved_crc;
}

//Store the motor positions for all the Tetri to EEPROM
void saveMotorPositionsToEEPROM() {
    uint16_t crc;
    uint32_t positions[N_TETRI];
    
    #ifdef DEBUG_EEPROM
        uint32_t t=millis();
    #endif
    //Fetch the current slit positions
    for(uint8_t i=0; i<N_TETRI; i++) {
        positions[i]=tetris[i].currentPosition();
    }
    //Save the positions
    EEPROM.updateBlock<uint32_t>(EEPROM_LAST_SAVED_POSITION_ADDR, positions, N_TETRI);
    //Compute their CRC16 & save it
    crc=OneWire::crc16((uint8_t*) positions, N_TETRI*4);
    EEPROM.writeInt(EEPROM_LAST_SAVED_POSITION_CRC16_ADDR, crc);
    #ifdef DEBUG_EEPROM
        uint32_t t1=millis();
        cout<<"saveMotorPositionsToEEPROM took "<<t1-t<<" ms.\n";
    #endif
}

