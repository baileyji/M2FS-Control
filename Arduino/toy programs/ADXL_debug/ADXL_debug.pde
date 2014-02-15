#include <avr/sleep.h>
#include <avr/power.h>
#include <SdFat.h>
#include <SdFatUtil.h>
#include <Wire.h>
#include <OneWire.h>
#include <SPI.h>
#include <DallasTemperature.h>
#include <RTClib.h>
#include <ADXL345.h>
#include <Timer.h>
#include <MsTimer2.h>
#include <WatchdogSleeper.h>
#include "buffer.h"
#define MAX_UINT32                 0xFFFFFFFF
#define error(s)                   SD.errorHalt_P(PSTR(s))
#define disableRegBit(reg, regBit) reg&=~(1<<regBit)
#define enableRegBit(reg, regBit)  reg|=(1<<regBit)

//#############################
//       General Defines 
//#############################
#define MIN_IDLETIME             2            //?????????
#define MIN_NAPTIME              1            //??????????
#define N_TEMP_SENSORS           5
#define LINE_BUFFER_SIZE         120
#define MAX_LOGFILE_SIZE_BYTES   0x38400000   //~900MB
#define START_POWERED true
#define ID "M2FS Datalogger test version"


//#############################
//             Pins
//#############################
#define SD_CS             10
#define ACCELEROMETER_CS  9
#define ONE_WIRE_BUS      2  // Data wire is plugged into pin 2 on the Arduino
#define BATTERY_PIN       5
#define ACCELEROMETER_INTERRUPT 1  //1=> pint 3, 0=> pin 2

#pragma mark -
#pragma mark Timers

//#############################
//             Timers
//#############################
#define LOG_TIMER         'L'
#define TEMP_UPDATE_TIMER 'T'
#define TEMP_POLL_TIMER   'P'
#define RTC_TIMER         'R'
#define POWER_TIMER       'O'
#define MESSAGE_TIMER     'M'
#define BATTERY_TIMER     'B'
#define MSTIMER2_DELTA                       2	      // should be less than smallest timeout interval
#define MESSAGE_CONFIRMATION_TIMEOUT_MS      100
#define BATTERY_TEST_INTERVAL_MS             3600000  //Once per hour
#define DS18B20_10BIT_MAX_CONVERSION_TIME_MS 188
#define LOG_SYNC_TIME_INTERVAL_MS            300000   //Once every five minutes???????????
#define TEMP_UPDATE_INTERVAL_MS              30000    //Once per minute
#define RTC_UPDATE_INTERVAL_MS               36000  //Once per hour
#define EXTERNAL_POWER_TEST_INTERVAL_MS      30000    //120000	//Once every two minutes

#define NUM_NAP_RELATED_TIMERS   4 //must be <= NUM_TIMERS
#define NUM_TIMERS               7

Timer batteryCheckTimer(BATTERY_TIMER, BATTERY_TEST_INTERVAL_MS);
Timer logSyncTimer(LOG_TIMER, LOG_SYNC_TIME_INTERVAL_MS);
Timer updateTempsTimer(TEMP_UPDATE_TIMER, TEMP_UPDATE_INTERVAL_MS);
Timer pollTempsTimer(TEMP_POLL_TIMER, DS18B20_10BIT_MAX_CONVERSION_TIME_MS);
Timer updateRTCTimer(RTC_TIMER, RTC_UPDATE_INTERVAL_MS);
//How often do we check to see if we've be brought online
Timer pollForPowerTimer(POWER_TIMER, EXTERNAL_POWER_TEST_INTERVAL_MS);
//How long do we wiat after sending a message before panicing and going into offline mode
Timer messageConfTimer(MESSAGE_TIMER, MESSAGE_CONFIRMATION_TIMEOUT_MS);

//Timers that should not be used in determining nap times must be placed at the end of the array 
Timer* const timers[NUM_TIMERS]={
  &logSyncTimer, &updateTempsTimer, &pollTempsTimer, &pollForPowerTimer, //Nap related
  &updateRTCTimer, &batteryCheckTimer, &messageConfTimer};               //Not nap related

