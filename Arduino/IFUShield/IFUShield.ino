#include <SPI.h>         // needed for Arduino versions later than 0018
#include <OneWire.h>
#include <DallasTemperature.h>
#include "HVLamp.h"
#include <Adafruit_TLC5947.h>


#define TEMP_UPDATE_INTERVAL_MS 10000
#define DS18B20_10BIT_MAX_CONVERSION_TIME_MS 188
#define DS18B20_12BIT_MAX_CONVERSION_TIME_MS 750

//TODO NONE of the pins are final!


//These are Arduino Pins, e.g. args to digitalWrite
#define AFLED_LAT_PIN 4 //pin 11
#define AFLED_CLK_PIN 1 //pin 7
#define AFLED_DIN_PIN 2 //pin 8

#define SDA_PIN 4 //pin 10
#define SCL_PIN 0 //pin 6

#define ONEWIRE_PIN 3
#define N_TEMP_SENSORS 4

Adafruit_TLC5947 leddrive = Adafruit_TLC5947(1, AFLED_CLK_PIN, AFLED_DIN_PIN, AFLED_LAT_PIN);
HVLamp hvcontrol = HVLamp();

//LED Levels
uint16_t ledlevels[] = {0, 0, 0, 0, 0, 0};

//Temp monitoring
OneWire oneWire(ONEWIRE_PIN);  // Instantiate a oneWire instance
DallasTemperature tempSensors(&oneWire);  //Instantiate temp sensor on oneWire
typedef struct {
    uint8_t address;
    float reading=0.0;
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


#if defined(ARDUINO_ARCH_SAMD)  
// for Arduino Zero, output on USB Serial console, 
// remove line below if using programming port to program the Zero!
   #define Serial SerialUSB
#endif


//Commands
typedef struct {
    String name;
    bool (*callback)();
} Command;


bool PCcommand();
bool LEcommand();
bool HVcommand();
bool TScommand();
bool TEcommand();


#define N_COMMANDS 5
const Command commands[]={
    {"LE", LEcommand},
    {"HV", HVcommand},
    {"PC", PCcommand}, //Print Commands
    {"TE", TEcommand}, //Report temps
    {"TS", TScommand},  //Report all status (whats on and off)
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


//=========================
#pragma mark Setup & Loop
//Setup
void setup() {

    //Startup the light controllers 
    hvcontrol.begin();
    leddrive.begin();
    
    //Set up temp sensor
    tempSensors.begin();
    tempSensors.setResolution(12);
    tempSensors.setWaitForConversion(false);

    for (int i=0;i<N_TEMP_SENSORS;i++) {
      uint8_t addr;
      bool sensorFound;
      sensorFound = tempSensors.getAddress(&addr, i);
      temps[i].address = sensorFound ? addr: 0;         
    }
    tempSensors.requestTemperatures();
    time_of_last_temp_request=millis();
    tempRetrieved=false;

    // Start serial connection
    Serial.begin(115200);
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
       for (uint8_t i=0; i<N_TEMP_SENSORS; i++)
          temps[i].reading=tempSensors.getTempC(temps[i].address);
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
  if (command_length<4) return false;
  if (command_length<5 && command_buffer[2]!='?') return false;

  int level;
  if (command_length>4) {
    level=atoi(&command_buffer[4]);
    if (level<0) level=0;
    if (level>4096) level=4096;
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
    case '?' : char buf[31]; // "0000 0000 0000 0000 0000 0000\n"
               buf[31]=0;
               sprintf(buf,"%04d %04d %04d %04d %04d %04d\n", 
                       ledlevels[0],ledlevels[1],ledlevels[2],ledlevels[3],ledlevels[4],ledlevels[5]);
               Serial.write(buf, 31);
               return true; //Don't bother setting
               break;
  }
  for (int i=0;i<6;i++) leddrive.setPWM(i, ledlevels[i]);
  return true;
}


bool HVcommand() {
  /*
  HV # ############### \n
  HV##\n <- min command 
  */
  if (command_buffer[2]=='?') {
    lampstatus_t active = hvcontrol.getActiveLamp();
    switch (active.lamp) {
        case THAR_LAMP:
            Serial.print(F("ThAr "));
            Serial.println(active.current);
            break;
        case THNE_LAMP:
            Serial.print(F("ThNe "));
            Serial.println(active.current);
            break;
        case HG_LAMP:
            Serial.print(F("Hg "));
            Serial.println(active.current);
            break;
        case NE_LAMP:
            Serial.print(F("Ne "));
            Serial.println(active.current);
            break;
        case HE_LAMP:
            Serial.print(F("He "));
            Serial.println(active.current);
            break;
        case NONE_LAMP:
            Serial.println(F("Off"));
            break;
        default:
            Serial.println(F("ERROR"));
            break;
    }
    return true;
  }

  //TODO make this work with the lamp_t enum
  lamp_t lamp;
  if (command_buffer[2]>= '1' && command_buffer[2] <='5') {
    lamp = (lamp_t) command_buffer[2]-'1';
  } else {
    return false;
  }
  
  if (command_length > 4){
    if (!((command_buffer[3] >='0' && command_buffer[3]<='9') || 
          ((command_buffer[3] =='+' && command_length> 5) &&
          command_buffer[4] >='0' && command_buffer[4]<='9' ))) 
       return false;  
    unsigned int param = atoi(command_buffer+3);
    hvcontrol.turnOn(lamp, (current_t) param);
    return true;
  } else {
    return false;
  }

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
  Serial.print(F(" UV (390): "));Serial.print(ledlevels[0]);Serial.print(F("BL (410): "));Serial.print(ledlevels[1]);
  Serial.print(F("White : "));Serial.println(ledlevels[2]);
  Serial.print(F(" IR (740): "));Serial.print(ledlevels[3]);Serial.print(F("IR (770): "));Serial.print(ledlevels[4]);
  Serial.print(F("IR (850): "));Serial.println(ledlevels[5]);

  Serial.println(F("Temps:"));
  for (int i=0;i<N_TEMP_SENSORS-1;i++) {
    Serial.print(temps[i].reading, 3);
    Serial.print(", "); 
  }
  Serial.println(temps[N_TEMP_SENSORS-1].reading, 3);

  Serial.print(F("HV Lamps:\nHV Supply\n"));

  if (hvcontrol.isEnabled()) {
    Serial.println(F("Disabled"));
  } else {
    Serial.print(F("Enabled, running in "));Serial.print(hvcontrol.isVoltageMode() ? "voltage":"current");Serial.println(F(" mode"));
    Serial.print(hvcontrol.getVoltage());Serial.print(F(" V ("));Serial.print(hvcontrol.getVoltageLimit());Serial.print(F(" lim) "));
    Serial.print(hvcontrol.getCurrent());Serial.print(F(" mA ("));Serial.print(hvcontrol.getCurrentLimit());Serial.println(F(" lim)"));
  }
  Serial.println(F("Relays"));
  Serial.print(F("ThAr: "));Serial.println(hvcontrol.isLampEnabled(THAR_LAMP) ? "On":"Off");
  Serial.print(F("ThNe: "));Serial.println(hvcontrol.isLampEnabled(THNE_LAMP) ? "On":"Off");
  Serial.print(F("Hg:   "));Serial.println(hvcontrol.isLampEnabled(HG_LAMP) ? "On":"Off");
  Serial.print(F("Ne:   "));Serial.println(hvcontrol.isLampEnabled(NE_LAMP) ? "On":"Off");
  Serial.print(F("He:   "));Serial.println(hvcontrol.isLampEnabled(HE_LAMP) ? "On":"Off");
  return true;
}

//Print the commands
bool PCcommand() {
    Serial.println(F("#PC   Print Commands - Print this list of commands"));
    Serial.println(F("#LEx# Led command - Set LED x to # illumination"));
    Serial.println(F("#HVx# High Voltage - Set HV lamp x to # illumination, all others off"));
    Serial.println(F("#TS   Tell Status - Tell the status"));
    Serial.println(F("#TE   Temperature - Report all temperatures"));
    return true;
}
