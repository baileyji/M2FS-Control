#include <SPI.h>         // needed for Arduino versions later than 0018
#include <Ethernet.h>
#include <EthernetUdp.h> // UDP library from: bjoern@cs.stanford.edu 12/30/2008
#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

//Note these are NOT Arduino Pins
#define NXP_UV_PIN 5 //pin 11
#define NXP_BL_PIN 1 //pin 7
#define NXP_WH_PIN 2 //pin 8
#define NXP_74_PIN 4 //pin 10
#define NXP_77_PIN 0 //pin 6
#define NXP_IR_PIN 3 //pin 9

#define ARD_UV_PIN 3 //pin 
#define ARD_BL_PIN 8 //pin 
#define ARD_WH_PIN 6 //pin 
#define ARD_74_PIN 4 //pin 
#define ARD_77_PIN 9 //pin 
#define ARD_IR_PIN 5 //pin 

//Bloody Hell, the pinouts of the two connectors don't match
//Drive 1-7: 740, 770, Whi, UV, 875, 407, VCC
//LED 1-1:   875, 770, 740, Whi, UV, 407, VCC
//1->3
//2->2
//3->4
//4->5
//5->1
//6->6
//7->7

#define ETH_NRST_PIN 7
//#define LED_PIN 13

const int NPX_NOE_PIN=A3;
// These pints are also in use for SPI & TWI

// SCK MOSI MISO CS  13, 11, 12, 10
// SCL SDA 19/A5 18/A4

// called this way, it uses the default address 0x40
Adafruit_PWMServoDriver pwm = Adafruit_PWMServoDriver();

#if defined(ARDUINO_ARCH_SAMD)  
// for Arduino Zero, output on USB Serial console, 
// remove line below if using programming port to program the Zero!
   #define Serial SerialUSB
#endif

// Define a MAC address and IP address
byte mac[] = {0xDE, 0xAD, 0xBE, 0xEF, 0xFE, 0xED};
IPAddress ip(192, 168, 0, 177);

//Port to listen on
EthernetServer server(8888);
boolean alreadyConnected = false;

// buffers for receiving and sending data
unsigned int CMD_LEN = 5;  //[*|1-6]####
unsigned int cmd_ndx=0;
char cmdBuffer[6];  //buffer to hold incoming packet

//Levels
unsigned int levels[] = {0, 0, 0, 0, 0, 0};

/* General overview:
 * WIZ812 -(SPI)-> Arduino -(TWI)-> NXP PCA9685 ->
 * 2x MAX16824 LED Drivers
 * 
 * Commands: [*|1-6]####\n
 * 
 * Configure NXP for 1600Hz PWM
 * 
 * 
 */


void setup() {

  pinMode(NPX_NOE_PIN, OUTPUT);
  digitalWrite(NPX_NOE_PIN, HIGH);

  pwm.begin();
  // twbr must be changed after calling Wire.begin() inside pwm.begin()
  TWBR = 12; // up speed to 400KHz
  pwm.setPWMFreq(1600);  // Maximum PWM frequency
  pwm.setPin(NXP_UV_PIN, 0);
  pwm.setPin(NXP_BL_PIN, 0);
  pwm.setPin(NXP_WH_PIN, 0);
  pwm.setPin(NXP_74_PIN, 0);
  pwm.setPin(NXP_77_PIN, 0);
  pwm.setPin(NXP_IR_PIN, 0);  
  
  digitalWrite(NPX_NOE_PIN, LOW);

  pinMode(ETH_NRST_PIN, OUTPUT);
  digitalWrite(ETH_NRST_PIN, HIGH);

  pinMode(NXP_UV_PIN, OUTPUT);
  digitalWrite(NXP_UV_PIN, LOW);
  pinMode(NXP_BL_PIN, OUTPUT);
  digitalWrite(NXP_BL_PIN, LOW);
  pinMode(NXP_WH_PIN, OUTPUT);
  digitalWrite(NXP_WH_PIN, LOW);
  pinMode(NXP_74_PIN, OUTPUT);
  digitalWrite(NXP_74_PIN, LOW);
  pinMode(NXP_77_PIN, OUTPUT);
  digitalWrite(NXP_77_PIN, LOW);
  pinMode(NXP_IR_PIN, OUTPUT);
  digitalWrite(NXP_IR_PIN, LOW);

  Ethernet.begin(mac, ip);

  Serial.begin(115200);
  
  server.begin();

  Serial.println("MCalLED v0.2");
  
}