//#############################
//             Globals
//#############################

WatchdogSleeper WDT;

RTC_DS1307 RTC;                 //Real Time Clock object

SdFat SD;                       //SD card filesystem object

OneWire oneWire(ONE_WIRE_BUS);  // Instantiate a oneWire instance

DallasTemperature dallasSensors(&oneWire);  // Instantiate Dallas Temp sensors on oneWire 

ArduinoOutStream cout(Serial);  // Serial print stream

SdFile logfile;             // file for logging
uint32_t writePos, readPos;


int16_t accel[3];
float temps[N_TEMP_SENSORS];
boolean powered=false;
boolean updateRTCPending=false;
volatile boolean asleep=false;
uint32_t msgID=0;

volatile boolean currently_inactive=false;
volatile uint8_t accelerometerInterrupt = 0;
volatile boolean accelerometerCausedWakeup = false;
volatile boolean store_fifo_accels=true;
volatile uint8_t n_in_fifo=0;

// Date/time format operator
ostream& operator << (ostream& os, DateTime& dt) {
  os << dt.year() << '/' << int(dt.month()) << '/' << int(dt.day()) << ' ';
  os << int(dt.hour()) << ':' << setfill('0') << setw(2) << int(dt.minute());
  os << ':' << setw(2) << int(dt.second()) << setfill(' ');
  return os;
}

#pragma mark -
#pragma mark ISRs & Callbacks
  
//=============================
// ISR for watchdog timer
//=============================
extern "C" volatile unsigned long timer0_millis;
extern "C" volatile unsigned long timer0_overflow_count;
ISR(WDT_vect) {

  WDT._WDT_ISR_Called=true;
  
  // Restart WDT if required
  if (WDT._autorestart)
    WDT.on(WDT.readPrescaler());
  
  // Self-calibrate if required
  if (WDT._cycles2ms > 1)
    if (timer0_millis > WDT._cycles2ms)
      WDT._cycles2ms=(timer0_millis - WDT._cycles2ms)/
        WDT.__Prescaler2Cycles(WDT_CALIBRATION_PRESCALE_V);
  
  // Do the callback, if required
  if (WDT._WDT_Callback_Enabled) 
    WDT.__WDT_Callback_Func(WDT._WDT_timer0_millis_increment);

  // Keep millis() on track, if required  
  if (WDT._update_timer0_millis) {
    timer0_overflow_count+=WDT._WDT_timer0_overflow_count_increment;
    timer0_millis+=WDT._WDT_timer0_millis_increment;
    WDT._update_timer0_millis=false;
  }
}


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

  WDT.cancelSleep();
}


void recoveryISR() {
  cout<<"#AINT going High\n";
  detachInterrupt(ACCELEROMETER_INTERRUPT);
}

  
//=============================
// WDT ISR callback function
//=============================
void timerUpdater(uint32_t delta) {
  for (int i=0; i<NUM_TIMERS; i++)
    timers[i]->increment(delta);
    WDT.cancelSleep();
}


//=============================
// MsTimer2 ISR callback function
//=============================
void timerUpdater(void) {
  for (int i=0; i<NUM_TIMERS; i++)
    timers[i]->increment(MSTIMER2_DELTA);
}


//=============================
// Callback for file timestamps
//=============================
void dateTime(uint16_t* date, uint16_t* time) {
  DateTime now = DateTime(1999,1,1,0,0,0);//RTC.now();
  *date = FAT_DATE(now.year(), now.month(), now.day()); // return date using FAT_DATE macro to format fields
  *time = FAT_TIME(now.hour(), now.minute(), now.second()); // return time using FAT_TIME macro to format fields
}


#pragma mark -
#pragma mark Functions

