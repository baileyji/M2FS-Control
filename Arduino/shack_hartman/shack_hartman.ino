#include <SdFat.h>
#include "sh_pins.h"

#define POWERDOWN_DELAY_US  1000
#define VERSION_STRING "Sharck-Hartman v0.1"
#define N_COMMANDS 7

//#define DEBUG

ArduinoOutStream cout(Serial);

char command_buffer[81];
unsigned char command_buffer_ndx=0;
unsigned char command_length=0;
bool have_command_to_parse=false;

uint8_t ledIntensity=0;

String commands[N_COMMANDS]={
  "LG",//LED Get
  "LS",//LED Set
  "II",//Inserter In
  "IO",//Inserter Out
  "IG",//Inserter Get
  "PC",//Print Commands
  "PV"//Print version String
  };
bool (*cmdFuncArray[N_COMMANDS])() = {
  LGcommand,
  LScommand,
  IIcommand,
  IOcommand,
  IGcommand,
  PCcommand,
  PVcommand
  };
  
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

void setup() {
  
  //Set up LED power relay pin
  pinMode(LED_ENABLE_PIN,OUTPUT);
  digitalWrite(LED_ENABLE_PIN,LOW);
  
  pinMode(SHLED_PIN,OUTPUT);
  digitalWrite(SHLED_PIN,LOW);
  
  // Motion controller startup
  //TODO
  
  // Start serial connection
  Serial.begin(115200);
}

void loop() {

  // Handle command parsing
  if (have_command_to_parse) {
    #ifdef DEBUG
      printCommandBufNfo();
    #endif
    bool commandGood=parseAndExecuteCommand();
    if (commandGood) Serial.write(":\n");
    else Serial.write("?\n");
    have_command_to_parse=false;
    command_buffer_ndx=0;
  }

}

bool parseAndExecuteCommand() {
  if(command_length < 2) return false;
  char ndx=getCallbackNdxForCommand();
  if (ndx == -1 ) return false;
  return cmdFuncArray[ndx]();
} 

// Search through commands for a string that matches c and 
//return the index, -1 if not found
char getCallbackNdxForCommand() {
  String command;
  command+=command_buffer[0];
  command+=command_buffer[1];
  for (char i=0;i<N_COMMANDS;i++) if (commands[i]==command) return i;
  return -1;
}

#ifdef DEBUG
void printCommandBufNfo(){
  cout<<"Command Buffer Info";Serial.write('\n');
  cout<<"Buf ndx: "<<(unsigned int)command_buffer_ndx<<" Cmd len: "<<(unsigned int)command_length;Serial.write('\n');
  cout<<"Contents:";Serial.write((const uint8_t*)command_buffer,command_buffer_ndx);
  Serial.write('\n');
}
#endif



//Report intensity of the LED
bool LGcommand() {
  cout<<(uint16_t)ledIntensity;
  return true;
}

//Set the LED intensity
bool LScommand() {

  ledIntensity=atol(command_buffer+2);
  
  if (ledIntensity==0)
    digitalWrite(LED_ENABLE_PIN,LOW);
  else {
    analogWrite(SHLED_PIN, ledIntensity);
    digitalWrite(LED_ENABLE_PIN,HIGH);
  }
  
  return true;
}

//Insert the lenslet array
bool IIcommand() {
  //Check for errors with the polulu
  if (errors) cout<<"ERROR: Pololu Error";
  //command the polou controller to put it in position
  //TODO
  //Check for errors with the polulu
  if (errors) cout<<"ERROR: Pololu Error";
  
  return true;
}


//Remove the lenslet array
bool IOcommand() {
  //Check for errors with the polulu
  if (errors) cout<<"ERROR: Pololu Error";
  //command the polou controller to put it in position
  //TODO
  //Check for errors with the polulu
  if (errors) cout<<"ERROR: Pololu Error";
  
  return true;
}

bool IGcommand() {
  //Check for errors with the polulu
  if (errors) cout<<"ERROR: Pololu Error";
  //determine the current position //TODO
  if (currently moving) cout<<"MOVING";
  else if( inserted ) cout<<"IN";
  else if ( removed ) cout<<"OUT";
  else cout<<"UNKNOWN";
  return true;
}


//Report the version string
bool PVcommand() {
  cout<<VERSION_STRING;
  return true;
}


//Print the commands
bool PCcommand() {
  cout<<"#PC   Print Commands - Print the list of commands";Serial.write('\n');
  
  return true;
}
