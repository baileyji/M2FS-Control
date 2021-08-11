#include <SdFat.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <EEPROM.h>
#include <EwmaT.h>
#include "fibershoe_pins.h"
#include "shoe.h"
#include "MemoryFree.h"


/*
 * Temb send addr
 * 0x2A00000C35749728   on a control board
 * 0x28D9A4190C000070 . on a shoe (1 dot, pcb needs reflow on button) add byte reversed
 * 0x4700000C19A4D828 . on a shoe (2 dots, rshoe)
 * 0xF700000C19A4CD28 . on a shoe (3 dots, bshoe)
 * 
 */

// DS time is about ? ms and boot time is about ? ms

//#define DEBUG_ANALOG
#define DEBUG_EEPROM
//#define DEBUG_RUN_TIME  //2.4ms
//#define DEBUG_COMMAND

#define POWERDOWN_DELAY_US  1000
#define VERSION_STRING "IFUShoe v1.1"
#define VERSION 0x02

#define TEMP_UPDATE_INTERVAL_MS 5000  //must be longer than max conversion time
#define DS18B20_10BIT_MAX_CONVERSION_TIME_MS 188
#define DS18B20_12BIT_MAX_CONVERSION_TIME_MS 750

//EEPROM Addresses (Uno has 1024 so valid adresses are 0x0000 - 0x03FF
#define EEPROM_VERSION_ADDR 0x000  //3 bytes (version int repeated thrice)
#define EEPROM_BOOT_COUNT_ADDR  0x003  // 1 byte
#define EEPROM_MODE_ADDR 0x004  //1byte   0=unconfigured 1=debug 2=normal operation  anything else -> 0
#define EEPROM_SLIT_POSITIONS_CRC16_ADDR            0x0006 //2 bytes
#define EEPROM_SLIT_POSITIONS_ADDR                  0x0008 //32 bytes, ends at 0x28


#pragma mark Globals
bool booted=false;

