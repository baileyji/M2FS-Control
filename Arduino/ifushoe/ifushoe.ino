#include <SdFat.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <EEPROM.h>
#include <EwmaT.h>
#include "fibershoe_pins.h"
#include "shoe.h"


// DS time is about 8 ms and boot time is about 12 ms

//#define DEBUG_ANALOG
//#define DEBUG_EEPROM
//#define DEBUG_RUN_TIME  2.4ms
//#define DEBUG_COMMAND

#define POWERDOWN_DELAY_US  1000
//#define LOCKING_SCREW_ENGAGE_DEBOUNCE_TIME_MS 200
#define VERSION_STRING "IFUShoe v1.0"
#define VERSION 0x01
#define N_COMMANDS 15

#define TEMP_UPDATE_INTERVAL_MS 20000
#define DS18B20_10BIT_MAX_CONVERSION_TIME_MS 188
#define DS18B20_12BIT_MAX_CONVERSION_TIME_MS 750

//EEPROM Addresses (Uno has 1024 so valid adresses are 0x0000 - 0x03FF
#define EEPROM_VERSION_ADDR 0x000  //3 bytes (version int repeated thrice)
#define EEPROM_BOOT_COUNT_ADDR  0x003  // 1 byte
#define EEPROM_SLIT_POSITIONS_CRC16_ADDR            0x0006 //2 bytes
#define EEPROM_SLIT_POSITIONS_ADDR                  0x0008 //32 bytes, ends at 0x28


#pragma mark Globals

typedef struct eeprom_shoe_data_t {
  shoecfg_t shoeR;
  shoecfg_t shoeB;
  shoepos_t posR;
  shoepos_t posB;
} eeprom_shoe_data_t;

typedef struct eeprom_version_t {
  uint8_t v[3];
} eeprom_version_t; 


uint32_t boottime;
uint8_t bootcount;
ArduinoOutStream cout(Serial);

#ifdef DEBUG_ANALOG
EwmaT<uint64_t> filt0(20,100), filt1(15,100), filt2(1,10), filt3(1,1);  //1/100 = .01 ~average 100 .1 average 10 1 average none
#endif

//Stress testing
unsigned long stresscycles=0;
uint8_t stress_slit=0;

//Power state management
bool locking_screw_disengaged=false; //Boot assuming locking nut is disengaged
bool shoeOnline=true; //Always boot in offline mode

//The Shoes
#define SHOE_R 0
#define SHOE_B 1


Servo psr,psb,hsr,hsb;
ShoeDrive shoeR = ShoeDrive(PIN_PIPE_SERVO_R, PIN_PIPE_POT_R, PIN_HEIGHT_SERVO_R, PIN_HEIGHT_POT_R, PIN_HEIGHT_SENSE_R, &psr,&hsr);
ShoeDrive shoeB = ShoeDrive(PIN_PIPE_SERVO_B, PIN_PIPE_POT_B, PIN_HEIGHT_SERVO_B, PIN_HEIGHT_POT_B, PIN_HEIGHT_SENSE_B, &psb,&hsb);
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


#pragma mark Commands

//Commands
typedef struct {
    String name;
    bool (*callback)();
    const bool allowOffline;
} Command;


bool CScommand();
bool CYcommand();
bool PCcommand();
bool PVcommand();
bool SDcommand();
bool SGcommand();
bool SLcommand();
bool SScommand();
bool STcommand();
bool TDcommand();
bool TEcommand();
bool TScommand();
bool ZBcommand();
bool MVcommand();
bool DScommand();

