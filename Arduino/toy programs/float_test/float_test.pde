#include <avr/sleep.h>
#include <avr/power.h>
#include <SdFat.h>
#include <SdFatUtil.h>  // define FreeRam()
#include <Wire.h>
#include <OneWire.h>
#include <SPI.h>
#include <DallasTemperature.h>
#include <RTClib.h>
#include <ADXL345.h>
#include <Timer.h>
#include <avr/wdt.h>
#include <WatchdogSleeper.h>
//#include "datalogger_defs.h"
#include "handyAVRDefs.h"
//#include "sleepHelper.h"




//++++++++++++++++++++++++++++++++++++++++++++++++++++++++
//   Setup
//++++++++++++++++++++++++++++++++++++++++++++++++++++++++
void setup(void)
{
  Serial.begin(115200);

  Serial.println(FreeRam());
  float a=300.21;
  uint32_t  *binfloatptr;
  uint8_t   *floatbyteptr;
  uint32_t binfloat;
  uint8_t  floatbyte;
  
  binfloatptr=(uint32_t *)((void *)&a);
  floatbyteptr=(uint8_t *)((void *)&a);
  
  binfloat=*binfloatptr;

  Serial.print("Float: ");
  Serial.println(a);
  Serial.print(" ");
  Serial.println(binfloat,HEX);

  Serial.print(" ");
  floatbyte=*(floatbyteptr+0);
  Serial.print(floatbyte,HEX); 
  Serial.print(" ");
  floatbyte=*(floatbyteptr+1);
  Serial.print(floatbyte,HEX); 
  Serial.print(" ");
  floatbyte=*(floatbyteptr+2);
  Serial.print(floatbyte,HEX); 
  Serial.print(" ");
  floatbyte=*(floatbyteptr+3);
  Serial.println(floatbyte,HEX); 
    
}



//++++++++++++++++++++++++++++++++++++++++++++++++++++++++
//   loop
//++++++++++++++++++++++++++++++++++++++++++++++++++++++++
void loop(void){

}