typedef struct eeprom_shoe_data_t {
  shoecfg_t cfgR;
  shoecfg_t cfgB;
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
bool shoeOnline=true; //Always boot in offline mode


//The Shoes
#define SHOE_R 0
#define SHOE_B 1

#define SHOE_B_TEMP 0
#define SHOE_R_TEMP 1
#define DRIVE_TEMP 2
#define DRIVE_TEMP_ADDR  0x2A00000C35749728
#define SHOE_B_TEMP_ADDR 0xF700000C19A4CD28
#define SHOE_R_TEMP_ADDR 0x4700000C19A4D828


Servo psr,psb,hsr,hsb;
ShoeDrive shoeR = ShoeDrive(PIN_PIPE_SERVO_R, PIN_PIPE_POT_R, PIN_HEIGHT_SERVO_R, PIN_HEIGHT_POT_R, PIN_DOWNBUTTON_R, 
                            PIN_MOTORSOFF_R, PIN_MOTORSON_R, &psr,&hsr);
ShoeDrive shoeB = ShoeDrive(PIN_PIPE_SERVO_B, PIN_PIPE_POT_B, PIN_HEIGHT_SERVO_B, PIN_HEIGHT_POT_B, PIN_DOWNBUTTON_B, 
                            PIN_MOTORSOFF_B, PIN_MOTORSON_B, &psb,&hsb);
ShoeDrive* shoes[] ={&shoeR, &shoeB};



//Temp monitoring
#define N_TEMP_SENSORS 3
OneWire oneWire(PIN_ONE_WIRE_BUS);  // Instantiate a oneWire instance
DallasTemperature tempSensors(&oneWire);  //Instantiate temp sensors on oneWire 
typedef struct {
    DeviceAddress address;
    float reading=999.0;
    bool present=false;
} TempSensor;
TempSensor temps[N_TEMP_SENSORS];
bool tempRetrieved=false;
unsigned long time_of_last_temp_request=0;

bool device_address_match(DeviceAddress a, DeviceAddress b){
  for (uint8_t i=0;i<8;i++) if (a[i]!=b[i]) return false;
  return true;
}

void load_deviceaddress(DeviceAddress a, uint64_t x) {
  for(uint8_t i=0;i<8;i++) {
    a[i] = x & 0xFF;
    x = x >> 8;
  }
}

// function to print a device address
void print1WireAddress(DeviceAddress deviceAddress) {
  Serial.print("0x");
  for (int8_t i = 7; i >=0; i--) {
    if (deviceAddress[i] < 16) Serial.print("0");
    Serial.print(deviceAddress[i], HEX);
  }
}


#pragma mark Commands

enum Shoe {RED_SHOE=SHOE_R, BLUE_SHOE=SHOE_B, NO_SHOE};

//Command buffer
char command_buffer[81];
unsigned char command_buffer_ndx=0;
unsigned char command_length=0;
bool have_command_to_parse=false;


typedef struct {
    Shoe shoe;
    int8_t ndx;
    uint8_t arg_len;
    char *arg_buffer;
} Instruction;

Instruction instruction;

//Commands
#define N_COMMANDS 16
typedef struct {
    String name;
    bool (*callback)();
    const bool allowOffline;
    const bool shoeSpecific;
} Command;


bool CYcommand();
bool PCcommand();
bool PVcommand();
bool SDcommand();
bool SGcommand();
bool SLcommand();
bool SScommand();
bool TOcommand();
bool HScommand();
bool STcommand();
bool TDcommand();
bool TEcommand();
bool TScommand();
bool ZBcommand();
bool MVcommand();
bool IOcommand();

Command commands[N_COMMANDS]={
    //name callback offlineok shoespecific
    //Cycle tetri N times through all of the slits
    {"CY", CYcommand, false, false},
    //Print Commands
    {"PC", PCcommand, true, false},
    //Print version String
    {"PV", PVcommand, true, false},
    //Slit Defined Position, get the defined position of slit
    {"SD", SDcommand, true, true},
    //Slit Get. Get the current slit for shoe R|B 1-6,UNKNOWN,INTERMEDIATE,MOVING
    {"SG", SGcommand, false, true},
    //Slit, move to position of slit
    {"SL", SLcommand, false, true},
    //Slit Set, define position of slit
    {"SS", SScommand, true, true},
    //Set TOlerance Set, define position of slit
    {"TO", TOcommand, true, true},
    //Height Set, define position of up/down
    {"HS", HScommand, true, true},
    //Stop moving
    {"ST", STcommand, true, false},
    //Tell Step Position (# UKNOWN MOVING)
    {"TD", TDcommand, false, true},
    //Report temperature
    {"TE", TEcommand, true, false},
    //Tell Status (e.g. moving vreg, etc)
    {"TS", TScommand, true, false},
    //Zero the boot count
    {"ZB",ZBcommand, true, false},
    //Directly move an axis on a given shoe 
    {"MV", MVcommand, false, true},
    //Idle off
    {"IO", IOcommand, true, false}
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

    boottime=millis();

    //Analog setup
    analogReference(EXTERNAL);

    // Start serial connection
    Serial.begin(115200);

    //Shoe Driver Startup
    shoeR.init();
    shoeB.init();
    
    //Set up R vs. B side detection
    pinMode(PIN_SHOESENSE_R, INPUT);
    pinMode(PIN_SHOESENSE_B, INPUT);
    
    digitalWrite(PIN_SHOESENSE_B, HIGH);
    digitalWrite(PIN_SHOESENSE_R, LOW);

    //Set up temp sensor
    load_deviceaddress(temps[DRIVE_TEMP].address, DRIVE_TEMP_ADDR);
    load_deviceaddress(temps[SHOE_B_TEMP].address, SHOE_B_TEMP_ADDR);
    load_deviceaddress(temps[SHOE_R_TEMP].address, SHOE_R_TEMP_ADDR);
    initTempSensors();

    //Restore the nominal slit positions & backlash amounts from EEPROM
    loadSlitPositionsFromEEPROM();

    //Boot info
    boottime=millis()-boottime;
    bootcount=bootCount(true);
    cout<<F("#Boot ")<<(uint16_t) bootcount<<F(" took ")<<boottime<<F(" ms.\n");
    booted=true;
}


//Main loop, runs forever at full steam ahead
void loop() {


    monitorTemperature();

    //If the command received flag is set
    if (have_command_to_parse) {

        bool commandGood=false;
        
        #ifdef DEBUG_COMMAND
            printCommandBufNfo();
        #endif

        //If not a command respond error
        if (parseCommand()) {

            Command *cmd=&commands[instruction.ndx];

            #ifdef DEBUG_COMMAND
                cout<<"ShoeR "<<(shoeRConnected() ? "ON":"OFF")<<endl;
                cout<<"ShoeB "<<(shoeBConnected() ? "ON":"OFF")<<endl;
                cout<<"Command is ";Serial.println(cmd->name);
            #endif

            if(instruction.shoe==NO_SHOE) cout<<"Nshoe\n";
            if(instruction.shoe==RED_SHOE) cout<<"Rshoe\n";
            if(instruction.shoe==BLUE_SHOE) cout<<"Bshoe\n";
            
            if (shoeWiresCrossed()&& cmd->shoeSpecific) {
                cout<<F("#Shoes Crossed\n");
                commandGood=false;
            } else if (instruction.shoe==NO_SHOE && cmd->shoeSpecific){
                commandGood=false;
            } else if (instruction.shoe==RED_SHOE && !cmd->allowOffline && !shoeRConnected()) {
                cout<<F("#Shoe R Disconnected\n:");
                commandGood=false;
            } else if (instruction.shoe==BLUE_SHOE && !cmd->allowOffline && !shoeBConnected()) {
                cout<<F("#Shoe B Disconnected\n");
                commandGood=false;
            } else {
                commandGood=cmd->callback();  //Execute the command 
            }
        }
        
        Serial.println(commandGood ? ":" : "?");
        //Reset the command buffer and the command received flag now that we are done with it
        have_command_to_parse=false;
        command_buffer_ndx=0;
    }

    shoeOnlineMain();

}


//Tasks to execute every main loop iteration when the shoe is online 
void shoeOnlineMain() {
    //Stress testing code
    if (stresscycles>0 && !shoeR.moveInProgress() && !shoeB.moveInProgress()) {
      //#TODO add error handling

        cout<<F("R: "); shoeR.tellCurrentPosition();
        cout<<F(" B: "); shoeB.tellCurrentPosition();
        cout<<endl;
        if (!(shoeR.errors|shoeB.errors)) {
          cout<<F("#Starting cycle ")<<stresscycles<<F(" to ")<<(uint16_t)stress_slit+1<<endl;
          if (shoeRConnected()) shoeR.moveToSlit(stress_slit);
          if (shoeBConnected()) shoeB.moveToSlit(stress_slit);
          stress_slit++;
          stresscycles--;
        } else {
          cout<<F("#Quit due to errors.");
          cout<<F("------R Shoe")<<endl; shoeR.tellStatus(); 
          cout<<F("------B Shoe")<<endl; shoeB.tellStatus();
          stresscycles=0;
        }
        if (stress_slit==N_SLIT_POS) stress_slit=0;
    }


    #ifdef DEBUG_ANALOG
      //RpipeR filt0 fil1 filt2 filt3 filt4
        uint16_t x[4];
        x[0]=analogRead(PIN_PIPE_POT_R);
        x[1]=analogRead(PIN_HEIGHT_POT_R);
        x[2]=analogRead(PIN_PIPE_POT_B);
        x[3]=analogRead(PIN_HEIGHT_POT_B);
        cout<<"R,"<<x[0]<<","<<(uint32_t)filt0.filter(x[0])<<","<<(uint32_t)filt1.filter(x[0])<<",";
        cout<<(uint32_t)filt2.filter(x[0])<<","<<(uint32_t)filt3.filter(x[0])<<endl;
//        cout<<"B: p="<<(uint32_t)filt2.filter(x[2])<<"("<<x[2]<<") h="<<(uint32_t)filt3.filter(x[3])<<"("<<x[3]<<")\n";
    #endif
    
    //Call run on each shoe
    #ifdef DEBUG_RUN_TIME
        uint32_t t=micros();
    #endif
    
    if (shoeRConnected()) shoeR.run();
    if (shoeBConnected()) shoeB.run();

    #ifdef DEBUG_RUN_TIME
        uint32_t t1=micros();
        //if((t1-t)>80) 
        cout<<"Run at "<<micros()<<" took "<<t1-t<<" us.\n";
    #endif    


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
  } 
  
  return true;
  
}

