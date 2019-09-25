#include <SPI.h>         // needed for Arduino versions later than 0018
#include "HVLamp.h"

#define VERSION_STRING "1.0"

//
//#define SDA_PIN 4 //pin 10
//#define SCL_PIN 0 //pin 6
HVLamp hvcontrol = HVLamp();



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
bool PVcommand();
bool OFcommand();


#define N_COMMANDS 7
const Command commands[]={
    {"LE", LEcommand}, //LEd lamp command
    {"HV", HVcommand}, //HV lamp command
    {"PC", PCcommand}, //Print Commands
    {"TE", TEcommand}, //TEmps Command
    {"TS", TScommand}, //Tell Status(whats on and off)
    {"PV", PVcommand}, //Print Version string
    {"OF", OFcommand}  //OFf (turn all light sources off)
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

    // Start serial connection
    Serial.begin(115200);
}


//Main loop, runs forever, full steam ahead
void loop() {
  
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
  return true;
}


bool HVcommand() {
  /*
  HV # ############### \n
  HV##\n <- min command 
  HV?\n
  */
  if (command_buffer[2]=='?') {
    current_t lamplevel;
    lampstatus_t active = hvcontrol.getActiveLamp();
    Serial.print(active.current);
    Serial.print("mA , ");
    Serial.print(active.voltage);
    Serial.println("V");

    return true;
  }

  lamp_t lamp;
  if (command_buffer[2]>= '1' && command_buffer[2] <='3') {
    lamp = (lamp_t) command_buffer[2]-'1';
  } else {
    return false;
  }

  if (lamp==NONE_LAMP) {
    hvcontrol.turnOff();
    return true;
  }

  if (command_length > 4){
    if (!((command_buffer[3] >='0' && command_buffer[3]<='9') || 
          ((command_buffer[3] =='+' && command_length> 5) &&
          command_buffer[4] >='0' && command_buffer[4]<='9' ))) 
       return false;  
    unsigned int param = atoi(command_buffer+3);
    Serial.print("Commanded to in current level ");Serial.println((current_t) param);
    hvcontrol.turnOn(0, (current_t) param);
    return true;
  } else {
    return false;
  }

}

//Report the last temp reading
bool TEcommand() {
    return true;
}

bool TScommand() {


  Serial.print(F("HV Lamps:\nHV Supply\n"));

  if (hvcontrol.isEnabled()) {
    Serial.println(F("Disabled"));
  } else {
    Serial.print(F("Enabled, running in "));
  }
    Serial.print(hvcontrol.isVoltageMode() ? "voltage":"current");Serial.println(F(" mode"));
    Serial.print(hvcontrol.getVoltage());Serial.print(F(" V ("));Serial.print(hvcontrol.getVoltageLimit());Serial.print(F(" lim) "));
    Serial.print(hvcontrol.getCurrent());Serial.print(F(" mA ("));Serial.print(hvcontrol.getCurrentLimit());Serial.println(F(" lim)"));

  return true;
}

//Print the commands
bool PCcommand() {
    Serial.println(F("#PC   Print Commands - Print this list of commands"));
    Serial.println(F("#LEx# Led command - Set LED x to # illumination"));
    Serial.println(F("#HVx# High Voltage - Set HV lamp x to # illumination, all others off"));
    Serial.println(F("#OF   Off - Turn all light sources off"));
    Serial.println(F("#TS   Tell Status - Tell the status"));
    Serial.println(F("#PV   Print Version - Print the version string"));
    Serial.println(F("#TE   Temperature - Report all temperatures"));
    return true;
}

//Turn everything off
bool OFcommand() {
  hvcontrol.turnOff();
  return true;
}

//Print the version
bool PVcommand() {
    Serial.println(F(VERSION_STRING));
    return true;
}