void do_command(EthernetClient client) {
  
  cmdBuffer[5]='\0';

  Serial.print("Parse: ");
  Serial.println(cmdBuffer);
  
  int level=atoi(&cmdBuffer[1]);
  if (level<0) level=0;
  if (level>4096) level=4096;

  switch(cmdBuffer[0]) {
    case '1' : //Serial.print(F("UV: "));
               //Serial.println(level);
               pwm.setPin(NXP_UV_PIN, level);
               levels[0]=level;
               break;
    case '2' : //Serial.print(F("BL: "));
               //Serial.println(level);
               pwm.setPin(NXP_BL_PIN, level);
               levels[1]=level;
               break;
    case '3' : //Serial.print(F("WH: "));
               //Serial.println(level);
               pwm.setPin(NXP_WH_PIN, level);
               levels[2]=level;
               break;
    case '4' : //Serial.print(F("74: "));
               //Serial.println(level);
               pwm.setPin(NXP_74_PIN, level);
               levels[3]=level;
               break;               
    case '5' : //Serial.print(F("77: "));
               //Serial.println(level);
               pwm.setPin(NXP_77_PIN, level);
               levels[4]=level;
               break;
    case '6' : //Serial.print(F("85: "));
               //Serial.println(level);
               pwm.setPin(NXP_IR_PIN, level);
               levels[5]=level;
               break;
    case '*' : //Serial.print(F("*: "));
               //Serial.println(level);
               pwm.setPin(NXP_UV_PIN, level);
               pwm.setPin(NXP_BL_PIN, level);
               pwm.setPin(NXP_WH_PIN, level);
               pwm.setPin(NXP_74_PIN, level);
               pwm.setPin(NXP_77_PIN, level);
               pwm.setPin(NXP_IR_PIN, level);
               levels[0]=level;
               levels[1]=level;
               levels[2]=level;
               levels[3]=level;
               levels[4]=level;
               levels[5]=level;
               break;
    case '?' : //Serial.println(F("?"));
               break;
  }
  
  telllevel(client);
    
}

void telllevel(EthernetClient client) {
  char buf[35]; // "ACK 0000 0000 0000 0000 0000 0000\n"
  buf[34]=0;
  sprintf(buf,"ACK %04d %04d %04d %04d %04d %04d\n", 
          levels[0],levels[1],levels[2],levels[3],levels[4],levels[5]);
  Serial.write(buf, 34);
  client.write(buf, 34);
}

void loop() {
  // if there's data available, read a packet
  EthernetClient client = server.available();

  // when the client sends the first byte, say hello:
  if (client) {
    if (!alreadyConnected) {  //should this flag be per client?
      // clear out the input buffer:
      client.flush();
      Serial.println(F("Client connected."));
      //client.println("?");
      telllevel(client);
      alreadyConnected = true;
    }

    while (client.available() > 0) {
      // read the bytes incoming from the client:
      char thisChar = client.read();
      if (thisChar == '\n') {
        do_command(client);
        cmd_ndx=0;
      } else {
        cmdBuffer[cmd_ndx] = thisChar;
        cmd_ndx+=1;
      }
      if (cmd_ndx>CMD_LEN) cmd_ndx=0;
      Serial.write(thisChar);
    }

    // if the server's disconnected, stop the client:
    if (!client.connected()) {
      Serial.println(F("Client disconnect."));
      client.stop();
    }
  }

  if (Serial.available() > 0) {
    Serial.readBytes(cmdBuffer, 5);
    do_command(client);
    cmd_ndx=0;
  }
  
}


