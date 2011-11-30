/*
TODO:
Fix overslept time calc when sleep canceled
figure out why timer oly being decremented by 15 ms when sleep lasts for more than a second
fix RTC
figure out why only 31 records being recieved from accelerometer
*/
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
#define START_POWERED			 false
#define ID "M2FS Datalogger test version"
#define ID_SIZE 28

//#############################
//             Pins
//#############################
#define SD_CS             10
#define ACCELEROMETER_CS  9
#define ONE_WIRE_BUS      2  // Data wire is plugged into pin 2 on the Arduino
#define BATTERY_PIN       5
#define ACCELEROMETER_INTERRUPT 1  //1=> pint 3, 0=> pin 2
#define EJECT_PIN         4

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

#pragma mark -
#pragma mark Globals

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
uint32_t Logfile_End;
uint32_t Logfile_Data_Start;

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
  if (accelerometerCausedWakeup)
    WDT.cancelSleep();
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


//========================================================
//--------------------------------------------------------
//   Setup
//--------------------------------------------------------
//========================================================
void setup(void)
{
  
  pinMode(ACCELEROMETER_CS,OUTPUT);
  digitalWrite(ACCELEROMETER_CS,HIGH);
  pinMode(SD_CS,OUTPUT);
  digitalWrite(SD_CS,HIGH);
  pinMode(EJECT_PIN,INPUT);
  digitalWrite(EJECT_PIN,HIGH);
  
  // Disable unused periphreials
  
  // Disable analog comparator
  disableRegBit(ACSR, ACIE);  //turn off comparator interrupt
  disableRegBit(ACSR, ACD);   //turn off comparator
  
  // Disable the ADC
  disableRegBit(ADCSRA, ADEN); //Disable ADC before power off
  power_adc_disable();

  // Disable Timer1 (Is this needed by any of the arduino libraries????)
  power_timer1_disable();
  
  // Disable Timer2 
  power_timer2_disable(); //Needed by MsTimer2

  // Configure unused pins to consume minimum power
  //pinMode(?,INPUT);digitalWrite(?,LOW); //Will need testing to verify
  
  //Initialize the buffer head, who knows what was in memory
  bufferRewind();
  
  //Start the serial connection
  Serial.begin(115200);

  // Initialize the watchdog timer
  WDT.off();
  WDT.calibrate();
  WDT.registerCallback(timerUpdater);
  WDT.enableAutorestart();
  WDT.on(0);
  
  // Initialize SD card
  char name[] = "LOG.CSV";
  cout<<pstr("#Init SD...");
  // initialize the SD card at SPI_HALF_SPEED to avoid bus errors with
  // breadboards.  use SPI_FULL_SPEED for better performance.
  // if SD chip select is not SS, the second argument to init is CS pin number
  if (!SD.init(SPI_FULL_SPEED, SD_CS)) SD.initErrorHalt();
  
  
  Logfile_Data_Start=ID_SIZE + 13;
  
  // create a new file in root, the current working directory
  logfile.open(name, O_RDWR | O_TRUNC | O_CREAT);
  if (!logfile.isOpen()) 
    error("file.open"); 
  
  readPos=writePos=Logfile_End=Logfile_Data_Start;
	
  cout<<endl<<"Current Position: "<<logfile.curPosition()<<endl;
  cout<<"Write Logfile_Data_Start: "<<Logfile_Data_Start<<endl;
  logfile.write((uint8_t) Logfile_Data_Start); //Header Size
  cout<<"New Position: "<<logfile.curPosition()<<endl;
  
  cout<<"Write ID "<<endl;
  logfile.write(ID,ID_SIZE);		 //File Info
  cout<<"New Position: "<<logfile.curPosition()<<endl;
  
  cout<<"Write writePos: "<<writePos<<endl;
  logfile.write((void*)&writePos,sizeof(writePos));
  cout<<"New Position: "<<logfile.curPosition()<<endl;
  
  cout<<"Write readPos: "<<readPos<<endl;
  logfile.write((void*)&readPos,sizeof(readPos));
  cout<<"New Position: "<<logfile.curPosition()<<endl;

  cout<<"Write Logfile_End: "<<Logfile_End<<endl;
  logfile.write((void*)&Logfile_End,sizeof(Logfile_End));
  cout<<"New Position: "<<logfile.curPosition()<<endl;
  
  logfile.sync();

  cout<<pstr("initialized. Logging to: ")<<name<<endl;

  logfile.close();

  if (SD.exists(name)) {
	//Try to read header info and resume operation
    logfile.open(name, O_RDWR);
    if (!logfile.isOpen()) 
      error("file.open");
      
    cout<<"File reopened\n";

    int16_t header_size=logfile.read();
    cout<<"first byte: "<<header_size<<endl;
    
    cout<<"Seek to: "<<ID_SIZE+1<<endl;
    logfile.seekSet(ID_SIZE+1);
    cout<<"Current Position: "<<logfile.curPosition()<<endl;
        
    logfile.read((void*)&writePos,sizeof(writePos));
    cout<<"Current Position: "<<logfile.curPosition()<<endl;
    cout<<"writePos: "<<writePos<<endl;

    logfile.read((void*)&readPos,sizeof(readPos));
    cout<<"Current Position: "<<logfile.curPosition()<<endl;
    cout<<"readPos: "<<readPos<<endl;
    
    logfile.read((void*)&Logfile_End,sizeof(Logfile_End));
    cout<<"Current Position: "<<logfile.curPosition()<<endl;
    cout<<"Logfile_End: "<<Logfile_End<<endl;

  }

  // Report Free ram
  cout<<pstr("#Free RAM: ")<<FreeRam()<<endl;

}

         
//========================================================
//--------------------------------------------------------
//   loop
//--------------------------------------------------------
//========================================================

void loop(void){}
