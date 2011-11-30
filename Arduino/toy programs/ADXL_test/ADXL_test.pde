#include <avr/sleep.h>
#include <avr/power.h>
#include <SdFatUtil.h>  // define FreeRam()
#include <SPI.h>
#include <SdFat.h>
#include <ADXL345.h>
#include <Timer.h>
#include <avr/wdt.h>
//#include "datalogger_defs.h"
#include "handyAVRDefs.h"
//#include "sleepHelper.h"


#define MIN_IDLETIME 2  //?????????
#define MIN_NAPTIME 1  //??????????
#define MAX_UINT32 0xFFFFFFFF

//#############################
//             Pins
//#############################
#define SD_CS 10
#define ACCELEROMETER_CS 9
#define ACCELEROMETER_INTERRUPT 1  //1=> pint 3, 0=> pin 2
boolean spewData = false;
ArduinoOutStream cout(Serial);  // Serial print stream



volatile boolean asleep=false;
int accel[3];
boolean logAccel = false;	//Set when there is data to log
volatile boolean accelerometerCausedWakeup = false;
volatile boolean currently_inactive=false;
volatile char accelerometerInterrupt = 0;
volatile char n_in_fifo=0;
volatile uint32_t timerUpdaterCalled=0;
extern "C" volatile uint32_t timer0_millis;
uint32_t time1, time2;
volatile boolean store_fifo_accels=true;
  



//=============================
// Accelerometer ISR
//=============================
void accelerometerISR(void) {
  ADXL345.readRegister(ADXL_INT_SOURCE, 1, (char*) &accelerometerInterrupt);
  ADXL345.readRegister(ADXL_FIFO_STATUS,1, (char*) &n_in_fifo);
  accelerometerCausedWakeup = asleep;
  store_fifo_accels=store_fifo_accels ||
      (accelerometerInterrupt & (ADXL_INT_ACTIVITY | ADXL_INT_FREEFALL));
      
  //Update the activity status only when information about the activity status is present
  if (accelerometerInterrupt & (ADXL_INT_ACTIVITY | ADXL_INT_FREEFALL | ADXL_INT_INACTIVITY))
    currently_inactive = (accelerometerInterrupt & ADXL_INT_INACTIVITY) && 
                       !(accelerometerInterrupt & ADXL_INT_FREEFALL);
}


void recoveryISR() {
  cout<<"#AINT going High\n";
  detachInterrupt(ACCELEROMETER_INTERRUPT);
}

//++++++++++++++++++++++++++++++++++++++++++++++++++++++++
//   Setup
//++++++++++++++++++++++++++++++++++++++++++++++++++++++++
void setup(void)
{
  Serial.begin(115200);

  cout<<FreeRam()<<endl;
  cout<<pstr("Initializing Accelerometer...");
  pinMode(3, INPUT);
  ADXL345.init(ACCELEROMETER_CS);
  attachInterrupt(ACCELEROMETER_INTERRUPT, accelerometerISR, FALLING);
  cout<<pstr("accelerometer initialized.\n");
  
}



