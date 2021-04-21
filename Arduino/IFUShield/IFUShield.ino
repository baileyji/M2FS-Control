#include "pins.h"
#include <SPI.h>         // needed for Arduino versions later than 0018
#include <OneWire.h>
#include <DallasTemperature.h>
#include "Ultravolt.h"
#include <Adafruit_TLC5947.h>

//#define DEBUG

#define FIRST_LED_CHAN 0  //6 for the wirewrap board

#if defined(ARDUINO_ARCH_SAMD)  
// for Arduino Zero, output on USB Serial console, 
// remove line below if using programming port to program the Zero!
   #define Serial SerialUSB
#endif

#define VERSION_STRING "1.0"
//28B3A61D0B00008B


//28B24E350C00004E pcb temp 1

#define IGNITION_TIME_MS 80  //Takes about 37 ms to stabilize on a resistor
#define VMAX 800
#define IMAX 10

#define N_TEMP_SENSORS 4  //entrance, ifu tower, fiber exit, hoffman
#define TEMP_UPDATE_INTERVAL_MS 10000
#define DS18B20_10BIT_MAX_CONVERSION_TIME_MS 188
#define DS18B20_12BIT_MAX_CONVERSION_TIME_MS 750

#define DAC_ADDR 0x61  //0x62 for wirewrap shield, :(

//HV Lamps
typedef enum {THXE_LAMP=0, BENEAR_LAMP=1, LIHE_LAMP=2, ALL_LAMPS=3} lamp_t;
Adafruit_MCP4725 dac; 
Ultravolt benear = Ultravolt(PIN_IMON_BENEAR, PIN_VMON_BENEAR, PIN_ENABLE_BENEAR, PIN_VMODE_BENEAR,
                            PIN_IMODE_BENEAR, PIN_IA0_BENEAR, PIN_VA0_BENEAR, VMAX, IMAX, dac);
Ultravolt lihe = Ultravolt(PIN_IMON_LIHE, PIN_VMON_LIHE, PIN_ENABLE_LIHE, PIN_VMODE_LIHE,
                            PIN_IMODE_LIHE, PIN_IA0_LIHE, PIN_VA0_LIHE, VMAX, IMAX, dac);
Ultravolt thxe = Ultravolt(PIN_IMON_THXE, PIN_VMON_THXE, PIN_ENABLE_THXE, PIN_VMODE_THXE,
                            PIN_IMODE_THXE, PIN_IA0_THXE, PIN_VA0_THXE, VMAX, IMAX, dac);

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
unsigned long time_since_last_temp_request=0xFFFFFFFF;


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
  for (uint8_t i = 0; i < 8; i++) {
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
    dac.begin(DAC_ADDR);
    thxe.begin();
    benear.begin();
    lihe.begin();

    pinMode(AFLED_INHIBIT_PIN, OUTPUT);
    digitalWrite(AFLED_INHIBIT_PIN, HIGH);
    Serial.print(F("LED Start: "));Serial.println(leddrive.begin());
    for (int i=0;i<24;i++) leddrive.setPWM(i,0);
    leddrive.write();
    
    //Set up temp sensors
    tempSensors.begin();
    tempSensors.setResolution(12);
    tempSensors.setWaitForConversion(false);

    Serial.println(F("Searching for temp sensors: "));
    for (int i=0;i<N_TEMP_SENSORS;i++) {
      uint8_t addr;
      bool sensorFound;
      temps[i].present = tempSensors.getAddress(temps[i].address, i);
      if (temps[i].present) {
        Serial.print(F("Found one at: "));print1WireAddress(temps[i].address);
        Serial.println("");
      }        
    }
    Serial.println(F(" done searching."));
    tempSensors.requestTemperatures();
    time_of_last_temp_request=millis();
    tempRetrieved=false;


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
  /*
  HV # ############### \n
  HV##\n <- min command 
  HV?\n
  */
  lamp_t lamp;
  
  if (command_buffer[2]=='?') {
//    current_t lamplevels[N_LAMPS];
//    for (int i=0; i<N_LAMPS; i++) {
//      lamplevels[i] = hvcontrol.isLampEnabled(i) ? active.current : 0;
//    }
//    char buf[16]; // "0000 0000 0000\n"
//    buf[16]=0;
    Serial.print(benear.getCurrent());
    Serial.print(" ");
    Serial.print(lihe.getCurrent());
    Serial.print(" ");
    Serial.println(thxe.getCurrent());
//    sprintf(buf,"%02d %02d %02d\n", lamplevels[0],lamplevels[1],lamplevels[2]);
//    Serial.write(buf, 16);

    return true;
  }


  if (command_buffer[2]>= '1' && command_buffer[2] <='3') {
    lamp = (lamp_t) command_buffer[2]-'1';
  } else if (command_buffer[2] == '*') {
    lamp = ALL_LAMPS; 
  } else return false;


  if (command_length > 4){
    long param = strtol(command_buffer+3, NULL, 10);
    if (param<0 || (param==0 && command_buffer[3] !='0'))
       return false;
    switch(lamp) {
        case BENEAR_LAMP : benear.turnOn((current_t) param);
                           break;
        case THXE_LAMP   : thxe.turnOn((current_t) param);
                           break;
        case LIHE_LAMP   : lihe.turnOn((current_t) param);
                           break;
        case ALL_LAMPS   : lihe.turnOn((current_t) param);
                           benear.turnOn((current_t) param);
                           thxe.turnOn((current_t) param);
                           break;
    }
    return true;
  } else return false;

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
  
  return true;
}

//Print the commands
bool PCcommand() {
    Serial.println(F("#PC   Print Commands - Print this list of commands"));
    Serial.println(F("#LEx# Led command - Set LED x (1-6) to # (0-4095) illumination"));
    Serial.println(F("#HVx# High Voltage - Set HV lamp x to # illumination, all others off"));
    Serial.println(F("#OF   Off - Turn all light sources off"));
    Serial.println(F("#TS   Tell Status - Tell the status"));
    Serial.println(F("#PV   Print Version - Print the version string"));
    Serial.println(F("#TE   Temperature - Report all temperatures"));
    Serial.println(F("#MIx#   Monitor Ignition - Monitor Ignition of x to #"));
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
  return true;
}

//Print the version
bool PVcommand() {
    Serial.println(F(VERSION_STRING));
    return true;
}