//++++++++++++++++++++++++++++++++++++++++++++++++++++++++
//   Setup
//++++++++++++++++++++++++++++++++++++++++++++++++++++++++
void setup(void)
{
  pinMode(ACCELEROMETER_CS,OUTPUT);
  digitalWrite(ACCELEROMETER_CS,HIGH);
  pinMode(SD_CS,OUTPUT);
  digitalWrite(SD_CS,HIGH);
  //Initialize the buffer head, who knows what was in memory
  bufferRewind();
  
  Serial.begin(115200);
  
  // Initialize the watchdog timer
  WDT.off();
  WDT.calibrate();
  WDT.registerCallback(timerUpdater);
  WDT.enableAutorestart();
  WDT.on(0);


  // Initialize timers
  batteryCheckTimer.start();
  updateTempsTimer.start();
  updateRTCTimer.start();



  // Initialize the temp sensors
  cout<<pstr("#Init Temp...");
  dallasSensors.begin();
  dallasSensors.setResolution(10);  //configure for 10bit, conversions take 187.5 ms max
  dallasSensors.setWaitForConversion(false);
  cout<<pstr("initialized.\n"); //*/

  // Initialize RTC
  cout<<pstr("#Init RTC...");
  Wire.begin();
  if (! RTC.isrunning()) {
    cout<<pstr("RTC NOT running\n");
    // following line sets the RTC to the date & time this sketch was compiled
    RTC.adjust(DateTime(__DATE__, __TIME__));
  }
  if (!RTC.begin()) {
    cout<<pstr("#RTC f'd\n");
  } else {
    cout<<pstr("RTC init'd.\n");
    // set date time callback function
    SdFile::dateTimeCallback(dateTime);
  }//*/
  
    
    
  // Initialize Accelerometer
  cout<<pstr("#Init ADXL...");
  pinMode(ACCELEROMETER_CS, INPUT);
  ADXL345.init(ACCELEROMETER_CS);
  attachInterrupt(ACCELEROMETER_INTERRUPT, accelerometerISR, FALLING);
  cout<<pstr("initialized.\n");
    


  // Initialize SD card
  cout<<pstr("#Init SD...");
  // initialize the SD card at SPI_HALF_SPEED to avoid bus errors with
  // breadboards.  use SPI_FULL_SPEED for better performance.
  // if SD chip select is not SS, the second argument to init is CS pin number
  if (!SD.init(SPI_QUARTER_SPEED, SD_CS)) SD.initErrorHalt();
  // create a new file in root, the current working directory
  char name[] = "LOG.CSV";
  logfile.open(name, O_RDWR | O_TRUNC | O_CREAT);
  if (!logfile.isOpen()) {
    cout<<pstr("#Error opening file.\n");
    //error("file.open");
  }
  logfile.write(sizeof(ID));
  logfile.write(ID,sizeof(ID));
  logfile.sync();
  writePos=logfile.curPosition();
  readPos=0;
	
  cout<<pstr("initialized. Logging to: ")<<name<<endl;  



  // Initialize power mode
  powered=START_POWERED;
  if (!powered) {
    pollForPowerTimer.start();
    setTimerUpdateSourceToWDT();
  } 
  else {
    setTimerUpdateSourceToMsTimer2();
  }
  
  // Report Free ram
  cout<<FreeRam()<<endl;
}