const Command commands[N_COMMANDS]={
    //Connect Shoe restore slit positions and eanble all commands
    {"CS", CScommand, true},
    {"DS", DScommand, true},
    
    //Cycle tetris A N times from stressBottomP to stressTopP
    {"CY", CYcommand, false},

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
    //Zero the boot count
    {"ZB",ZBcommand, true},
    //Directly move an axis on a given shoe 
    {"MV", MVcommand, true}
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

void initTempSensors() {
    tempSensors.begin(); //TO
    tempSensors.setResolution(12);
    tempSensors.setWaitForConversion(false);
    cout<<F("Searching for temp sensors: ")<<endl;
    for (int i=0;i<N_TEMP_SENSORS;i++) {
      uint8_t addr;
      bool sensorFound;
      temps[i].present = tempSensors.getAddress(temps[i].address, i);
      if (temps[i].present) {
        cout<<F("Found one at: ");
        print1WireAddress(temps[i].address);
        cout<<endl;
      }        
    }
    cout<<F(" done searching.")<<endl;
    tempSensors.requestTemperatures();
    time_of_last_temp_request=millis();
    tempRetrieved=false;
}

#pragma mark Setup & Loop
void setup() {

    boottime=millis();
    
    // Start serial connection
    Serial.begin(115200);
    
    //Analog setup
    analogReference(EXTERNAL);

    //Set up R vs. B side detection
//    pinMode(R_SIDE_POLL_PIN,INPUT);
//    digitalWrite(R_SIDE_POLL_PIN, LOW);

    //Set up temp sensor
    initTempSensors();

    //Shoe Driver Startup
    shoeR.init();
    shoeB.init();

    //Restore the nominal slit positions & backlash amounts from EEPROM
    loadSlitPositionsFromEEPROM();

    //Boot info
    boottime=millis()-boottime;
    bootcount=bootCount(true);
    cout<<F("# Total boots: ")<<(uint16_t) bootcount<<F(" Boot took ")<<boottime<<F(" ms.\n");
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

    //In general the controller will probably boot before the shoes are connected
    for (int i=0;i<N_TEMP_SENSORS;i++) if (!temps[i].present) initTempSensors();
    monitorTemperature();

    //If the command received flag is set
    if (have_command_to_parse) {
        #ifdef DEBUG_COMMAND
            printCommandBufNfo();
        #endif

        //Find command in commands
        int8_t ndx=getCallbackNdxForCommand();
        
        //If not a command respond error
        if (ndx == -1 ) Serial.write("?\n");
        else {
            //Ensure stresscycles=0 if command is not CY
            if (commands[ndx].name == "CY") stresscycles=0;
            
            #ifdef DEBUG_COMMAND
                cout<<"Shoe is "<<(shoeOnline ? "ON":"OFF")<<endl;
                cout<<"Command is ";Serial.println(commands[ndx].name);
            #endif
            
            //Execute the command or respond shoe is offline
            if (!shoeOnline && !commands[ndx].allowOffline) cout<<F("Powered Down\n:");
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

#pragma mark Helper Functions

#ifdef DEBUG_COMMAND
void printCommandBufNfo(){
  cout<<F("Command Buffer Info\n");
  cout<<"Buf ndx: "<<(unsigned int)command_buffer_ndx<<" Cmd len: "<<(unsigned int)command_length<<endl;
  cout<<"Contents: ";Serial.write((const uint8_t*)command_buffer,command_buffer_ndx);
  cout<<"Shoe:"<<(unsigned int)getShoeForCommand()<<endl;
}
#endif


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
//            #ifdef DEBUG_COMMAND
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
//                #ifdef DEBUG_COMMAND
//                    cout<<"Locking screw reingaged.\n";
//                #endif
//            }
//        }
//    }
//}


//Tasks to execute every main loop iteration when the shoe is online 
void shoeOnlineMain() {
    //Stress testing code
    if (stresscycles>0 && !shoes[0].moving()) {
        stresscycles--;
        for (uint8_t i=0;i<2;i++) shoes[i].moveToSlit(stress_slit);
        stress_slit++;
        if (stress_slit==N_SLIT_POS) stress_slit=0;
    }


    #ifdef DEBUG_ANALOG
        uint16_t x[4];
        x[0]=analogRead(PIN_PIPE_POT_R);
        x[1]=analogRead(PIN_HEIGHT_POT_R);
        x[2]=analogRead(PIN_PIPE_POT_B);
        x[3]=analogRead(PIN_HEIGHT_POT_B);
        cout<<"R: p="<<x[0]<<", "<<(uint32_t)filt0.filter(x[0])<<", "<<(uint32_t)filt1.filter(x[0])<<", ";
        cout<<(uint32_t)filt2.filter(x[0])<<", "<<(uint32_t)filt3.filter(x[0])<<endl;
//        cout<<"B: p="<<(uint32_t)filt2.filter(x[2])<<"("<<x[2]<<") h="<<(uint32_t)filt3.filter(x[3])<<"("<<x[3]<<")\n";
    #endif
    
    //Call run on each shoe
    #ifdef DEBUG_RUN_TIME
        uint32_t t=micros();
    #endif
    
    for (uint8_t i=0;i<2;i++) shoes[i].run();

    #ifdef DEBUG_RUN_TIME
        uint32_t t1=micros();
        if((t1-t)>80) cout<<"Run took "<<t1-t<<" us.\n";
    #endif    
    
    //More stress testing code
    if (stresscycles>0 && !shoes[0].moving()) {
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

uint8_t getShoeForCommand() {
  char shoe=command_buffer[2];
  if (shoe=='r' || shoe=='R') return SHOE_R;
  else if (shoe=='b' || shoe=='B') return SHOE_B;
  else return 0xFF;
}


#pragma mark Command Handlers

//Zero the boot count
bool ZBcommand(){
    EEPROM.write(EEPROM_BOOT_COUNT_ADDR, 0);
    return true;
}

//Connect the shoe to bring it online
bool CScommand() {
    //Come online if the locking nut is engaged
    //TODO
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


bool DScommand() {
    //Powerdown and store positions (if online)
    if (shoeOnline) {
//        disableTetrisVreg();
        saveSlitPositionsToEEPROM();
        shoeOnline=false;
    }
    return true;
}

//Report the current slit for specified shoe: 1-7,UNKNOWN,INTERMEDIATE,MOVING
bool SGcommand() {
  char shoe = getShoeForCommand();
  if ( shoe==0xFF ) return false;
  
  if(shoes[shoe].moving()) cout<<F("MOVING");
  else {
    char slit=shoes[shoe].getCurrentSlit();
    if (slit>=0) cout<<slit+1;
    else {
      shoepos_t pos = shoes[shoe].getCurrentPosition();
      cout<<F("INTERMEDIATE (")<<pos.pipe<<", "<<pos.height<<")";
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
  if ( slit>N_SLIT_POS-1 ) return false;

  shoes[shoe].tellSlitPosition(slit);
  cout<<endl;
  return true;
}

//Report the status bytes
bool TScommand() {

  cout<<endl;
  for (int i=0;i<2;i++) {
    if (i==SHOE_R) cout<<"R";
    else cout<<"B";
    cout<<": "; shoes[i].tellCurrentPosition(); cout<<": Slit "; shoes[i].tellCurrentSlit();
    cout<<" pm="<<shoes[i].pipeMoving()<<" hm="<<shoes[i].heightMoving();
    cout<<endl;
  }

  
//TODO
//  uint16_t statusBytes[4]={0,0,0,0};
//  for (int i=0;i<2;i++) statusBytes[0]|=(shoes[i].moving()<<i);
//  cout<<statusBytes[3]<<" "<<statusBytes[2]<<" "<<statusBytes[1]<<" "<<statusBytes[0]<<endl;
  return true;
}

// Get currrent position/moving/unknown
bool TDcommand(){
  
  uint16_t shoe = getShoeForCommand();
  if ( shoe==0xFF ) return false;
  
  if (shoes[shoe].moving()) cout<<F("MOVING");
  else shoes[shoe].tellCurrentPosition();
  cout<<endl;
  return true;
}

//Stop motion of a SHOE
bool STcommand(){
  uint16_t shoe = getShoeForCommand();
  if ( shoe==0xFF ) return false;
  shoes[shoe].stop();
  return true;
}

//Move to a nominal slit position
bool SLcommand() {

  uint8_t shoe = getShoeForCommand();
  if ( shoe==0xFF ) return false;

  uint8_t slit=convertCharToSlit(command_buffer[3]);
  if ( slit>N_SLIT_POS-1 ) return false;
    
  if (shoes[shoe].moving()) return false;

  shoes[shoe].moveToSlit(slit);

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

    cout<<F("#PC   Print Commands - Print the list of commands")<<endl;
    cout<<F("#TS   Tell Status - Tell the status bytes")<<endl;
    cout<<F("#CS   Connect Shoe - Restore slit positions & enable all commands")<<endl;
    cout<<F("#PV   Print Version - Print the version string")<<endl;
    cout<<F("#TE   Temperature - Report the shoe temperatures")<<endl;
  
    cout<<F("#TDx  Tell Position - Tell position of shoe x in UNITS")<<endl;
    cout<<F("#SGx  Slit Get - Get the current slit for shoe x")<<endl;
    cout<<F("#STx  Stop - Stop motion of shoe x")<<endl;

    cout<<F("#SLx# Slit - Command shoe x to go to the position of slit #")<<endl;
    cout<<F("#SDx# Slit Defined at - Get step position for slit # for shoe x")<<endl;
  
    cout<<F("#CYx# Cycle - Cycle shoe x through all the slits # times")<<endl;
    
    cout<<F("#SSx#[#] Slit Set - Set the position of slit # for shoe x to the current position. "\
               "If given the second number is used to define the position.")<<endl;

    cout<<F("#MVxy# Move - !DANGER! Command the position of shoe x (R|B) axis y (H|P) to # (0-180).")<<endl;

    return true;
}

bool CYcommand() {
  
  int command_offset=3;
  char * searchstr=" ";
  
  if (command_offset >= command_length) return false;
    
  stresscycles=atol(command_buffer+command_offset);
  
  command_offset+=strcspn(command_buffer+command_offset, searchstr)+1;
  if (command_offset >= command_length) return false;
  
  return true;
}


bool MVcommand() {

  if (command_length<5) return false;
  
  uint8_t shoe = getShoeForCommand();
  if ( shoe==0xFF ) return false;

  uint16_t pos=max(atol(command_buffer+4),0);

  if (command_buffer[3]=='H') shoes[shoe].moveHeight(pos);
  else if (command_buffer[3]=='P') shoes[shoe].movePipe(pos);
  else return false;

  cout<<"Moving "<<(uint16_t) shoe<<" axis "<<command_buffer[3]<<" to "<<pos<<endl;

  return true;
}

#pragma mark EEPROM Commands

//Return true if data in eeprom is consistent with current software
// version
bool versionMatch() {
  bool updateVersion=false;

  eeprom_version_t ver_info;
  
  EEPROM.get(EEPROM_VERSION_ADDR, ver_info);
  if (ver_info.v[0]!=ver_info.v[1] || ver_info.v[1] != ver_info.v[2]) {
    //version corrupt or didn't exist
    updateVersion=true;
  } else if (ver_info.v[0]!=VERSION) {
    //Version changed do what ever needs doing
    updateVersion=true;
  }
  
  if (updateVersion) {
    ver_info.v[0]=VERSION;
    ver_info.v[1]=VERSION;
    ver_info.v[2]=VERSION;
    EEPROM.put(EEPROM_VERSION_ADDR, ver_info);
    return false;
  } else return true;
  
}

//Load the nominal slits positions for all the slits from EEPROM
bool loadSlitPositionsFromEEPROM() {
    uint16_t crc, saved_crc;
    eeprom_shoe_data_t data;
    
    bool ret=false;
    
    #ifdef DEBUG_EEPROM
        uint32_t t=millis();
    #endif
    //Fetch the stored slit positions & CRC16
    EEPROM.get(EEPROM_SLIT_POSITIONS_ADDR, data);
    EEPROM.get(EEPROM_SLIT_POSITIONS_CRC16_ADDR, saved_crc);
    crc=OneWire::crc16((uint8_t*) &data, sizeof(eeprom_shoe_data_t));  //second to is from the cast

    //If the CRC matches, restore the positions
    if (crc == saved_crc) {
        shoeR.restoreEEPROMInfo(data.shoeR);
        shoeB.restoreEEPROMInfo(data.shoeB);
        shoeR.movePipe(data.posR.pipe);
        shoeR.moveHeight(data.posR.height);
        shoeB.movePipe(data.posB.pipe);
        shoeB.moveHeight(data.posB.height);
        ret=true;
    }

    #ifdef DEBUG_EEPROM
        cout<<"Restoring shoe config from EEPROM took "<<millis()-t<<" ms.\n";
        cout<<"ShoeR:\n  "<<data.shoeR.height_pos[0]<<" "<<data.shoeR.height_pos[1]<<"\n  ";
        for (uint8_t i=0;i<N_SLIT_POS;i++) cout<<data.shoeR.pipe_pos[i]<<" ";
        cout<<endl<<data.posR.pipe<<", "<<data.posR.height<<endl;
        cout<<"ShoeB:\n  "<<data.shoeB.height_pos[0]<<" "<<data.shoeB.height_pos[1]<<"\n  ";
        for (uint8_t i=0;i<N_SLIT_POS;i++) cout<<data.shoeB.pipe_pos[i]<<" ";
        cout<<endl<<data.posB.pipe<<", "<<data.posB.height<<endl;
    #endif

    return ret;
}

//Store the nominal slits positions for all the slits to EEPROM
void saveSlitPositionsToEEPROM() {
    uint16_t crc;
    eeprom_shoe_data_t data;
    
    #ifdef DEBUG_EEPROM
        uint32_t t=millis();
    #endif
    
    //Fetch the defined slit positions
    shoeR.getEEPROMInfo(data.shoeR);
    shoeB.getEEPROMInfo(data.shoeB);

    data.posR = shoeR.getCommandedPosition();
    data.posB = shoeB.getCommandedPosition();
    
    //Store them with their CRC16
    EEPROM.put(EEPROM_SLIT_POSITIONS_ADDR, data);
    crc=OneWire::crc16((uint8_t*) &data, sizeof(eeprom_shoe_data_t));  //second to is from the cast
    EEPROM.put(EEPROM_SLIT_POSITIONS_CRC16_ADDR, crc);
    #ifdef DEBUG_EEPROM
        cout<<"saveSlitPositionsToEEPROM took "<<millis()-t<<" ms.\n";
    #endif
}
