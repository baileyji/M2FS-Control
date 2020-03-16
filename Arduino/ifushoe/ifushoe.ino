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
const bool leave_shoe_on_when_idle=true; //This does nothing without relays between the LACs and the shoes


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

enum Shoe {RED_SHOE=SHOE_R, BLUE_SHOE=SHOE_B, NO_SHOE};

typedef struct {
    Shoe shoe;
    int8_t ndx;
    unsigned char arg_len;
    char arg_buffer[];
} Instruction;

Instruction instruction;

//Commands
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
bool STcommand();
bool TDcommand();
bool TEcommand();
bool TScommand();
bool ZBcommand();
bool MVcommand();

const Command commands[N_COMMANDS]={
    
    //Cycle tetris A N times from stressBottomP to stressTopP
    {"CY", CYcommand, false, true},

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
    //Stop moving
    {"ST", STcommand, false, true},
    //Tell Step Position (# UKNOWN MOVING)
    {"TD", TDcommand, false, true},
    //Report temperature
    {"TE", TEcommand, true, false},
    //Tell Status (e.g. moving vreg, etc)
    {"TS", TScommand, true, false},
    //Zero the boot count
    {"ZB",ZBcommand, true, false},
    //Directly move an axis on a given shoe 
    {"MV", MVcommand, true, true}
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

    //In general the controller will probably boot before the shoes are connected
    for (int i=0;i<N_TEMP_SENSORS;i++) if (!temps[i].present) initTempSensors();
    monitorTemperature();

    //If the command received flag is set
    if (have_command_to_parse) {
        #ifdef DEBUG_COMMAND
            printCommandBufNfo();
        #endif

        //If not a command respond error
        if (!parseCommand()) {
            Serial.write("?\n");
        } else {

            Command *cmd=commands[instruction.ndx];

            #ifdef DEBUG_COMMAND
                cout<<"ShoeR "<<(shoeOnlineR ? "ON":"OFF")<<endl;
                cout<<"ShoeB "<<(shoeOnlineB ? "ON":"OFF")<<endl;
                cout<<"Command is ";Serial.println(cmd->name);
            #endif
            
            //Ensure stresscycles=0 if command is CY
            if (cmd->name == "CY") 
              stresscycles=0;
            
            if (shoesWiresCrossed()) {
                cout<<F("Wires Crossed\n:");
            } else if (instruction.shoe==NO_SHOE && cmd->shoeRequired){
                Serial.write("?");
            } else if (instruction.shoe==RED_SHOE && !cmd->allowOffline && !shoeRconnected()) {
                cout<<F("Shoe R Disconnected\n:");
            } else if (instruction.shoe==BLUE_SHOE && !cmd->allowOffline && !shoeBconnected()) {
                cout<<F("Shoe B Disconnected\n:");
            } else {
                //Execute the command 
                bool commandGood;
                commandGood=cmd->callback();
                Serial.write(commandGood ? ":" : "?");
            }
        }
        //Reset the command buffer and the command received flag
        have_command_to_parse=false;
        command_buffer_ndx=0;
    }
  
    if (shoeRconnected()) shoeOnlineMainR();
    if (shoeBconnected()) shoeOnlineMainB(); 

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


bool shoeRconnected() {
  return digitalRead(SHOE_SENSE_R_PIN);
}

bool shoeBconnected() {
  return !digitalRead(SHOE_SENSE_B_PIN);
}

bool shoesWiresCrossed() {
  //Shoe R ties SHOESENSE to HIGH, Shoe B ties SHOESENSE to LOW
  //SHOE_SENSE_R_PIN is pulled down
  //SHOE_SENSE_B_PIN is pulled up
  bool shoeB=temps[SHOE_B_TEMP].present;
  bool shoeR=temps[SHOE_R_TEMP].present;
  bool shoeBwireB = !digitalRead(SHOE_SENSE_B_PIN);
  bool shoeRwireR = digitalRead(SHOE_SENSE_R_PIN);
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
    instruction.cmd_ndx=-1;
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
      if (command_length[2]=='R' || command_length[2]=='r')
        instruction.shoe=RED_SHOE;
      else if (command_length[2]=='B' || command_length[2]=='B')
        instruction.shoe=BLUE_SHOE;
    }
    consumed+=(uint8_t)(instruction.shoe!=NO_SHOE);

    instruction.arg_len=command_length-consumed;
    instruction.arg_buffer=command_buffer+consumed;
    
    return instruction.ndx!=-1;
}


//Convert a character to a slit number. '1' becomes 0, '2' 1, ...
inline uint8_t charToSlit(char c) { 
    // anything >5 indicates an illegal slit
    return c-'0'-1; //(-1 as slit is specified 1-6)
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


//Tasks to execute every main loop iteration when the shoe is online 
void shoeOnlineMain() {
    //Stress testing code
    if (stresscycles>0 && !shoes[0].moving()) {
        stresscycles--;
        if (shoeRConnected()) shoeR.moveToSlit(stress_slit);
        if (shoeBConnected()) shoeB.moveToSlit(stress_slit);
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
    
    if (shoeRConnected()) shoeR.run();
    if (shoeBConnected()) shoeB.run();

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
    // NB this is a NO OP unless relays are added between the LAC boards and the shoes
    if (!leave_shoe_on_when_idle) {     
        if (shoeR.idle()) shoeR.motorsOff();
        if (shoeB.idle()) shoeB.motorsOff();
    }
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


//Report the current slit for specified shoe: 1-6,UNKNOWN,INTERMEDIATE,MOVING
bool SGcommand() {
  if ( instruction.shoe==NO_SHOE ) return false;

  Shoe *shoe=&shoes[instruction.shoe];
  
  if(shoe->moving()) 
    cout<<F("MOVING");
  else {
    uint8_t slit=shoe->getCurrentSlit(); //0-5 or 0xFF = INTERMEDIATE, 0xFE = MOVING
    if (slit<6) cout<<slit+1;
    else
      shoepos_t pos = shoe->getCurrentPosition();
      if (slit==0xFF) cout<<F("INTERMEDIATE (");
      else cout<<F("MOVING (");
      cout<<pos.pipe<<", "<<pos.height<<")";
    }
  }
  cout<<endl;
  return true;
}

//Report the nominial position of the specified slit
bool SDcommand() {
  if ( instruction.shoe==NO_SHOE ) return false;
  Shoe *shoe=&shoes[instruction.shoe];

  unsigned char slit=charToSlit(instruction.arg_buffer[0]);
  if ( slit>N_SLIT_POS-1 ) return false;

  shoe->tellSlitPosition(slit);
  cout<<endl;
  return true;
}

//Report the status bytes
bool TScommand() {
//TO send for each shoe connected shoeXwireX current slit position movementdetected moveinprog temp
//shoeboxtemp
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

  uint8_t slit=charToSlit(command_buffer[3]);
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

  uint8_t slit=charToSlit(command_buffer[3]);
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
