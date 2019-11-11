#include <SdFat.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <EEPROMEx.h>
#include "fibershoe_pins.h"
#include "shoe.h"

#define POWERDOWN_DELAY_US  1000
//#define LOCKING_SCREW_ENGAGE_DEBOUNCE_TIME_MS 200
#define VERSION_STRING "IFUShoe v1.0"
#define VERSION_INT32 0x00000001
#define N_COMMANDS 32

//#define DEBUG
//#define DEBUG_EEPROM
//#define DEBUG_RUN_TIME

#define TEMP_UPDATE_INTERVAL_MS 20000
#define DS18B20_10BIT_MAX_CONVERSION_TIME_MS 188
#define DS18B20_12BIT_MAX_CONVERSION_TIME_MS 750

//EEPROM Addresses (Mega has 4KB so valid adresses are 0x0000 - 0x0FFF
#define EEPROM_LAST_SAVED_POSITION_CRC16_ADDR       0x0000
#define EEPROM_LAST_SAVED_POSITION_ADDR             0x0002 //32 bytes, ends at 0x0022

#define EEPROM_SLIT_POSITIONS_CRC16_ADDR            0x0080
#define EEPROM_SLIT_POSITIONS_ADDR                  0x0082 //224 bytes, ends at 0x0162
#define N_SLIT_POSITIONS                            7

#define EEPROM_BACKLASH_CRC16_ADDR                  0x0200
#define EEPROM_BACKLASH_ADDR                        0x0202 // 32 bytes, ends at 0x0222

#define EEPROM_BOOT_COUNT_ADDR  0x0600  // One byte

#define EEPROM_VERSION_ADDR 0x0610  //12 bytes (version int repeated thrice)

#pragma mark Globals

ArduinoOutStream cout(Serial);

//The Shoes
#define SHOE_R 0
#define SHOE_B 1
ShoeDrive shoeR = ShoeDrive(PIN_PIPE_SERVO_R, PIN_PIPE_POT_R, PIN_HEIGHT_SERVO_R, PIN_HEIGHT_POT_R, PIN_HEIGHT_SENSE_R);
ShoeDrive shoeB = ShoeDrive(PIN_PIPE_SERVO_B, PIN_PIPE_POT_B, PIN_HEIGHT_SERVO_B, PIN_HEIGHT_POT_B, PIN_HEIGHT_SENSE_B);
ShoeDrive shoes[] ={shoeR, shoeB};

//Command buffer
char command_buffer[81];
unsigned char command_buffer_ndx=0;
unsigned char command_length=0;
bool have_command_to_parse=false;

//Temp monitoring
#define N_TEMP_SENSORS 2
OneWire oneWire(ONE_WIRE_BUS_PIN);  // Instantiate a oneWire instance
DallasTemperature tempSensors(&oneWire);  //Instantiate temp sensors on oneWire 
typedef struct {
    DeviceAddress address;
    float reading=999.0;
    bool present=false;
} TempSensor;
TempSensor temps[N_TEMP_SENSORS];
bool tempRetrieved=false;
unsigned long time_of_last_temp_request=0;
unsigned long time_since_last_temp_request=0xFFFFFFFF;

// function to print a device address
void print1WireAddress(DeviceAddress deviceAddress) {
  Serial.print("0x");
  for (uint8_t i = 0; i < 8; i++) {
    if (deviceAddress[i] < 16) Serial.print("0");
    Serial.print(deviceAddress[i], HEX);
  }
}

//Stress testing
unsigned long stresscycles=0;
long stressBottomP=0;
long stressTopP=0;

//Power state management
bool locking_screw_disengaged=false; //Boot assuming locking nut is disengaged
//bool shoeOnline=false; //Always boot in offline mode


#pragma mark Commands

//Commands
typedef struct {
    String name;
    bool (*callback)();
    const bool allowOffline;
} Command;

