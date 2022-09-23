#include "pins.h"
#include <SPI.h>         // needed for Arduino versions later than 0018
#include <OneWire.h>
#include <DallasTemperature.h>
#include "Ultravolt.h"
#include <Adafruit_TLC5947.h>
#include <AsyncDelay.h>
#include <SoftWire.h>

//#define DEBUG
char swi2cTxBuffer[16];
char swi2cRxBuffer[16];
SoftWire i2c(PIN_SDA2, PIN_SCL2);

#define FIRST_LED_CHAN 0  //6 for the wirewrap board

#if defined(ARDUINO_ARCH_SAMD)  
// for Arduino Zero, output on USB Serial console, 
// remove line below if using programming port to program the Zero!
   #define Serial SerialUSB
#endif

#define VERSION_STRING "1.1"

#define IGNITION_TIME_MS 80  //Takes about 37 ms to stabilize on a resistor
#define VMAX 950
#define IMAX 20

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

#define TEMP_UPDATE_INTERVAL_MS 10000
#define DS18B20_10BIT_MAX_CONVERSION_TIME_MS 188
#define DS18B20_12BIT_MAX_CONVERSION_TIME_MS 750

#define DAC_ADDR 0x61  //0x62 for wirewrap shield, :(

//HV Lamps
typedef enum {THXE_LAMP=0, BENEAR_LAMP=1, LIHE_LAMP=2, ALL_LAMPS=3, USER_LAMP=4} lamp_t;
Adafruit_MCP4725 dac; 
Ultravolt benear = Ultravolt(PIN_IMON_BENEAR, PIN_VMON_BENEAR, PIN_ENABLE_BENEAR, PIN_VMODE_BENEAR,
                            PIN_IMODE_BENEAR, PIN_IA0_BENEAR, PIN_VA0_BENEAR, VMAX, IMAX, dac);
Ultravolt lihe = Ultravolt(PIN_IMON_LIHE, PIN_VMON_LIHE, PIN_ENABLE_LIHE, PIN_VMODE_LIHE,
                            PIN_IMODE_LIHE, PIN_IA0_LIHE, PIN_VA0_LIHE, VMAX, IMAX, dac);
Ultravolt thxe = Ultravolt(PIN_IMON_THXE, PIN_VMON_THXE, PIN_ENABLE_THXE, PIN_VMODE_THXE,
                            PIN_IMODE_THXE, PIN_IA0_THXE, PIN_VA0_THXE, VMAX, IMAX, dac);

//int thxe_pin, int benear_pin, int lihe_pin
//This is correct because lamp colors are 123 but lamps are in bays 654
UltravoltMultilamp lamp4 = UltravoltMultilamp(PIN_LAMP4_ENABLE, PIN_LAMP4_3, PIN_LAMP4_2, 
                                              PIN_LAMP4_1, VMAX, IMAX, i2c); 
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


    dac.begin(DAC_ADDR, &Wire);
    thxe.begin();
    benear.begin();
    lihe.begin();

    i2c.setTxBuffer(swi2cTxBuffer, sizeof(swi2cTxBuffer));
    i2c.setRxBuffer(swi2cRxBuffer, sizeof(swi2cRxBuffer));
    i2c.setDelay_us(5);
    i2c.setTimeout(1000);
    //i2c.enablePullups(false);
    i2c.setClock(400000); // Set I2C frequency to desired speed
    i2c.begin();
    lamp4.begin();

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
    load_deviceaddress(temps[HOFFMAN_TEMP].address, HOFFMAN_TEMP_ADDR1);


    Serial.println(F("#Searching for temp sensors: "));
    for (int i=0;i<N_TEMP_SENSORS;i++) {
      DeviceAddress x;
      bool present;
      present = tempSensors.getAddress(x, i);
      if (present) {
        Serial.print(F("#Found sensor at: "));print1WireAddress(x);Serial.println("");
        if (device_address_match(x, HOFFMAN_TEMP_ADDR2)) {
          load_deviceaddress(temps[HOFFMAN_TEMP].address, HOFFMAN_TEMP_ADDR2);
        }
      }        
    }
    Serial.println(F("# done searching."));
    
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
  //2=benear  this is LAMP BAY 2 e.g. WIRE 2
  //3=lihe NB this is LAMP BAY 1 e.g. WIRE 1
  //1=thxe NB this is LAMP BAY 3 e.g. WIRE 3
  //4#=selectable HV4[lamp][current]
  //42=benear  this is LAMP BAY 5 e.g. WIRE 5
  //43=lihe NB this is LAMP BAY 4 e.g. WIRE 4
  //41=thxe NB this is LAMP BAY 6 e.g. WIRE 6