//++++++++++++++++++++++++++++++++++++++++++++++++++++++++
//   loop
//++++++++++++++++++++++++++++++++++++++++++++++++++++++++
void loop(void){

  //if (Serial.peek()=='r') 
  time1=millis();
  time2=millis();
 
 
  if ( Serial.available() > 0 ) {
    char byteIn=Serial.read();
    if (byteIn == 't') {
      ADXL345.selfTest(accel);
      ADXL345.getRawAccelerations(accel);
      cout<<"Self Test: "<<accel[0]<<" "<<accel[1]<<" "<<accel[2]<<endl;
    } else if (byteIn == 'v') {
      cout<<"Spewing Enabled"<<endl;
      spewData=true;
    } else if (byteIn=='s') {
      spewData=false;
      cout<<"Spewing Disabled"<<endl;
    }
    Serial.flush();
    
  }

  // Acceleration Monitoring
  // Acceleration Monitoring
  if (accelerometerInterrupt & ADXL_INT_WATERMARK) {

    detachInterrupt(ACCELEROMETER_INTERRUPT);
    attachInterrupt(ACCELEROMETER_INTERRUPT, recoveryISR, RISING);  
    
    ///*
    cout<<pstr("# Accel. int=");Serial.print(accelerometerInterrupt,HEX);
    if (accelerometerInterrupt & ADXL_INT_DATAREADY)	  cout<<pstr(", data ready");
    if (accelerometerInterrupt & ADXL_INT_FREEFALL)	  cout<<pstr(", freefall");
    if (accelerometerInterrupt & ADXL_INT_INACTIVITY) cout<<pstr(", inactivity");
    if (accelerometerInterrupt & ADXL_INT_OVERRUN)	  cout<<pstr(", data dropped");
    if (accelerometerInterrupt & ADXL_INT_WATERMARK)  cout<<pstr(", watermark");
    cout<<". N in FIFO: "<<(unsigned int)n_in_fifo<<endl;
    //*/
    
    if (store_fifo_accels) {
      for (uint8_t i=0; i<n_in_fifo;i++) {
        ADXL345.getRawAccelerations(accel);
        cout<<"#  "<<accel[0]<<" "<<accel[1]<<" "<<accel[2]<<endl;
      }
    }
    else {
      for (uint8_t i=0; i<n_in_fifo;i++) {
        ADXL345.getRawAccelerations(accel);
      }
      //cout<<"Purged "<<(unsigned int)n_in_fifo<<" Millis: "<<millis()<<endl;
    }

    if (digitalRead(3)) cout<<pstr("#Accel Int. Pin HIGH")<<endl;
    else cout<<pstr("#Accel Int. Pin LOW")<<endl;
    
    store_fifo_accels=!currently_inactive;
    
    
    accelerometerISR();
    
    cout<<pstr("# Accel. int=");Serial.print(accelerometerInterrupt,HEX);
    if (accelerometerInterrupt & ADXL_INT_DATAREADY)	  cout<<pstr(", data ready");
    if (accelerometerInterrupt & ADXL_INT_ACTIVITY)	  cout<<pstr(", activity");
    if (accelerometerInterrupt & ADXL_INT_FREEFALL)	  cout<<pstr(", freefall");
    if (accelerometerInterrupt & ADXL_INT_INACTIVITY) cout<<pstr(", inactivity");
    if (accelerometerInterrupt & ADXL_INT_OVERRUN)	  cout<<pstr(", data dropped");
    if (accelerometerInterrupt & ADXL_INT_WATERMARK)  cout<<pstr(", watermark");
    cout<<". N in FIFO: "<<(unsigned int)n_in_fifo<<endl;


    

  }
  else if (!digitalRead(3)) {
    cout<<pstr("#Accel Int. LOW")<<endl;
    accelerometerISR();
    cout<<pstr("# Accel. int=");Serial.print(accelerometerInterrupt,HEX);
    if (accelerometerInterrupt & ADXL_INT_DATAREADY)	  cout<<pstr(", data ready");
    if (accelerometerInterrupt & ADXL_INT_ACTIVITY)	  cout<<pstr(", activity");
    if (accelerometerInterrupt & ADXL_INT_FREEFALL)	  cout<<pstr(", freefall");
    if (accelerometerInterrupt & ADXL_INT_INACTIVITY) cout<<pstr(", inactivity");
    if (accelerometerInterrupt & ADXL_INT_OVERRUN)	  cout<<pstr(", data dropped");
    if (accelerometerInterrupt & ADXL_INT_WATERMARK)  cout<<pstr(", watermark");
    cout<<". N in FIFO: "<<(unsigned int)n_in_fifo<<endl;
  }
    

  if(digitalRead(3)){
    detachInterrupt(ACCELEROMETER_INTERRUPT);
    attachInterrupt(ACCELEROMETER_INTERRUPT, accelerometerISR, FALLING);
  }

 
}