const Command commands[N_COMMANDS]={
    //Connect Shoe restore slit positions and eanble all commands
    {"CS", CScommand, true},
    
    //Cycle tetris A N times from stressBottomP to stressTopP
    {"CY", CYcommand, false},

    //Disconnect Shoe, power off tetris shield save current position data
    //  and disable motion & shield power commands
    {"DS", DScommand, true},

    //Position absolute move, 
    {"PA", PAcommand, true},
    //Print Commands
    {"PC", PCcommand, true},
    //Print version String
    {"PV", PVcommand, true},
    //Slit Defined Position, get the defined position of slit
    {"SD", SDcommand, true},
    //Slit Get. Get the current slit for shoe R|B 1-6,UNKNOWN,INTERMEDIATE,MOVING
    {"SG", SGcommand, false},
    //Slit, move to position of slit
    {"SL", SLcommand, false},
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
    {"ZB",ZBcommand, true},
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

uint32_t boottime;
void setup() {
    
    boottime=millis();

//    //Set up R vs. B side detection
//    pinMode(R_SIDE_POLL_PIN,INPUT);
//    digitalWrite(R_SIDE_POLL_PIN, LOW);
//    pinMode(R_SIDE_POLL_DRIVER_PIN,OUTPUT);
//    digitalWrite(R_SIDE_POLL_DRIVER_PIN, HIGH);

//    //Set up temp sensor
    tempSensors.begin();
    tempSensors.setResolution(12);
    tempSensors.setWaitForConversion(false);
    cout<<pstr("Searching for temp sensors: ");Serial.write('\r');
    for (int i=0;i<N_TEMP_SENSORS;i++) {
      uint8_t addr;
      bool sensorFound;
      temps[i].present = tempSensors.getAddress(temps[i].address, i);
      if (temps[i].present) {
        cout<<pstr("Found one at: ");
        print1WireAddress(temps[i].address);
        Serial.write("\r");
      }        
    }
    cout<<pstr(" done searching.");Serial.write('\r');
    tempSensors.requestTemperatures();
    time_of_last_temp_request=millis();
    tempRetrieved=false;


    //Shoe Driver Startup

    //Restore the nominal slit positions & backlash amounts from EEPROM
//    loadSlitPositionsFromEEPROM();
//    loadBacklashFromEEPROM();

    // Start serial connection
    Serial.begin(115200);
    
    boottime=millis()-boottime;
    uint8_t bootcount;
    bootcount=bootCount(true);
    
    Serial.print("#Booted for ");
    Serial.print((uint16_t) bootcount);
    Serial.print(" time in ");
    Serial.print(boottime);
    Serial.println(" ms.");
}


uint8_t bootCount(bool set) {
    uint8_t count;
    count=EEPROM.read(EEPROM_BOOT_COUNT_ADDR);
    if (set==true && count < 200) {
        count++;
        //increment & save boot count
        EEPROM.write(EEPROM_BOOT_COUNT_ADDR, count);
    }
    return count;
}

//Main loop, runs forever at full steam ahead
void loop() {

//    monitorLockingNutState();
    
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
            if (commands[ndx].name == "CY") stresscycles=0;
            
            #ifdef DEBUG
                cout<<"Shoe is "<<(shoeOnline ? "ON":"OFF")<<endl;
                cout<<"Command is ";Serial.println(commands[ndx].name);
            #endif
            
            //Execute the command or respond shoe is offline
            if (!shoeOnline && !commands[ndx].allowOffline) cout<<"Powered Down"<<endl<<":";
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
  
    if (shoeOnline) shoeOnlineMain();
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
        for (uint8_t i=0; i<N_COMMANDS;i++) if (commands[i].name==name) return i;
    }
    return -1;
}

//Convert a character to a slit number. '1' becomes 0, '2' 1, ...
inline uint8_t convertCharToSlit(char c) {
    return c-'0'-1; //(-1 as slit is specified 1-7)
}

//Request and fetch the temperature regularly, ignore rollover edgecase
void monitorTemperature() {
    if (time_since_last_temp_request > TEMP_UPDATE_INTERVAL_MS) {
        tempSensors.requestTemperatures();
        time_of_last_temp_request=millis();
        tempRetrieved=false;
    }
    
    time_since_last_temp_request=millis()-time_of_last_temp_request;
    
    if(!tempRetrieved && time_since_last_temp_request > DS18B20_12BIT_MAX_CONVERSION_TIME_MS) {
       for (uint8_t i=0; i<N_TEMP_SENSORS; i++) {
         if (temps[i].present) temps[i].reading=tempSensors.getTempC(temps[i].address);
       }
       tempRetrieved = true;
    }
}