/*
 * presently L3=W6 into wire5 bay 5 and L1=W4 goes wire 6
 */
  
  /*
  HV # ############### \n
  HV##\n <- min command 
  HV?\n
  */
  lamp_t lamp;
  
  if (command_buffer[2]=='?') {
    currentf_t currents[3];
    currents[1]=benear.getCurrent();
    currents[2]=lihe.getCurrent();
    currents[0]=thxe.getCurrent();
    if (lamp4.getSelectedLamp()<3) {
      currents[lamp4.getSelectedLamp()]+=lamp4.getCurrent();
    }
    Serial.print(currents[0]);
    Serial.print(" ");
    Serial.print(currents[1]);
    Serial.print(" ");
    Serial.println(currents[2]);
//    Serial.print(" ");
//    Serial.println(lamp4.getCurrent());
    return true;
  }


  if (command_buffer[2]-'1' < 4) {
    lamp = (lamp_t) command_buffer[2]-'1';
    if (command_buffer[2]=='4') lamp=USER_LAMP;
  } else if (command_buffer[2] == '*') {
    lamp = ALL_LAMPS; 
  } else return false;


  if (command_length < 4) return false;
  
  long param=255;
  lamp_t sublamp=255;
  
  if (lamp==USER_LAMP) {
    if (command_length<5) return false;
    else {
      //THXE_LAMP=0='1', BENEAR_LAMP=1='2', LIHE_LAMP=2='3'
      sublamp = (lamp_t) command_buffer[3]-'1'; 
      if (sublamp!=LIHE_LAMP && 
          sublamp!=BENEAR_LAMP && 
          sublamp!=THXE_LAMP)
        return false;
    }
    param = strtol(command_buffer+4, NULL, 10);
  } 
  else {
    param = strtol(command_buffer+3, NULL, 10);
  }
  if (param<0 ) //|| (param==0 && command_buffer[3] !='0'))
     return false;
  switch(lamp) {
      case BENEAR_LAMP : benear.turnOn((current_t) param);
                         break;
      case THXE_LAMP   : thxe.turnOn((current_t) param);
                         break;
      case LIHE_LAMP   : lihe.turnOn((current_t) param);
                         break;
      case USER_LAMP   : lamp4.turnOn((current_t) param, (uint8_t) sublamp);
                         break;
      case ALL_LAMPS   : lihe.turnOn((current_t) param);
                         benear.turnOn((current_t) param);
                         thxe.turnOn((current_t) param);
                         break;
  }
  return true;

}


bool MIcommand() {
  /* HV##\n */
  lamp_t lamp;
  
  if (command_buffer[2]>= '1' && command_buffer[2] <='3') {
    lamp = (lamp_t) command_buffer[2]-'1';
  } else return false;

  if (command_length < 4) 
    return false;
  
  long param = strtol(command_buffer+3, NULL, 10);
  if (param<0 || (param==0 && command_buffer[3] !='0'))
     return false;
     
  switch(lamp) {
      case BENEAR_LAMP : benear.setCurrentLimit((current_t) param);
                         benear.monitorIgnition(IGNITION_TIME_MS);
                         break;
      case THXE_LAMP   : thxe.setCurrentLimit((current_t) param);
                         thxe.monitorIgnition(IGNITION_TIME_MS);
                         break;
      case LIHE_LAMP   : lihe.setCurrentLimit((current_t) param);
                         lihe.monitorIgnition(IGNITION_TIME_MS);
                         break;
  }
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


  Serial.print(F("ThXe Lamp is "));
  if (!thxe.isEnabled()) Serial.print(F("disabled"));
  else Serial.print(F("enabled"));
  Serial.print(F(", running in "));Serial.print(thxe.isVoltageMode() ? "voltage":"current");Serial.println(F(" mode"));
  Serial.print(thxe.getVoltage());Serial.print(F(" V ("));Serial.print(thxe.getVoltageLimit());Serial.print(F(" lim)  "));
  Serial.print(thxe.getCurrent());Serial.print(F(" mA ("));Serial.print(thxe.getCurrentLimit());Serial.println(F(" lim)"));

  Serial.print(F("BeNeAr Lamp is "));
  if (!benear.isEnabled()) Serial.print(F("disabled"));
  else Serial.print(F("enabled"));
  Serial.print(F(", running in "));Serial.print(benear.isVoltageMode() ? "voltage":"current");Serial.println(F(" mode"));
  Serial.print(benear.getVoltage());Serial.print(F(" V ("));Serial.print(benear.getVoltageLimit());Serial.print(F(" lim)  "));
  Serial.print(benear.getCurrent());Serial.print(F(" mA ("));Serial.print(benear.getCurrentLimit());Serial.println(F(" lim)"));
  
  Serial.print(F("LiHe Lamp is "));
  if (!lihe.isEnabled()) Serial.print(F("disabled"));
  else Serial.print(F("enabled"));
  Serial.print(F(", running in "));Serial.print(lihe.isVoltageMode() ? "voltage":"current");Serial.println(F(" mode"));
  Serial.print(lihe.getVoltage());Serial.print(F(" V ("));Serial.print(lihe.getVoltageLimit());Serial.print(F(" lim)  "));
  Serial.print(lihe.getCurrent());Serial.print(F(" mA ("));Serial.print(lihe.getCurrentLimit());Serial.println(F(" lim)"));
  
  Serial.print(F("Lamp 4 is "));
  if (!lamp4.isEnabled()) Serial.print(F("disabled"));
  else Serial.print(F("enabled"));
  Serial.print(F(", lamp "));Serial.print((uint16_t)lamp4.getSelectedLamp());Serial.println(" selected.");
  Serial.print(lamp4.getVoltageLimit());Serial.print(F(" V "));Serial.print(lamp4.getCurrentLimit());Serial.println(F(" mA "));
  
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
  lihe.turnOff();
  thxe.turnOff();
  benear.turnOff();
  lamp4.turnOff();
  return true;
}

//Print the version
bool PVcommand() {
    Serial.println(F(VERSION_STRING));
    return true;
}