//Load the nominal slits positions for all the slits from EEPROM
bool loadSlitPositionsFromEEPROM() {
    cout<<F("#Restoring EEPROM slit info")<<endl;
    uint16_t crc, saved_crc;
    eeprom_shoe_data_t data;
    uint8_t mode;
    
    bool ret=false;
    
    #ifdef DEBUG_EEPROM
        uint32_t t=millis();
    #endif
    //Fetch the stored slit positions & CRC16
    EEPROM.get(EEPROM_SLIT_POSITIONS_ADDR, data);
    EEPROM.get(EEPROM_SLIT_POSITIONS_CRC16_ADDR, saved_crc);
    EEPROM.get(EEPROM_MODE_ADDR, mode);
    crc=OneWire::crc16((uint8_t*) &data, sizeof(eeprom_shoe_data_t));  //second to is from the cast

    //If the CRC matches, restore the positions
    if (crc == saved_crc) {
        shoeR.restoreState(data.cfgR);
        shoeB.restoreState(data.cfgB);

//        if (mode==1) {
//            //This will cause the
//        //TODO How does this make things behave e.g. what is the start position?
//            shoeR.movePipe(data.posR.pipe);
//            shoeR.moveHeight(data.posR.height);
//            shoeB.movePipe(data.posB.pipe);
//            shoeB.moveHeight(data.posB.height);
//        }
        ret=true;
    } else {
        cout<<F("#ERROR EEPROM CRC")<<endl;
        return false;
    }

    #ifdef DEBUG_EEPROM
        cout<<"Restoring shoe config from EEPROM took "<<millis()-t<<" ms.\n";
        cout<<"R: P=";
        for (uint8_t i=0;i<N_SLIT_POS;i++) cout<<data.cfgR.pipe_pos[i]<<" ";
        cout<<" H="<<data.cfgR.height_pos[0]<<" "<<data.cfgR.height_pos[1];
        cout<<" Pos="<<data.posR.pipe<<", "<<data.posR.height<<endl;
        cout<<"B: P=";
        for (uint8_t i=0;i<N_SLIT_POS;i++) cout<<data.cfgB.pipe_pos[i]<<" ";
        cout<<" H="<<data.cfgB.height_pos[0]<<" "<<data.cfgB.height_pos[1];
        cout<<" Pos="<<data.posB.pipe<<", "<<data.posB.height<<endl;
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
    shoeB.getState(data.cfgB);    
    shoeR.getState(data.cfgR);
    data.posR = shoeR.getCommandedPosition();
    data.posB = shoeB.getCommandedPosition();

    //Store them with their CRC16
    EEPROM.put(EEPROM_SLIT_POSITIONS_ADDR, data);
    crc=OneWire::crc16((uint8_t*) &data, sizeof(eeprom_shoe_data_t));  //second to is from the cast
    EEPROM.put(EEPROM_SLIT_POSITIONS_CRC16_ADDR, crc);
    #ifdef DEBUG_EEPROM
        cout<<"Saving config to EEPROM took "<<millis()-t<<" ms.\n";
        cout<<"R: P=";
        for (uint8_t i=0;i<N_SLIT_POS;i++) cout<<data.cfgR.pipe_pos[i]<<" ";
        cout<<" H="<<data.cfgR.height_pos[0]<<" "<<data.cfgR.height_pos[1];
        cout<<" Pos="<<data.posR.pipe<<", "<<data.posR.height<<endl;
        cout<<"B: P=";
        for (uint8_t i=0;i<N_SLIT_POS;i++) cout<<data.cfgB.pipe_pos[i]<<" ";
        cout<<" H="<<data.cfgB.height_pos[0]<<" "<<data.cfgB.height_pos[1];
        cout<<" Pos="<<data.posB.pipe<<", "<<data.posB.height<<endl;
    #endif
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





uint8_t bootCount(bool set) {
    uint8_t count;
    count=EEPROM.read(EEPROM_BOOT_COUNT_ADDR);
    if (set==true && count < 200) {
        //increment & save boot count
        EEPROM.write(EEPROM_BOOT_COUNT_ADDR, ++count);
    }
    return count;
}

bool shoeRConnected() {
  return digitalRead(PIN_SHOESENSE_R);
}

bool shoeBConnected() {
  return !digitalRead(PIN_SHOESENSE_B);
}

bool shoeWiresCrossed() {
  //Shoe R ties SHOESENSE to HIGH, Shoe B ties SHOESENSE to LOW
  //PIN_SHOESENSE_R is pulled down
  //PIN_SHOESENSE_B is pulled up
  //No R     No B -> No temp,  PIN_SHOESENSE_B at high,               PIN_SHOESENSE_R at low
  //R to R   No B -> R temp,   PIN_SHOESENSE_B at high,               PIN_SHOESENSE_R pulled high from low
  //R to B   No B -> R temp,   PIN_SHOESENSE_B pulled high from high, PIN_SHOESENSE_R at low
  //No R   B to B -> B temp,   PIN_SHOESENSE_B pulled  low from high, PIN_SHOESENSE_R at low
  //No R   B to R -> B temp,   PIN_SHOESENSE_B pulled high from high, PIN_SHOESENSE_R pulled low from low
  //R to R B to R -> R&B temp, PIN_SHOESENSE_B pulled  low from high, PIN_SHOESENSE_R pulled high from low
  
  bool shoeB=temps[SHOE_B_TEMP].present;
  bool shoeR=temps[SHOE_R_TEMP].present;
  bool shoeBwireB = !digitalRead(PIN_SHOESENSE_B);
  bool shoeRwireR = digitalRead(PIN_SHOESENSE_R);
  bool shoeRwireB = !shoeRwireR && shoeR;
  bool shoeBwireR = !shoeBwireB && shoeB;
  return shoeRwireB || shoeBwireR;
}


//Search through command names for a name that matches the first two
// characters received. Attempt to pull out the shoe specifier and comput argument 
// lengths and buffer offsets. Load everything into the instruction. Return false
// if no command was matched or fewer than two characters received. 
bool parseCommand() {
    //Extract the command from the command_buffer
    String name;
    uint8_t consumed=0;
    instruction.ndx=-1;
    if(command_length >= 2) {
        name+=command_buffer[0];
        name+=command_buffer[1];
        for (uint8_t i=0; i<N_COMMANDS;i++) {
          if (commands[i].name==name) {
            instruction.ndx=i;
            consumed=2;
            break;
          }
        }
    }
    instruction.shoe=NO_SHOE;
    if(command_length >=3){
      if (command_buffer[2]=='R' || command_buffer[2]=='r')
        instruction.shoe=RED_SHOE;
      else if (command_buffer[2]=='B' || command_buffer[2]=='b')
        instruction.shoe=BLUE_SHOE;
    }
    consumed+=(uint8_t)(instruction.shoe!=NO_SHOE);

    instruction.arg_len=command_length-consumed;
    instruction.arg_buffer=&command_buffer[consumed];
    return instruction.ndx!=-1;
}


//Convert a character to a slit number. '1' becomes 0, '2' 1, ...
inline uint8_t charToSlit(char c) { 
    // anything >5 indicates an illegal slit
    return c-'0'-1; //(-1 as slit is specified 1-6)
}

//Clobbers any conversions in progress
void initTempSensors() {
    tempSensors.begin();
    tempSensors.setResolution(12);
    tempSensors.setWaitForConversion(false);
}

//Request and fetch the temperature regularly, ignore rollover edgecase
void monitorTemperature() {
  unsigned long since = millis() - time_of_last_temp_request;
  uint8_t inited=0;

  //In general the controller will probably boot before the shoes are connected
  for (int i=0;i<N_TEMP_SENSORS;i++) inited+=temps[i].present;

  if (tempRetrieved && inited!=N_TEMP_SENSORS) initTempSensors();
  
  if (since > TEMP_UPDATE_INTERVAL_MS) {
    tempSensors.requestTemperatures();
    time_of_last_temp_request=millis();
    tempRetrieved=false;
    since=0;
  }
    
  if(!tempRetrieved && since > DS18B20_12BIT_MAX_CONVERSION_TIME_MS) {
     for (uint8_t i=0; i<N_TEMP_SENSORS; i++) {
       //cout<<F("Fetching temp ")<<(uint16_t)i;
       float x=tempSensors.getTempC(temps[i].address);
       //cout<<" got "<<temps[i].reading<<endl;
       temps[i].present=x>-127.0;
       temps[i].reading= temps[i].present ? x: 999.0;
     }
     tempRetrieved = true;
  }
}


uint8_t getShoeForCommand() {
  char shoe=command_buffer[2];
  if (shoe=='r' || shoe=='R') return SHOE_R;
  else if (shoe=='b' || shoe=='B') return SHOE_B;
  else return 0xFF;
}


#pragma mark Command Handlers

//Zero the boot count and set shoe to uninited
bool ZBcommand(){
  if (instruction.arg_len>0) EEPROM.write(EEPROM_SLIT_POSITIONS_CRC16_ADDR, 0);
  EEPROM.write(EEPROM_BOOT_COUNT_ADDR, 0);
  EEPROM.write(EEPROM_MODE_ADDR, 0);
  return true;
}


//Report the current slit for specified shoe: 1-6,UNKNOWN,INTERMEDIATE,MOVING
bool SGcommand() {
  if ( instruction.shoe==NO_SHOE ) return false;

  shoes[instruction.shoe]->tellCurrentSlit();
  shoepos_t pos = shoes[instruction.shoe]->getFilteredPosition();
  cout<<"("<<pos.pipe<<", "<<pos.height<<")"<<endl;
  return true;
}

//Report the nominial position of the specified slit
bool SDcommand() {
  if ( instruction.shoe==NO_SHOE ) return false;
  ShoeDrive *shoe=shoes[instruction.shoe];

  unsigned char slit=charToSlit(instruction.arg_buffer[0]);
  if ( slit>N_SLIT_POS-1 ) return false;
  
  cout<<shoe->getSlitPosition(slit)<<endl;
  return true;
}

//Report the status bytes
bool TScommand() {
//TO send for each shoe connected shoeXwireX current slit position movementdetected moveinprog temp
//shoeboxtemp
  cout<<endl<<endl<<F("================\n");

  if (shoeRConnected()) cout<<F("R Connected")<<endl;
  if (shoeBConnected()) cout<<F("B Connected")<<endl;
  if (shoeWiresCrossed()) cout<<F("R&B Swapped")<<endl;
  if ( instruction.shoe==NO_SHOE ) {
    cout<<F("------R Shoe")<<endl; shoeR.tellStatus(); 
    cout<<F("------B Shoe")<<endl; shoeB.tellStatus(); 
  } else {
    shoes[instruction.shoe]->tellStatus();
  }
  cout<<F("================\n");
  return true;
}

// Get currrent position/moving/unknown
bool TDcommand(){
  if ( instruction.shoe==NO_SHOE) return false;
  bool moving;
  moving=shoes[instruction.shoe]->moveInProgress();
  if (moving) cout<<F("MOVING (");
  shoes[instruction.shoe]->tellCurrentPosition();
  if (moving) cout<<")";
  cout<<endl;
  return true;
}

//Stop motion of a SHOE
bool STcommand(){
  stresscycles=0;
  if ( instruction.shoe==NO_SHOE) {
    shoeR.stop();
    shoeB.stop();
  } else {
    shoes[instruction.shoe]->stop();
  }
  return true;
}

//Move to a nominal slit position
bool SLcommand() {

  if ( instruction.shoe==NO_SHOE) return false;
  
  if (instruction.arg_len<1) return false;
  uint8_t slit=charToSlit(instruction.arg_buffer[0]);
  if ( slit>N_SLIT_POS-1 ) return false;
    
  if (shoes[instruction.shoe]->moveInProgress()) return false;

  shoes[instruction.shoe]->moveToSlit(slit);

  return true;
}

//Define a nominal slit position
//SS[R|B][#]{#######}\0  without the last number the slit uses the current position
bool SScommand() {
  if ( instruction.shoe==NO_SHOE) return false;

  if (instruction.arg_len<1) return false;
  uint8_t slit=charToSlit(instruction.arg_buffer[0]);
  if ( slit>N_SLIT_POS-1 ) return false;

  if (instruction.arg_len>1){
    if (!(instruction.arg_buffer[1] >='0' && instruction.arg_buffer[1]<='9')) 
    return false;
    long pos=atol(instruction.arg_buffer+1);
    if (pos>MAX_SHOE_POS || pos<0) 
      return false;
    shoes[instruction.shoe]->defineSlitPosition(slit, pos);
  }
  else {
    shoes[instruction.shoe]->defineSlitPosition(slit);
  }

  saveSlitPositionsToEEPROM();
  return true;
}

//Define a motor axis tolerance
//TO[R|B][H|P][1-25]\0
bool TOcommand() {
 
  if ( instruction.shoe==NO_SHOE) return false;
  if (instruction.arg_len<2) return false;
  if (instruction.arg_buffer[0]!='H' && instruction.arg_buffer[0]!='P') return false;
  uint8_t mtol = instruction.arg_buffer[0]=='H' ? MAX_HEIGHT_TOL : MAX_PIPE_TOL;
  long tol=atol(instruction.arg_buffer+1);
  if (tol>mtol || tol<1) 
      return false;
  shoes[instruction.shoe]->defineTol(instruction.arg_buffer[0], tol);

  saveSlitPositionsToEEPROM();
  return true;

}





//HS[R|B][U|D]{#######}\0  without the last number the height uses the current position
bool HScommand() {
  if ( instruction.shoe==NO_SHOE) return false;

  if (instruction.arg_len<1) return false;
  if (instruction.arg_buffer[0] != 'U' && instruction.arg_buffer[0] != 'D') return false;
  
  uint8_t height = instruction.arg_buffer[0]=='U' ? UP_NDX:DOWN_NDX;
  if (instruction.arg_len>1){
    if (!(instruction.arg_buffer[1] >='0' && instruction.arg_buffer[1]<='9')) 
    return false;
    long pos=atol(instruction.arg_buffer+1);
    if (pos>MAX_SHOE_POS || pos<0)  return false;
    shoes[instruction.shoe]->defineHeightPosition(height, pos);
  }
  else {
    shoes[instruction.shoe]->defineHeightPosition(height);
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

    cout<<F("#PC - Print list of commands\n");
    cout<<F("#TS - Tell Status\n");
    cout<<F("#PV - Print Version\n");
    cout<<F("#TE - Report temperatures (B, R, Ctrl)\n");
  
    cout<<F("#TD[R|B] - Tell smoothed ADC pos\n");
    cout<<F("#SG[R|B] - Get the current slit for shoe\n");
    cout<<F("#ST{R|B} - Stop motion, optionally of shoe\n");

    cout<<F("#SL[R|B][1-6] - Move to slit\n");
    cout<<F("#SD[R|B][1-6] - Report defined slit position\n");
    cout<<F("#SS[R|B][1-6]{#} - Set Slit position to the current position. "\
               "If given, second number is used to specify the position.\n");
    cout<<F("#HS[R|B][U|D]{#} - Set up/down positon like SS.\n");
    cout<<F("#TO[R|B][P|H][#] - Set TOlerance of axis\n");

    cout<<F("#CY# - Cycle shoes through all the slits # times\n");
   
    cout<<F("#MV[R|B][P|H][#] - !DANGER! Move the Height or Pipe axis to # (0-1000) without safety checks.\n");
    cout<<F("#IO - Toggle if we idle the motors.\n");
    cout<<F("#ZB - Zero the boot count\n");


    return true;
}

bool CYcommand() {
  stresscycles=0;
  if (instruction.arg_len <1) return false;
  stresscycles=atol(instruction.arg_buffer);
  stress_slit=0;
  return true;
}


bool MVcommand() {
  //MV R|B H|P #  No spaces
  uint16_t pos;
  
  if (instruction.arg_len<2 || instruction.shoe==NO_SHOE) return false;
  pos=max(atol(instruction.arg_buffer+1), 0);
  if (instruction.arg_buffer[0]=='H') shoes[instruction.shoe]->moveHeight(pos);
  else if (instruction.arg_buffer[0]=='P') shoes[instruction.shoe]->movePipe(pos);
  else return false;

  cout<<F("#Moving ")<<(uint16_t) instruction.shoe<<F(" axis ")<<instruction.arg_buffer[0]<<F(" to ")<<pos<<endl;
  return true;
}


bool IOcommand() {
  shoeR.toggleOffWhenIdle();
  shoeB.toggleOffWhenIdle();
  cout<<"#"<<shoeR.getOffWhenIdle()<<endl;
  return true;
}