/* 
Read the digital input for the locking nut,
If the state changes to engaged, debounce the pin (routine will block for
LOCKING_SCREW_ENGAGE_DEBOUNCE_TIME_MS) and update the locking nut state.
If the state changes to disengaged, update the state immediately and put
the shoe into offline mode by calling DScommand.
*/
//void monitorLockingNutState() {
//
//    // If the locking screw reads as disengaged...
//    if (digitalRead(DISCONNECT_SHOE_PIN)){
//        if (!locking_screw_disengaged) { //and this is a state change...
//            //Enter offline mode
//            DScommand();
//            locking_screw_disengaged=true;
//            #ifdef DEBUG
//                cout<<"Locking screw disengaged.\n";
//            #endif
//        }
//    }
//    else { //the screw reads as engaged
//        if (locking_screw_disengaged) { //and this is a state change...
//            //Debounce switch
//            uint8_t i=LOCKING_SCREW_ENGAGE_DEBOUNCE_TIME_MS;
//            while (!digitalRead(DISCONNECT_SHOE_PIN) && (i-- > 1) ) delay(1);
//            //If the locking screw is engaged power up and accept commands
//            if (i==0) {
//                locking_screw_disengaged=false;
//                #ifdef DEBUG
//                    cout<<"Locking screw reingaged.\n";
//                #endif
//            }
//        }
//    }
//}


