#include "pins.h"
#include <SPI.h>         // needed for Arduino versions later than 0018
#include <OneWire.h>
#include <DallasTemperature.h>
#include "Ultravolt.h"
#include <Adafruit_TLC5947.h>
#include <AsyncDelay.h>
#include <Adafruit_TLA202x.h>


/*
Update plan for IFUSheld 2.0 and carrier cards.
PCB becomes a pair. Control shield and HV driver PCB

HV ICs and connectors on sheild change rest do not.

HV driver card each gets
- an LM78L 5V reg
- a TLA2021IRUGR 2channel ADC
- a pair of MCP47xx ICs as before (but each diff addr)
- passives
- IO conn (i2c+select, enable, mode out, 24v power) 7 pins
- HV conn 2 pins

HV board is breaable shy of wires out on current ultravolts

Shield PCB gets as many pating connectors as I can put.

----

Code changes:
- none to temps or led control paths, that is validated, works well, and the hardware isn't changing.

- Ultravolts now use 
  https://github.com/adafruit/Adafruit_TLA202x 

Need to figure out lamp enum and control. All On is probably ok, but I need to check current draw in lab, especially at lamp ignition



*/


//#define DEBUG


#define FIRST_LED_CHAN 0  //6 for the wirewrap board

#if defined(ARDUINO_ARCH_SAMD)  
// for Arduino Zero, output on USB Serial console, 
// remove line below if using programming port to program the Zero!
   #define Serial SerialUSB
#endif

#define VERSION_STRING "1.2"

#define IGNITION_TIME_MS 80  //Takes about 37 ms to stabilize on a resistor
#define VMAX 950
#define IMAX 10

#define N_LAMPS 6
#define N_TEMP_SENSORS 4  //entrance, ifu tower, fiber exit, hoffman
#define ENTRANCE_TEMP 0
#define MIDDLE_TEMP 1
#define EXIT_TEMP 2
#define HOFFMAN_TEMP 3

#define ENTRANCE_TEMP_ADDR 0x8B00000B1DA6B328
#define MIDDLE_TEMP_ADDR 0x0600000B1EC52628
#define EXIT_TEMP_ADDR 0x7700000B1DF37C28
#define HOFFMAN_TEMP_ADDR1 0x2700000C35701C28
#define HOFFMAN_TEMP_ADDR2 0x4E00000C354EB228
#define HOFFMAN_TEMP_ADDR3 0x5E00001186FA2428

#define TEMP_UPDATE_INTERVAL_MS 10000
#define DS18B20_10BIT_MAX_CONVERSION_TIME_MS 188
#define DS18B20_12BIT_MAX_CONVERSION_TIME_MS 750

#define VDAC_ADDR 0x61  //0x62 for wirewrap shield, :(
#define IDAC_ADDR 0x65

//HV Lamps
typedef enum {
  THXE1_LAMP=0,
  BENEAR1_LAMP,
  LIHE1_LAMP,

  THXE2_LAMP,
  BENEAR2_LAMP,
  LIHE2_LAMP,

  THXE_LAMPS, 
  BENEAR_LAMPS,
  LIHE_LAMPS,
  ALL_LAMPS} lamp_t;



Adafruit_MCP4725 vdac, idac; 
Adafruit_TLA202x adc;  //0x49


Ultravolt lamps[N_LAMPS] = {
Ultravolt(PIN_ENABLE_LAMP1, PIN_IMODE_LAMP1, PIN_CSEL_LAMP1, VMAX, IMAX, vdac, idac, adc),
  Ultravolt(PIN_ENABLE_LAMP2, PIN_IMODE_LAMP2, PIN_CSEL_LAMP2, VMAX, IMAX, vdac, idac, adc),
  Ultravolt(PIN_ENABLE_LAMP3, PIN_IMODE_LAMP3, PIN_CSEL_LAMP3, VMAX, IMAX, vdac, idac, adc),
  Ultravolt(PIN_ENABLE_LAMP4, PIN_IMODE_LAMP4, PIN_CSEL_LAMP4, VMAX, IMAX, vdac, idac, adc),
  Ultravolt(PIN_ENABLE_LAMP5, PIN_IMODE_LAMP5, PIN_CSEL_LAMP5, VMAX, IMAX, vdac, idac, adc),
  Ultravolt(PIN_ENABLE_LAMP6, PIN_IMODE_LAMP6, PIN_CSEL_LAMP6, VMAX, IMAX, vdac, idac, adc),
};