//++++++++++++++++++++++++++++++++++++++++++++++++++++++++
//   loop
//++++++++++++++++++++++++++++++++++++++++++++++++++++++++
void loop(void){
  
  boolean dataFromLogfile=false;
  uint32_t availableNaptimeMS;
  SleepMode sleepMode;
  
  
  
  boolean spewData=false;
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



  // Reset millis() at 00:00:00
  if (needToResetMillis()) {
    resetMillis();
  }
    
  // Periodically check the battery status 
  if (batteryCheckTimer.expired()) {
    cout<<'B'<<testBattery()<<endl;
    batteryCheckTimer.reset();
    batteryCheckTimer.start();
  }

  // Periodically check for a connection while unpowered
  if (!powered && pollForPowerTimer.expired()) {
    cout<<"?";
    messageConfTimer.reset();
    messageConfTimer.start();
    pollForPowerTimer.reset();
    pollForPowerTimer.start();
  }

  // Temperature Conversion
  if (updateTempsTimer.expired()) {
    dallasSensors.requestTemperatures(); //Issue a global temperature conversion request
    cout<<"#Requesting T\n";
    pollTempsTimer.reset();
    pollTempsTimer.start();
    updateTempsTimer.reset();
    updateTempsTimer.start();
  }
  
  
  
  
  
  
  //////
  //Region of code in which buffer may be modified  
  //////
  
  // Handle case where we are no longer powered
  //  but there is a message in the buffer
  if (!powered) {
    if (!bufferIsEmpty()) {
      if (dataFromLogfile) {
        //logfile.seekCur(-bufferPos());	//rewind readPos
        //readPos=logfile.curPosition();
        bufferRewind();
      }
      else {
        //logfile.seekSet(writePos);
        //logfile.write(bufferGetBufPtr(), bufferPos());
        //writePos=logfile.curPosition();
        bufferRewind();
      }
    }
  } 
  
    
  
  // Temperature Monitoring
  if (pollTempsTimer.expired()) {
    cout<<"#Poll T\n";
    for (unsigned char i=0; i<N_TEMP_SENSORS; i++)
        temps[i]=dallasSensors.getTempCByIndex(i);//20.34;//dallasSensors.getTempCByIndex(i);
    bufferPut(temps, N_TEMP_SENSORS*sizeof(float));
    pollTempsTimer.reset();
  }


  // Acceleration Monitoring
  if (accelerometerInterrupt & ADXL_INT_WATERMARK) {

    //detachInterrupt(ACCELEROMETER_INTERRUPT);
    //attachInterrupt(ACCELEROMETER_INTERRUPT, recoveryISR, RISING);  
    
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

    //attachInterrupt(ACCELEROMETER_INTERRUPT, accelerometerISR, FALLING);
    

  }
/*  else if (!digitalRead(3)) {
    cout<<pstr("#Accel Int. LOW, BAD")<<endl;
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
*/
 
}


//=======================================
// testBattery() - Read the battery voltage
//  and return a rough estimate of the number
//  months life left in the battery.
//=======================================
int testBattery(void) {
  int batterypin_v;
  int months_remain;
  
  // Power up the ADC
  power_adc_enable();
  enableRegBit(ADCSRA, ADEN); //Enable the ADC
  //delayMicroseconds(?);     //Does the Arduino take care of the delay required before conversion??? 
  
  // Configure the ADC
  
  // Read the input on the battery pin
  batterypin_v=analogRead(BATTERY_PIN);
  
  // Power down the ADC
  disableRegBit(ADCSRA, ADEN); //Disable ADC before power off
  power_adc_disable();
  
  // Compute the rate of discharge
  
  // Compute how long we've got left
  months_remain=0;
  
  // Return
  return months_remain;
}//*/


boolean needToResetMillis() {
  return false; 
}

//=============================
// setTimerUpdateSourceToWDT
//  does as named, WDT has  
//  16ms minimum time slice
//=============================
void setTimerUpdateSourceToWDT(void) {
  /*MsTimer2::stop();
  power_timer2_disable(); //*/
  WDT.enableCallback();
}

//=============================
// setTimerUpdateSourceToMsTimer2
//  does as named, timeslice is 
//  defined by MSTIMER2_DELTA
//  minimum 1ms
//=============================
void setTimerUpdateSourceToMsTimer2(void) {
  
  WDT.enableCallback();
  
  /*power_timer2_enable();
  MsTimer2::set(MSTIMER2_DELTA, timerUpdater);
  WDT.disableCallback();
  MsTimer2::start(); //*/
}


//=============================
// resetMillis - Resets the millis counter
//=============================
void resetMillis() {
  uint8_t oldSREG = SREG;
  cli();
  timer0_millis = 0;
  SREG = oldSREG;
}