//Tasks to execute every main loop iteration when the shoe is online 
void shoeOnlineMain() {
    //Stress testing code
    if (stresscycles>0 && !shoe[0].moving()) {
        stresscycles--;
        for (char i=0;i<;i++) shoe[i].moveToSlit(next_stress_slit);
        next_stress_slit++;
        if (next_stress_slit==N_SLIT_POS) next_stress_slit=0;
    }

    //Call run on each shoe
    #ifdef DEBUG_RUN_TIME
        uint32_t t=micros();
    #endif
    
    for (char i=0;i<;i++) shoe[i].run();

    #ifdef DEBUG_RUN_TIME
        uint32_t t1=micros();
        if((t1-t)>80) cout<<"Run took "<<t1-t<<" us.\n";
    #endif
    
    //More stress testing code
    if (stresscycles>0 && !shoe[0].moving()) {
        cout<<"Cycle "<<(stresscycles+1)/2<<" finished.\n";
        delay(100);
    }
    //Do we leave the motors on while idle?
//    if (!leave_tetris_on_when_idle) {
//        for (unsigned char i=0; i<8; i++) {
//            if (!tetris[i].moving()) tetris[i].motorOff();
//        }
//    }
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


unsigned char getShoeForCommand() {
  char shoe=command_buffer[2];
  if (shoe=='r' || shoe=='R') return SHOE_R;
  else if (shoe=='b' || shoe=='B') return SHOE_B;
  else return 0xFF;
}


#pragma mark Command Handlers

bool ZBcommand(){
    EEPROM.write(EEPROM_BOOT_COUNT_ADDR, 0);
    return true;
}

bool CScommand() {
    //Come online if the locking nut is engaged
//    if (locking_screw_disengaged)
//        return false;
//    else {
        if (!shoeOnline) {
            shoeOnline=true;
//            enableTetrisVreg();
//            delay(20); //Wait a short time for the vreg to stabilize
        }
        return true;
//    }
}


//Report the current slit for specified shoe: 1-7,UNKNOWN,INTERMEDIATE,MOVING
bool SGcommand() {
  char shoe = getShoeForCommand();
  if ( shoe != R_SHOE &&  shoe != B_SHOE ) return false;
  
  if(shoes[shoe].moving()) cout<<"MOVING";
  else {
    char slit=shoes[i].getCurrentSlit();
    if (slit>=0) cout<<slit+1;
    else {
      shoepos_t pos = shoes[i].currentPositon();
      cout<<"INTERMEDIATE ("<<pos.pipe<<", "<<pos.height<<")";
    }
  }
  cout<<endl;
  return true;
}


//Report the nominial position of the specified slit
bool SDcommand() {
  uint8_t shoe = getShoeForCommand();
  if ( shoe==0xFF ) return false;

  unsigned char slit=convertCharToSlit(command_buffer[3]);
  if ( slit>N_SLIT_POS ) return false;

  shoes[shoe].tellSlitPosition(slit);
  cout<<endl;
  return true;
}

//Report the status bytes
//TODO
bool TScommand() {

  for (int i=0;i<2;i++) shoes[i].tellSlitPosition();
  
  uint16_t statusBytes[4]={0,0,0,0};
//  for (int i=0;i<2;i++) statusBytes[0]|=(shoes[i].moving()<<i);
  cout<<statusBytes[3]<<" "<<statusBytes[2]<<" "<<statusBytes[1]<<" "<<statusBytes[0]<<endl;
  return true;
}



// Get currrent position/moving/unknown
bool TDcommand(){
  
  uint8_t shoe = getShoeForCommand();
  if ( shoe==0xFF ) return false;
  
  if (shoes[shoe].moving()) cout<<"MOVING";
  else shoe[shoe].tellCurrentPosition();
  cout<<endl;
  return true;
}

//Stop motion of a SHOE
bool STcommand(){
  unsigned char shoe = getShoeForCommand();
  if ( shoe==0xFF ) return false;
  shoe[shoe].stop();
  return true;
}

//Move to a nominal slit position
bool SLcommand() {

  uint8_t shoe = getShoeForCommand();
  if ( shoe==0xFF ) return false;

  uint8_t slit=convertCharToSlit(command_buffer[3]);
  if ( slit>N_SLIT_POS-1 ) return false;
    
  if (shoes[i].moving()) return false;

  shoes[i].moveToSlit(slit);

  return true;
}

//Define a nominal slit position
//SS[R|B][#]\0 or SS[R|B][#|##{#######}]\0
bool SScommand() {
  uint8_t shoe = getShoeForCommand();
  if ( shoe==0xFF ) return false;

  uint8_t slit=convertCharToSlit(command_buffer[3]);
  if ( slit>N_SLIT_POS-1 ) return false;

  if (command_length >4){
    if (!(command_buffer[4] >='0' && command_buffer[4]<='9')) return false;
    long pos=atol(command_buffer+4);
    if (pos>MAX_SHOE_POS || pos<0) return false;
    shoes[shoe].defineSlitPosition(slit, pos);
  }
  else {
    shoes[shoe].defineSlitPosition(slit);
  }
  saveSlitPositionsToEEPROM();
  return true;
}


//Report the version string
bool PVcommand() {
  cout<<VERSION_STRING<<endl;
  return true;
}

//Report the last temp reading
bool TEcommand() {
  for (uint8_t i=0; i< N_TEMP_SENSORS; i++) {
    Serial.print(temps[i].reading, 4);
    if (i!=N_TEMP_SENSORS-1) Serial.print(",");
  }
  cout<<endl;
  return true;
}


//Print the commands
bool PCcommand() {
    cout<<pstr("#PC   Print Commands - Print the list of commands");Serial.write('\r');
    cout<<pstr("#TS   Tell Status - Tell the status bytes");Serial.write('\r');
    cout<<pstr("#CS   Connect Shoe - Restore slit positions & enable all commands");Serial.write('\r');
    cout<<pstr("#PV   Print Version - Print the version string");Serial.write('\r');
    cout<<pstr("#TE   Temperature - Report the shoe temperatures");Serial.write('\r');
  
    cout<<pstr("#TDx  Tell Position - Tell position of shoe x in UNITS");Serial.write('\r');
    cout<<pstr("#SGx  Slit Get - Get the current slit for shoe x");Serial.write('\r');
    cout<<pstr("#STx  Stop - Stop motion of shoe x");Serial.write('\r');

    cout<<pstr("#PAx# Position Absolute - Command shoe x to move to position #");Serial.write('\r');
    cout<<pstr("#SLx# Slit - Command shoe x to go to the position of slit #");Serial.write('\r');
    cout<<pstr("#SDx# Slit Defined at - Get step position for slit # for shoe x");Serial.write('\r');
  
    cout<<pstr("#CYx# Cycle - Cycle shoe x through all the slits # times");Serial.write('\r');
    
    cout<<pstr("#SSx#[#] Slit Set - Set the position of slit # for shoe x to the current position. "\
               "If given the second number is used to define the position.");Serial.write('\r');

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

//Return true if data in eeprom is consistent with current software
// version
bool versionMatch() {

  uint32_t versions[3];
  EEPROM.readBlock<uint32_t>(EEPROM_VERSION_ADDR, versions, 3);
  if (versions[0]!=versions[1] || versions[1] != versions[2] ||
      versions[0]!=versions[2]) {
    //version corrupt or didn't exist
    versions[0]=VERSION_INT32;
    versions[1]=VERSION_INT32;
    versions[2]=VERSION_INT32;
    EEPROM.updateBlock<uint32_t>(EEPROM_VERSION_ADDR, versions, 3);
    return false;
  }
  else if (versions[0]!=VERSION_INT32) {
    //Version changed do what ever needs doing
    
    //Update the version
    versions[0]=VERSION_INT32;
    versions[1]=VERSION_INT32;
    versions[2]=VERSION_INT32;
    EEPROM.updateBlock<uint32_t>(EEPROM_VERSION_ADDR, versions, 3);
    
    return false;
  }
  
  return true;
  
}

//Load the nominal slits positions for all the slits from EEPROM
bool loadSlitPositionsFromEEPROM() {
    uint16_t crc, saved_crc;
    uint16_t data[2*(N_SLIT_POS+N_HEIGH_POS)];
    uint16_t dataR[]=&data[0];
    uint16_t dataB[]=&data[N_SLIT_POS+N_HEIGH_POS];
    
    bool ret=false;
    
    #ifdef DEBUG_EEPROM
        uint32_t t=millis();
    #endif
    //Fetch the stored slit positions & CRC16
    EEPROM.readBlock<uint16_t>(EEPROM_SLIT_POSITIONS_ADDR, data, 2*(N_SLIT_POS+N_HEIGH_POS));
    saved_crc=EEPROM.readInt(EEPROM_SLIT_POSITIONS_CRC16_ADDR);
    crc=OneWire::crc16((uint8_t*) data, 2*(N_SLIT_POS+N_HEIGH_POS)*2);

    //If the CRC matches, restore the positions
    if (crc == saved_crc) {
        shoeR.restoreEEPROMInfo(dataR);
        shoeB.restoreEEPROMInfo(dataB);
        ret=true;
    }

    #ifdef DEBUG_EEPROM
        cout<<"loadSlitPositionsFromEEPROM took "<<millis()-t<<" ms.\n";
    #endif

    return ret;
}

//Store the nominal slits positions for all the slits to EEPROM
void saveSlitPositionsToEEPROM() {
    uint16_t crc;
    uint16_t data[2*(N_SLIT_POS+N_HEIGH_POS)];
    uint16_t dataR[]=&data[0];
    uint16_t dataB[]=&data[N_SLIT_POS+N_HEIGH_POS];
    
    #ifdef DEBUG_EEPROM
        uint32_t t=millis();
    #endif
    
    //Fetch the defined slit positions
    shoesR.getEEPROMInfo(dataR);
    shoesB.getEEPROMInfo(dataB);
    
    //Store them with their CRC16
    EEPROM.updateBlock<uint16_t>(EEPROM_SLIT_POSITIONS_ADDR, data, 2*(N_SLIT_POS+N_HEIGH_POS));
    crc=OneWire::crc16((uint8_t*) dat, 2*(N_SLIT_POS+N_HEIGH_POS)*2);  //second to is from the cast
    EEPROM.writeInt(EEPROM_SLIT_POSITIONS_CRC16_ADDR, crc);
    #ifdef DEBUG_EEPROM
        cout<<"saveSlitPositionsToEEPROM took "<<millis()-t<<" ms.\n";
    #endif
}



//Load the nominal slits positions for all the slits from EEPROM
bool loadBacklashFromEEPROM() {
    uint16_t crc, saved_crc;
    uint16_t backlash[N_TETRI];
    bool ret=false;
#ifdef DEBUG_EEPROM
    uint32_t t=millis();
#endif
    //Fetch the stored slit positions & CRC16
    EEPROM.readBlock<uint16_t>(EEPROM_BACKLASH_ADDR, backlash, N_TETRI);
    saved_crc=EEPROM.readInt(EEPROM_BACKLASH_CRC16_ADDR);
    crc=OneWire::crc16((uint8_t*) backlash, N_TETRI*2);
    //If the CRC matches, restore the positions
    if (crc == saved_crc) {
        for (uint8_t i=0; i<N_TETRI; i++) {
            tetris[i].setBacklash(backlash[i]);
        }
        ret=true;
    }
#ifdef DEBUG_EEPROM
    uint32_t t1=millis();
    cout<<"loadBacklashFromEEPROM took "<<t1-t<<" ms.\n";
#endif
    return ret;
}

//Store the backlash amount for for all the tetri to EEPROM
void saveBacklashToEEPROM() {
    uint16_t crc;
    uint16_t backlash[N_TETRI];
#ifdef DEBUG_EEPROM
    uint32_t t=millis();
#endif
    //Fetch the defined slit positions
    for (uint8_t i=0; i<N_TETRI; i++) {
        backlash[i]=tetris[i].getBacklash();
    }
    //Store them with their CRC16
    EEPROM.updateBlock<uint16_t>(EEPROM_BACKLASH_ADDR, backlash, N_TETRI);
    crc=OneWire::crc16((uint8_t*) backlash, N_TETRI*2);
    EEPROM.writeInt(EEPROM_BACKLASH_CRC16_ADDR, crc);
#ifdef DEBUG_EEPROM
    uint32_t t1=millis();
    cout<<"saveBacklashToEEPROM took "<<t1-t<<" ms.\n";
#endif
}