//LED Levels
//For PCB 390, 405, WHI, IR?, 740, 770
uint16_t ledlevels[] = {0, 0, 0, 0, 0, 0};  //Maybe for wire wrap 770, 740, IR, white, 405, 390


Adafruit_TLC5947 leddrive = Adafruit_TLC5947(1, AFLED_CLK_PIN, AFLED_DIN_PIN, AFLED_LAT_PIN);


//Temp monitoring
OneWire oneWire(ONEWIRE_PIN);  // Instantiate a oneWire instance
DallasTemperature tempSensors(&oneWire);  //Instantiate temp sensor on oneWire
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

bool device_address_match(DeviceAddress a, uint64_t x){
  DeviceAddress b;
  load_deviceaddress(b,x);
  for (uint8_t i=0;i<8;i++) if (a[i]!=b[i]) return false;
  return true;
}

void load_deviceaddress(DeviceAddress a, uint64_t x) {
  for(uint8_t i=0;i<8;i++) {
    a[i] = x & 0xFF;
    x = x >> 8;
  }
}

//Command buffer
char command_buffer[81];
unsigned char command_buffer_ndx=0;
unsigned char command_length=0;
bool have_command_to_parse=false;


//Commands

#define N_COMMANDS 8

typedef struct {
    String name;
    bool (*callback)();
} Command;

bool PCcommand();
bool LEcommand();
bool HVcommand();
bool TScommand();
bool TEcommand();
bool PVcommand();
bool OFcommand();
bool MIcommand();

