#include <SdFat.h>
#include "sh_pins.h"

#define POWERDOWN_DELAY_US  1000
#define VERSION_STRING "Sharck-Hartman v0.1"
#define LED_ENABLE_PIN 12
#define SHLED_PIN 11

//#define DEBUG

ArduinoOutStream cout(Serial);

char command_buffer[81];
unsigned char command_buffer_ndx=0;
unsigned char command_length=0;
bool have_command_to_parse=false;

uint8_t ledIntensity=0;

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
    parseAndExecuteCommand();
    have_command_to_parse=false;
    command_buffer_ndx=0;
  }

}

bool parseAndExecuteCommand() {
  
  if (command_buffer[0]>='0' && command_buffer[0]<='9'){
    ledIntensity = atoi(command_buffer);
    if (ledIntensity==0)
      digitalWrite(LED_ENABLE_PIN,LOW);
    else {
      analogWrite(SHLED_PIN, ledIntensity);
      digitalWrite(LED_ENABLE_PIN,HIGH);
    }
    return true;
  }
  else if (command_buffer[0]=='?') {
    cout<<ledIntensity;
    return true;
  }
  return false;
}