const Command commands[]={
    {"LE", LEcommand}, //LEd lamp command
    {"HV", HVcommand}, //HV lamp command
    {"PC", PCcommand}, //Print Commands
    {"TE", TEcommand}, //TEmps Command
    {"TS", TScommand}, //Tell Status(whats on and off)
    {"PV", PVcommand}, //Print Version string
    {"OF", OFcommand},  //OFf (turn all light sources off)
    {"MI", MIcommand}  //Monitor Ignition
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


// function to print a device address
void print1WireAddress(DeviceAddress deviceAddress) {
  Serial.print("0x");
  for (int8_t i = 7; i >=0; i--) {
    if (deviceAddress[i] < 16) Serial.print("0");
    Serial.print(deviceAddress[i], HEX);
  }
}

//=========================
#pragma mark Setup & Loop
//Setup
void setup() {

    // Start serial connection
    Serial.begin(115200);

    //Startup the light controllers


    digitalWrite(PIN_CSEL_LAMP1, HIGH);
    delayMicroseconds(SEL_PIN_DELAY_US);

  //   if (!adc.begin(0x49)) Serial.println("Failed to find TLA202x chip");
  //   adc.setMode(TLA202x_MODE_ONE_SHOT);
  //   adc.setRange(TLA202x_RANGE_6_144_V);
  //   adc.setDataRate(TLA202x_RATE_1600_SPS);
  //   adc.setMux(TLA202x_MUX_AIN0_GND);

  // Serial.print("Data rate set to: ");
  // switch (adc.getDataRate()) {
  //   case TLA202x_RATE_128_SPS: Serial.println("128 SPS");break;
  //   case TLA202x_RATE_250_SPS: Serial.println("250 SPS");break;
  //   case TLA202x_RATE_490_SPS: Serial.println("490 SPS");break;
  //   case TLA202x_RATE_92
    idac.begin(IDAC_ADDR, &Wire);
    vdac.begin(VDAC_ADDR, &Wire);


    for (int i=0; i<N_LAMPS; i++) {
      lamps[i].begin();
    }


    pinMode(AFLED_INHIBIT_PIN, OUTPUT);
    digitalWrite(AFLED_INHIBIT_PIN, HIGH);
    Serial.print(F("#LED Start: "));Serial.println(leddrive.begin());
    for (int i=0;i<24;i++) leddrive.setPWM(i,0);
    leddrive.write();
    
    //Set up temp sensors
    initTempSensors();
    load_deviceaddress(temps[ENTRANCE_TEMP].address, ENTRANCE_TEMP_ADDR);
    load_deviceaddress(temps[MIDDLE_TEMP].address, MIDDLE_TEMP_ADDR);
    load_deviceaddress(temps[EXIT_TEMP].address, EXIT_TEMP_ADDR);
    // load_deviceaddress(temps[HOFFMAN_TEMP].address, HOFFMAN_TEMP_ADDR1);
    load_deviceaddress(temps[HOFFMAN_TEMP].address, 0);

    Serial.println(F("#Searching for temp sensors: "));
    oneWire.reset_search();
    
    DeviceAddress deviceAddress;
    int deviceCount = 0;
    uint64_t x=0;
    // Loop through all devices found on the bus
    while (oneWire.search(deviceAddress)) {
      bool unknown=false;
      deviceCount++;
      for (uint8_t i = 0; i < 8; i++) {
        unknown |= ((deviceAddress[i]!=temps[ENTRANCE_TEMP].address[i]) && 
                    (deviceAddress[i]!=temps[MIDDLE_TEMP].address[i]) &&
                    (deviceAddress[i]!=temps[EXIT_TEMP].address[i]));
          // x+=(uint64_t)deviceAddress[i])<<(8*i);
      }

      if (unknown) {
        Serial.print("Found unknown device: ");
        for (uint8_t i = 0; i < 8; i++) 
          temps[HOFFMAN_TEMP].address[i]=deviceAddress[i];
        print1WireAddress(temps[HOFFMAN_TEMP].address);
        Serial.println();
      }
    }

    Serial.print("Total devices found: ");
    Serial.println(deviceCount);
    
    tempSensors.requestTemperatures();
    time_of_last_temp_request=millis();
    tempRetrieved=false;
}

void initTempSensors() {
    tempSensors.begin();
    tempSensors.setResolution(12);
    tempSensors.setWaitForConversion(false);
}

//Main loop, runs forever, full steam ahead
void loop() {

    monitorTemperature();

    //If the command received flag is set
    if (have_command_to_parse) {
        #ifdef DEBUG
            printCommandBufNfo();
        #endif

        //Find command in commands
        int8_t ndx=getCallbackNdxForCommand();

        #ifdef DEBUG
                Serial.print(F("Callback ndx is "));Serial.println(ndx);
        #endif
        //If not a command respond error
        if (ndx == -1 ) Serial.write("?\n");
        else {
            #ifdef DEBUG
                Serial.print(F("Command is "));Serial.println(commands[ndx].name);
            #endif
            
            if (commands[ndx].callback()) Serial.write(":");
            else Serial.write("?");
        }
        //Reset the command buffer and the command received flag
        have_command_to_parse=false;
        command_buffer_ndx=0;
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

//Request and fetch the temperature regularly, ignore rollover edgecase
void monitorTemperature() {

  unsigned long since = millis() - time_of_last_temp_request;

  if (since > TEMP_UPDATE_INTERVAL_MS) {
    tempSensors.requestTemperatures();
    time_of_last_temp_request=millis();
    tempRetrieved=false;
    since=0;
  }

  if(!tempRetrieved && since > DS18B20_12BIT_MAX_CONVERSION_TIME_MS) {
     for (uint8_t i=0; i<N_TEMP_SENSORS; i++) {
       float x=tempSensors.getTempC(temps[i].address);
       temps[i].present=x>-127.0;
       temps[i].reading= temps[i].present ? x: 999.0;
     }
     tempRetrieved = true;
  }
    
}


#ifdef DEBUG
void printCommandBufNfo(){
  Serial.println(F("Command Buffer Info"));
  Serial.print(F("Buf ndx: "));Serial.print((unsigned int)command_buffer_ndx);
  Serial.print(F(" Cmd len: "));Serial.println((unsigned int)command_length);
  Serial.print(F("Contents:"));Serial.write((const uint8_t*)command_buffer,command_buffer_ndx);
  Serial.write('\n');
}
#endif


bool LEcommand() {
  bool ledon=false;
  int level;
  
  if (command_length<4) return false;
  if (command_length<5 && command_buffer[2]!='?') return false;

  if (command_length>4) {
    level=atoi(&command_buffer[3]);
    if (level<0) level=0;
    if (level>4095) level=4095;
  }

  switch(command_buffer[2]) {
    case '1' : ledlevels[0]=level;
               break;
    case '2' : ledlevels[1]=level;
               break;
    case '3' : ledlevels[2]=level;
               break;
    case '4' : ledlevels[3]=level;
               break;               
    case '5' : ledlevels[4]=level;
               break;
    case '6' : ledlevels[5]=level;
               break;
    case '*' : ledlevels[0]=level;
               ledlevels[1]=level;
               ledlevels[2]=level;
               ledlevels[3]=level;
               ledlevels[4]=level;
               ledlevels[5]=level;
               break;
    case '?' : 
               for (uint8_t i=0; i<6; i++) {
                 if (i!=0) Serial.print(" ");
                 Serial.print(ledlevels[i]);
               }
               Serial.print("\n");
               return true; //Don't bother setting
               break;
    default:
      return false;
  }

  for (int i=0;i<6;i++) ledon|=ledlevels[i]>0;
  if (ledon) digitalWrite(AFLED_INHIBIT_PIN, LOW);
  else digitalWrite(AFLED_INHIBIT_PIN, HIGH);
  for (int i=0;i<6;i++) leddrive.setPWM(i+FIRST_LED_CHAN, ledlevels[i]);  // ch 6-11
  leddrive.write();
  return true;
}


bool HVcommand() {

  //1-n lamp bay # i/ WIRE #i 
  //2=benear  this is LAMP BAY 2 e.g. WIRE 2
  //3=lihe NB this is LAMP BAY 1 e.g. WIRE 1
  //1=thxe NB this is LAMP BAY 3 e.g. WIRE 3

  /*
  HV # ############### \n
  HV##\n <- min command 
  HV?\n
  */
  lamp_t lamp;
  
  if (command_buffer[2]=='?') {
    currentf_t currents[N_LAMPS];

    for (int i=0;i<N_LAMPS;i++) 
      currents[i]=lamps[i].getCurrent();

    for (int i=0;i<N_LAMPS;i++) {
      Serial.print(currents[0]);
      if (i!=N_LAMPS-1) Serial.print(" ");
    }
    Serial.println();
    return true;
  }


  if (command_buffer[2]-'1' < N_LAMPS) {
    lamp = (lamp_t) command_buffer[2]-'1';
  } else if (command_buffer[2] == '*') {
    lamp = ALL_LAMPS; 
  } else 
    return false;


  if (command_length < 4) 
    return false;
  

  long param=255;
  lamp_t sublamp=255;
  

  param = strtol(command_buffer+3, NULL, 10);

  if (param<0 ) //|| (param==0 && command_buffer[3] !='0'))
     return false;
  if (lamp==ALL_LAMPS) {
    for (int i=0;i<N_LAMPS;i++) lamps[i].turnOn((current_t) param);
  } else {
    lamps[lamp].turnOn((current_t) param);
  }

  return true;

}


bool MIcommand() {
  /* HV##\n */
  lamp_t lamp;
  
  if (command_buffer[2]-'1'<N_LAMPS) {
    lamp = (lamp_t) command_buffer[2]-'1';
  } else 
    return false;

  if (command_length < 4) 
    return false;
  
  long param = strtol(command_buffer+3, NULL, 10);
  if (param<0 || (param==0 && command_buffer[3] !='0'))
     return false;
     
  lamps[lamp].setCurrentLimit((current_t) param);
  lamps[lamp].monitorIgnition(IGNITION_TIME_MS);
  
  return true;
}

//Report the last temp reading
bool TEcommand() {
    for (int i=0; i< N_TEMP_SENSORS; i++) {
        if (i!=N_TEMP_SENSORS-1) {
          Serial.print(temps[i].reading, 4);
          Serial.print(",");
        } else {
          Serial.println(temps[i].reading, 4);
        }
    }
    return true;
}

bool TScommand() {
  Serial.println("LEDs");
  Serial.print(F(" UV (390): "));Serial.print(ledlevels[0]);Serial.print(F("  BL (410): "));Serial.print(ledlevels[1]);
  Serial.print(F("  White : "));Serial.println(ledlevels[2]);
  Serial.print(F(" IR (740): "));Serial.print(ledlevels[3]);Serial.print(F("  IR (770): "));Serial.print(ledlevels[4]);
  Serial.print(F("  IR (850): "));Serial.println(ledlevels[5]);

  Serial.println(F("Temps:"));
  for (int i=0;i<N_TEMP_SENSORS-1;i++) {
    Serial.print(temps[i].reading);
    Serial.print(", "); 
  }
  Serial.println(temps[N_TEMP_SENSORS-1].reading, 3);


  for (int i=0; i<N_LAMPS; i++) {
    Serial.print(F("Lamp "));Serial.print(i);Serial.print(F(" is "));
    Serial.print(lamps[i].isEnabled() ? F("enabled") : F("disabled"));
    Serial.print(F(", running in "));Serial.print(lamps[i].isCurrentMode() ? "voltage":"current");Serial.println(F(" mode"));
    Serial.print(lamps[i].getVoltage());Serial.print(F(" V ("));Serial.print(lamps[i].getVoltageLimit());Serial.print(F(" lim)  "));
    Serial.print(lamps[i].getCurrent());Serial.print(F(" mA ("));Serial.print(lamps[i].getCurrentLimit());Serial.println(F(" lim)"));
  }
  
  return true;
}

//Print the commands
bool PCcommand() {
    Serial.println(F("#PC    Print Commands - Print this list of commands"));
    Serial.println(F("#LEx#  Led command - Set LED x, 1-6 to #, 0-4095 illumination"));
    Serial.println(F("#HVx#  High Voltage - Set HV lamp x=1-3 (THXE, BENEAR, LIHE), to #=0-20 (mA)"));
    Serial.println(F("#HV4x# High Voltage - Set HV boost lamp x=1-3 (THXE, BENEAR, LIHE), to #=0-20 (mA)"));
    Serial.println(F("#OF    Off - Turn all light sources off"));
    Serial.println(F("#TS    Tell Status - Tell the status"));
    Serial.println(F("#PV    Print Version - Print the version string"));
    Serial.println(F("#TE    Temperature - Report all temperatures"));
    Serial.println(F("#MIx#  Monitor Ignition - Monitor Ignition of x=1-3 (THXE, BENEAR, LIHE) to # #=0-20 (mA)"));
    return true;
}

//Turn everything off
bool OFcommand() {
  for (int i=0;i<6;i++) {
    ledlevels[i]=0;
    leddrive.setPWM(i+6, 0);
  }
  digitalWrite(AFLED_INHIBIT_PIN, HIGH);
  for (int i=0; i<N_LAMPS; i++) lamps[i].turnOff();
  return true;
}

//Print the version
bool PVcommand() {
    Serial.println(F(VERSION_STRING));
    return true;
}
