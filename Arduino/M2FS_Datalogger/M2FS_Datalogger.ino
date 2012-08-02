/*
TODO:
figure out why timer oly being decremented by 15 ms when sleep lasts for more than a second

FUSES:
  Default for 3.3V Arduino 328p
  High: 0xDA  Low: 0xFF Ext: 0xFD
  For this sketch:
  High: 0xDA  Low: 0xDF Ext: 0xFB -> startup time from power-down/power-save 16k clocks (2ms), BOD @ 2.7V
  
*/
#include <avr/sleep.h>
#include <avr/power.h>
#include <SdFat.h>
#include <SdFatUtil.h>
#include <Wire.h>
#include <OneWire.h>
#include <SPI.h>
#include <DallasTemperature.h>
#include <RTC_DS1337.h>
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
#define N_TEMP_SENSORS           5
#define MAX_LOGFILE_SIZE_BYTES   0x38400000   //~900MB
#define START_POWERED		 true
#define ID "v0.1"
#define ID_SIZE 4

//#define DEBUG_STARTUP //Passes
#define DEBUG_PROTOCOL
//#define DEBUG_STAY_POWERED
//#define DEBUG_ACCEL
//#define DEBUG_FAKE_SLEEP
//#define DEBUG_SLEEP
//#define DEBUG_LOGFILE

//#############################
//             Pins
//#############################
#define SD_CS             10
#define ACCELEROMETER_CS  9
#define ONE_WIRE_BUS      2  // Data wire is plugged into pin 2 on the Arduino
#define BATTERY_PIN       5
#define ACCELEROMETER_INTERRUPT 1  //1=> pin 3, 0=> pin 2
#define ACCELEROMETER_INTERRUPT_PIN 3
#define EJECT_PIN         4

#pragma mark -
#pragma mark Timers

//#############################
//             Timers
//#############################
#define ADXL_POLL_TIMER   'A'
#define LOG_TIMER         'L'
#define TEMP_UPDATE_TIMER 'T'
#define TEMP_POLL_TIMER   'P'
#define RTC_TIMER         'R'
#define POWER_TIMER       'O'
#define MESSAGE_TIMER     'M'
#define BATTERY_TIMER     'B'
#define MSTIMER2_DELTA                       2	      // should be less than smallest timeout interval
#define MESSAGE_CONFIRMATION_TIMEOUT_MS      250      //MUST be less than the ADXL FIFO period
#define BATTERY_TEST_INTERVAL_MS             3600000  //Once per hour
#define DS18B20_10BIT_MAX_CONVERSION_TIME_MS 188
#define ADXL_FIFO_RATE                       1280     //ADXL_CONVERSION_RATE*32
#define LOG_SYNC_TIME_INTERVAL_MS            300000   //Once every five minutes???????????
#define TEMP_UPDATE_INTERVAL_MS              30000    //Once per minute
#define RTC_UPDATE_INTERVAL_MS               36000  //Once per hour
#define EXTERNAL_POWER_TEST_INTERVAL_MS      30000    //120000	//Once every two minutes

#define NUM_NAP_RELATED_TIMERS   5 //must be <= NUM_TIMERS
#define NUM_TIMERS               8

Timer batteryCheckTimer(BATTERY_TIMER, BATTERY_TEST_INTERVAL_MS);
Timer logSyncTimer(LOG_TIMER, LOG_SYNC_TIME_INTERVAL_MS);
Timer updateTempsTimer(TEMP_UPDATE_TIMER, TEMP_UPDATE_INTERVAL_MS);
Timer accelTimer(ADXL_POLL_TIMER, ADXL_FIFO_RATE);
Timer pollTempsTimer(TEMP_POLL_TIMER, DS18B20_10BIT_MAX_CONVERSION_TIME_MS);
Timer updateRTCTimer(RTC_TIMER, RTC_UPDATE_INTERVAL_MS);
//How often do we check to see if we've be brought online
Timer pollForPowerTimer(POWER_TIMER, EXTERNAL_POWER_TEST_INTERVAL_MS);
//How long do we wiat after sending a message before panicing and going into offline mode
Timer messageConfTimer(MESSAGE_TIMER, MESSAGE_CONFIRMATION_TIMEOUT_MS);

//Timers that should not be used in determining nap times must be placed at the end of the array 
Timer* const timers[NUM_TIMERS]={
  &logSyncTimer, &updateTempsTimer, &pollTempsTimer, &pollForPowerTimer, &accelTimer, //Nap related
  &updateRTCTimer, &batteryCheckTimer, &messageConfTimer};               //Not nap related

#pragma mark -
#pragma mark Globals

//#############################
//             Globals
//#############################

WatchdogSleeper WDT;

RTC_DS1337 RTC;                 //Real Time Clock object

SdFat SD;                       //SD card filesystem object

OneWire oneWire(ONE_WIRE_BUS);  // Instantiate a oneWire instance

DallasTemperature dallasSensors(&oneWire);  // Instantiate Dallas Temp sensors on oneWire 

ArduinoOutStream cout(Serial);  // Serial print stream

uint8_t systemStatus=0;   //x,newheader,header,accel,temps,RTC,sd,logfile
#define SYS_NOMINAL     0x3F
#define SYS_FILE_OK     0x01
#define SYS_SD_OK       0x02
#define SYS_RTC_OK      0x04
#define SYS_TEMP_OK     0x08
#define SYS_ADXL_OK     0x10
#define SYS_HEADER_OK   0x20
#define SYS_HEADER_NEW  0x40

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

uint32_t resetTime;

volatile boolean inactive=false;
volatile uint8_t accelerometerInterrupt = 0;
volatile boolean accelerometerCausedWakeup = false;
volatile boolean retrieve_fifo_accels=true;
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
    WDT.on(WDT._prescaler);
  else
    _WD_CONTROL_REG &= (~(1<<WDIE)); //Disable the WDT interrupt
  
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
	
	// Switch update source for timer, if required
  if (WDT._switchUpdateSourceToMsTimer2Queued) {
    WDT._switchUpdateSourceToMsTimer2Queued=false;
    setTimerUpdateSourceToMsTimer2();
    _WD_CONTROL_REG &= (~(1<<WDIE));
    WDT._autorestart=false;
  }
}


//=============================
// Accelerometer ISR
/*
each time hit one of the following:
  go active, go inactive, freefall, watermark & active, watermark & inactive

inactive && activity -> switch watermark to active pin & inactive=false
inactive && freefall -> switch watermark to active pin & inactive=false
inactive && watermark -> nothing
!inactive & watermark -> retrieve_fifo_accels
!inactive & inactivity -> retrieve_fifo_accels & & inactive=true & switch watermark to other pin

initial condition ->
  inactive=true;
  retrieve_fifo_accels=true;
*/
//=============================
void accelerometerISR(void) {

 
  ADXL345.readRegister(ADXL_INT_SOURCE, 1, (char*) &accelerometerInterrupt);
  ADXL345.readRegister(ADXL_FIFO_STATUS,1, (char*) &n_in_fifo);
	
  if ( inactive ) {
    if (accelerometerInterrupt & (ADXL_INT_ACTIVITY | ADXL_INT_FREEFALL)) {

      //We've got activity
      inactive=false;
    
      //Switch watermark to active pin
      uint8_t interrupts= ADXL_INT_FREEFALL | ADXL_INT_WATERMARK | 
                          ADXL_INT_ACTIVITY  | ADXL_INT_INACTIVITY;
      ADXL345.writeRegister(ADXL_INT_MAP, ~interrupts );
            
      if ( accelerometerInterrupt & ADXL_INT_WATERMARK )
        retrieve_fifo_accels=true;
      
    }
    else {
      //watermark
      //inactivity (shouldn't be possible to get inactivity while inactive)
    }
    
  }
	else {
  
    if ( accelerometerInterrupt & ADXL_INT_WATERMARK )
      retrieve_fifo_accels=true;

    if (accelerometerInterrupt & ADXL_INT_INACTIVITY) {
      inactive=true;
      retrieve_fifo_accels=true; 
      //Switch watermark to unused pin
      uint8_t interrupts= ADXL_INT_FREEFALL | ADXL_INT_ACTIVITY  | ADXL_INT_INACTIVITY;
      ADXL345.writeRegister(ADXL_INT_MAP, ~interrupts );
    }
    
    //freefall
    //activity ,(surpurfolous)
    if ( accelerometerInterrupt & ADXL_INT_ACTIVITY )
      retrieve_fifo_accels=true;

  }
	
  if (asleep) {
    WDT.cancelSleep();
    accelerometerCausedWakeup = true;
  }
  
  #ifdef DEBUG_ACCEL
    uint8_t interrupts;
    ADXL345.readRegister(ADXL_INT_MAP,1, (char*) &interrupts);

    cout<<pstr("#hit, ai=");Serial.print(accelerometerInterrupt,BIN);
    cout<<" n="<<(uint16_t)n_in_fifo<<" map=";Serial.print(interrupts,BIN);
    if (!digitalRead(ACCELEROMETER_INTERRUPT_PIN))
      cout<<pstr(" low");
    else 
      cout<<pstr(" high");
    if (retrieve_fifo_accels)
      cout<<pstr(" store=t ");
    else 
      cout<<pstr(" store=f ");
    if (inactive)
      cout<<pstr("in");
    cout<<pstr("active\n");
  #endif
  
}
  
//=============================
// WDT ISR callback function
//=============================
void timerUpdater(uint32_t delta) {
  for (int i=0; i<NUM_TIMERS; i++)
    timers[i]->increment(delta);
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
   
  pinMode(ACCELEROMETER_INTERRUPT_PIN, INPUT);
  
  pinMode(ACCELEROMETER_CS,OUTPUT);
  digitalWrite(ACCELEROMETER_CS,HIGH);
  pinMode(SD_CS,OUTPUT);
  digitalWrite(SD_CS,HIGH);
  pinMode(EJECT_PIN,INPUT);
  digitalWrite(EJECT_PIN,HIGH);
  
  Wire.begin();
  
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
  #ifdef DEBUG_STARTUP
    Serial.print(F("#WDT clock: "));
    Serial.print(WDT.clockRatekHz());
    Serial.println(F(" kHz"));
  #endif
  
  // Initialize timers
  batteryCheckTimer.start();
  updateTempsTimer.start();
  updateRTCTimer.start();

  // Initialize Accelerometer
  #ifdef DEBUG_STARTUP
    Serial.print(F("#Init ADXL..."));
  #endif
  ADXL345.init(ACCELEROMETER_CS);
  attachInterrupt(ACCELEROMETER_INTERRUPT, accelerometerISR, FALLING);
  if (!digitalRead(ACCELEROMETER_INTERRUPT_PIN)) {
    accelerometerISR();
  }
  systemStatus|=SYS_ADXL_OK;
  #ifdef DEBUG_STARTUP
    Serial.println(F("done"));
  #endif
  
  // Initialize the temp sensors
  #ifdef DEBUG_STARTUP
    Serial.print(F("#Init temp..."));
  #endif
  dallasSensors.begin();
  dallasSensors.setResolution(10);  //configure for 10bit, conversions take 187.5 ms max
  dallasSensors.setWaitForConversion(false);
  systemStatus|=SYS_TEMP_OK;
  #ifdef DEBUG_STARTUP
    Serial.println(F("done"));
  #endif
  
  // Initialize RTC
  #ifdef DEBUG_STARTUP
    cout<<pstr("#Init RTC...");
  #endif
  if (! RTC.isrunning()) {
    #ifdef DEBUG_STARTUP
      Serial.println(F("begin..."));
    #endif
    RTC.adjust(DateTime(__DATE__, __TIME__));
    RTC.begin();
  }
  if ( !RTC.isrunning()) {
    #ifdef DEBUG_STARTUP
      Serial.println(F("fail"));
    #endif
  }
  else {

    systemStatus|=SYS_RTC_OK;

    // Set date time callback function
    SdFile::dateTimeCallback(dateTime);
    
    //Set millis counter to proper point in day
    DateTime now=RTC.now();
    resetTime=now.unixtime();
    cli();
    timer0_millis=(now.unixtime()%86400)*1000;
    sei();
    
    #ifdef DEBUG_STARTUP
      Serial.println(F("done"));
    #endif
  }

  // Initialize SD card
  char name[] = "LOG.CSV";

  #ifdef DEBUG_STARTUP
    cout<<pstr("#Init SD...");
  #endif  
  if (!SD.init(SPI_FULL_SPEED, SD_CS)) {
    SD.initErrorPrint();
    errorLoop();
  }
  else {
    systemStatus|=SYS_SD_OK;
  }
  
  Logfile_Data_Start=ID_SIZE + 13;  //Header size
  
  if (SD.exists(name)) {
    //Try to read header info and resume operation
    logfile.open(name, O_RDWR);
    if (!logfile.isOpen()) { 
      cout<<pstr("#file.reopen");
      errorLoop();
    }
	  systemStatus|=SYS_FILE_OK;
    
    int16_t header_size=logfile.read();
    logfile.seekSet(ID_SIZE+1);
    logfile.read((void*)&writePos,sizeof(writePos));
    logfile.read((void*)&readPos,sizeof(readPos));
    logfile.read((void*)&Logfile_End,sizeof(Logfile_End));
    
    #ifdef DEBUG_LOGFILE
      Serial.println(F("#Log Opened"));
      Serial.print(F("# Header size="));Serial.println(header_size);
      Serial.print(F("# Wptr="));Serial.println(writePos);
      Serial.print(F("# Rptr="));Serial.println(readPos);
      Serial.print(F("# EOF="));Serial.println(Logfile_End);
    #endif
    
    //Sanity check
    if (writePos > MAX_LOGFILE_SIZE_BYTES ||
      readPos > MAX_LOGFILE_SIZE_BYTES ||
      Logfile_End > MAX_LOGFILE_SIZE_BYTES) {
      cout<<pstr("#Bad Header");
      logfile.close();
    }
    else {
      systemStatus|=SYS_HEADER_OK;
    }
     
  }
  
  if (!logfile.isOpen()) {
    // create a new file in root, the current working directory
    logfile.open(name, O_RDWR | O_TRUNC | O_CREAT);
    if (!logfile.isOpen()) { 
      cout<<pstr("#file.open");
      errorLoop();
    }
    systemStatus|=SYS_FILE_OK;

    readPos=writePos=Logfile_End=Logfile_Data_Start;
	
    logfile.write((uint8_t) Logfile_Data_Start); //Header Size
    logfile.write(ID,ID_SIZE);		 //File Info
    logfile.write((void*)&writePos,sizeof(writePos));
    logfile.write((void*)&readPos,sizeof(readPos));
    logfile.write((void*)&Logfile_End,sizeof(Logfile_End));
    logfile.sync();
    
    systemStatus|=SYS_HEADER_NEW;
  }
  #ifdef DEBUG_STARTUP
    cout<<pstr("done. File:")<<name<<endl;
  #endif

  // Initialize power mode
  powered=START_POWERED;
  if (!powered) {
    pollForPowerTimer.start();
    setTimerUpdateSourceToWDT();
  } 
  else {
    setTimerUpdateSourceToMsTimer2();
  }

  #ifdef DEBUG_STARTUP
    cout<<pstr("#Free RAM: ")<<FreeRam()<<endl;
  #endif
  
  cout<<pstr("#Startup: ");Serial.println(systemStatus,HEX);
  
}


void errorLoop(void) {
  while(1) {
    cout<<pstr("Fatal Error: ");
    Serial.println(systemStatus,HEX);
    delay(5000);
  }
}

//========================================================
//--------------------------------------------------------
//   loop
//--------------------------------------------------------
//========================================================

void loop(void){

  boolean dataFromLogfile=false;
  uint32_t availableNaptimeMS;
  SleepMode sleepMode;

  // Serial Monitoring
  // Any and all responses should be in the buffer
  // possible responses: '!', '#', '#t'uint32_t, & 't'uint32_t
  if(Serial.available()) {
    #ifdef DEBUG_PROTOCOL
      uint8_t temp=Serial.peek();
      Serial.print(F("#Byte In: '"));
      Serial.print((uint16_t)temp);Serial.println("'");
      if (!messageConfTimer.expired()){
        Serial.print(F("#Conf mID "));Serial.println(msgID);
      }
    #endif

    messageConfTimer.stop();
    messageConfTimer.reset();
    switch (Serial.read()) {
	
      case '!': //We've got Power!!
        powerUp();
        break;

      case '#': //Message sucessfully sent, may also have a time update pending
        bufferRewind();
        if (Serial.peek()!='t')
          break;
        else
          Serial.read();

      case 't': //timeupdate
        updateRTCTimer.reset();
        updateRTCTimer.start();
        updateRTCPending=false;
        setRTCFromSerial();
        break;

      default:
        bufferRewind(); //Why is this here???
        break;
    }

    // Make sure no garbage builds up
    Serial.flush();
    
  }
  else if (messageConfTimer.expired())  {
    #ifdef DEBUG_PROTOCOL
      Serial.print(F("#T/O mID "));Serial.println(msgID);
    #endif
    messageConfTimer.stop();
    messageConfTimer.reset();
    #ifdef DEBUG_STAY_POWERED
      bufferRewind();
      Serial.println(F("#Skipping PD"));
    #else
      powerDown();
    #endif
  }

  // See if we need to remove SD card
  if (!digitalRead(EJECT_PIN)) {
    delay(500);
    if (!digitalRead(EJECT_PIN)) {
      logfile.close();
      Serial.println(F("#Safe to remove SD card"));
      while(1);
    }
  }
  
  
  // Reset millis()
  if (needToResetMillis()) {
    resetMillis();
    bufferPut(temps, N_TEMP_SENSORS*sizeof(float)); //Resend temp date as a time sync
  }
    
  /*
  // Periodically check the battery status 
  if (batteryCheckTimer.expired()) {
    cout<<'B'<<testBattery()<<endl;
    batteryCheckTimer.reset();
    batteryCheckTimer.start();
  }
  */

  // Periodically check for a connection while unpowered
  if (!powered && pollForPowerTimer.expired()) {
    cout<<"?";msgID++;
    messageConfTimer.reset();
    messageConfTimer.start();
    pollForPowerTimer.reset();
    pollForPowerTimer.start();
  }

  // Temperature Conversion
  if (updateTempsTimer.expired()) {
    dallasSensors.requestTemperatures(); //Issue a global temperature conversion request
    #ifdef DEBUG_TEMP
      cout<<"#Requesting T\n";
    #endif
    pollTempsTimer.reset();
    pollTempsTimer.start();
    updateTempsTimer.reset();
    updateTempsTimer.start();
  }
  
  
  // Handle case where we are no longer powered
  //  but there is a message in the buffer
  if (!powered && !bufferIsEmpty() ) {
    if (!dataFromLogfile) {
      logData();
    }
    else {
      ungetLogDataFromFile();
    }
  } 

  
  // Temperature Monitoring
  if (pollTempsTimer.expired()) {
    #ifdef DEBUG_TEMP
      cout<<"#Poll T\n";
    #endif
    for (unsigned char i=0; i<N_TEMP_SENSORS; i++)
        temps[i]=dallasSensors.getTempCByIndex(i); //NB Returns -127 if a temp sensor is disconnected
    bufferPut(temps, N_TEMP_SENSORS*sizeof(float));
    pollTempsTimer.reset();
  }


  // Acceleration Monitoring
  if (retrieve_fifo_accels) {
    
    #ifdef DEBUG_ACCEL

      cout<<pstr("# Accel. int=");Serial.print(accelerometerInterrupt,HEX);
      if (accelerometerInterrupt & ADXL_INT_DATAREADY)	  cout<<pstr(", data ready");
      if (accelerometerInterrupt & ADXL_INT_ACTIVITY)	  cout<<pstr(", activity");
      if (accelerometerInterrupt & ADXL_INT_FREEFALL)	  cout<<pstr(", freefall");
      if (accelerometerInterrupt & ADXL_INT_INACTIVITY) cout<<pstr(", inactivity");
      if (accelerometerInterrupt & ADXL_INT_OVERRUN)	  cout<<pstr(", data dropped");
      if (accelerometerInterrupt & ADXL_INT_WATERMARK)  cout<<pstr(", watermark");
      cout<<". N in FIFO: "<<(unsigned int)n_in_fifo<<endl;
     
      uint8_t interrupts;
      ADXL345.readRegister(ADXL_INT_MAP,1, (char*) &interrupts );
      cout<<pstr("# Int map: ");Serial.println(interrupts,HEX);
    #endif
    
    
    retrieve_fifo_accels=false;
    
    if (n_in_fifo < 32) {
      delay(40*(32-n_in_fifo)+10);  //40 is for sample rate of 25Hz
      ADXL345.readRegister(ADXL_FIFO_STATUS, 1, (char*) &n_in_fifo );
    }
    for (uint8_t i=0; i<n_in_fifo;i++) {
      ADXL345.getRawAccelerations(accel);
      bufferPut(accel,6);
    }
    
    accelTimer.reset();
    if (!inactive)
      accelTimer.start();
    
    //accelerometerISR();
    #ifdef DEBUG_ACCEL
      if (digitalRead(3)) cout<<pstr("#Accel int. inactive")<<endl;
      else cout<<pstr("#Accel int. active: BAD")<<endl;
    #endif

  }
  
  if(accelTimer.expired()) {
    #ifdef DEBUG_ACCEL
      cout<<pstr("#Accel tim. exp.")<<endl;
    #endif
    accelTimer.reset();
    accelerometerISR();
  }
  
  
  // Upload old data
  if (powered && bufferIsEmpty()) {
    #ifdef DEBUG_LOGFILE
      cout<<"#GLDfF\n";
      cout<<pstr("# buffer: ")<<(unsigned int) bufferSpaceRemaining()<<" "<<(unsigned int)bufferPos()<<endl;
    #endif
    dataFromLogfile=getLogDataFromFile();
    #ifdef DEBUG_LOGFILE
      cout<<pstr("# buffer: ")<<(unsigned int) bufferSpaceRemaining()<<" "<<(unsigned int)bufferPos()<<endl;
    #endif
  }



  // Save or send the log data
  if(!bufferIsEmpty()) {
    
    if (!dataFromLogfile) {   // Add a timestamp
      uint32_t unixtime=RTC.now().unixtime();
      uint32_t millisTime=millis();
      
      bufferPut(&unixtime,4);
      bufferPut(&millisTime,4);
    }
    
    if (!powered) logData();
    else          sendData();    

  }



  // Sync the logfile
  //   NB timer is started by logData()
  if (logSyncTimer.expired()) {
    #ifdef DEBUG_LOGFILE
      Serial.println(F("#Logfile sync"));
    #endif
    logfile.sync();
    logSyncTimer.stop();
    logSyncTimer.reset();
  }
  
  
  
  // RTC monitoring
  // updateRTCPending prevents spamming if the host never sends good values
  if (powered) {
    if (!updateRTCPending) {
      if (updateRTCTimer.expired()) {
        cout<<"t";msgID++;
        updateRTCPending=true;
        messageConfTimer.reset();
        messageConfTimer.start();
      }
    }
  }
      
  
  // Determine how much time we can sleep
  if (messageConfTimer.running() || messageConfTimer.expired()) {
    sleepMode=SLEEP_IDLE;
    availableNaptimeMS=messageConfTimer.value();
  }
  else {
    sleepMode=SLEEP_HARD;
	
    //Find min value of running timers,
    // Ignore interrups here as we don't need to get that picky
    availableNaptimeMS=(timers[0]->running() || timers[0]->expired()) ? timers[0]->value() : MAX_UINT32;
    for (int i=1; i<NUM_NAP_RELATED_TIMERS; i++) {
      uint32_t temp;

      temp=(timers[i]->running() || timers[i]->expired()) ? timers[i]->value() : MAX_UINT32;
      
      if (temp < availableNaptimeMS) {
        availableNaptimeMS=temp;
      }
    }
  }

  // Go to sleep to conserve power
  if (!retrieve_fifo_accels) {
    #ifdef DEBUG_SLEEP
      cout<<"#Sleep "<<availableNaptimeMS<<" ms.\n";
      uint32_t timepoint; timepoint=millis();
    #endif

    goSleep(availableNaptimeMS, sleepMode);

    #ifdef DEBUG_SLEEP
      if (availableNaptimeMS < 0) 
        cout<<"#Overslept: "<<millis()-timepoint-availableNaptimeMS<<" ms.\n";
    #endif
  }
  
  while(messageConfTimer.running()); //MUST expire before next loop or bad things happen
  
}



boolean needToResetMillis() {
  DateTime now=RTC.now();
  if ( (now.unixtime() % 86400 == 0) && resetTime!=now.unixtime()){
    resetTime=now.unixtime();
    return true;
  }
  else
    return false;
}

//=======================================
// getLogDataFromFile() - Grabs the next logged line
//  from the logfile. Returns true if a line was
//  grabbed, false otherwise.
//  Requires buff.width() >= longest log message
//=======================================
boolean getLogDataFromFile() {
  
  if (readPos!=writePos) {
    
    logfile.seekSet(readPos);
    uint8_t recordSize=logfile.read();
    if (recordSize != -1) { 
        logfile.read(bufferWritePtr(), recordSize);
        bufferIncrementWritePtr(recordSize);
    }
    else {
      cout<<pstr("#This can't happen.\n"); //Unless no data has been logged
    }
    
    //If we've reached the end of file rewind
    if (logfile.peek()==-1) 
      logfile.seekSet(Logfile_Data_Start);

    readPos=logfile.curPosition();
	
    //Update the file header
    logfile.seekSet(Logfile_Data_Start-2*sizeof(writePos));
    logfile.write((void*)&readPos,sizeof(readPos));
	
    return true;

  }

  return false; //We've reported all the logged data	
}


void ungetLogDataFromFile() {
  if (readPos == Logfile_Data_Start ) {
    //wrap around to end
    logfile.seekCur(Logfile_End-bufferGetRecordSize());
  }
  else {
    logfile.seekCur(-bufferGetRecordSize());	//rewind readPos
  }
  readPos=logfile.curPosition();
  
  //Update the file header
  logfile.seekSet(Logfile_Data_Start-2*sizeof(writePos));
  logfile.write((void*)&readPos,sizeof(readPos));
  
  bufferRewind();
} 


//=======================================
// logData() - Writes the contents of buff
//	 to logfile, requires buff end in endl
//	 fails if out of space
//=======================================
void logData() {
  if (bufferIsEmpty()) {
    return;	// Nothing to log
  }
  uint32_t futurePos=writePos + bufferGetRecordSize();
  
      //can wp be < rp && (fp overflow || fp >= max filesize) 
  if ( writePos >= readPos || futurePos < writePos) {
    if (futurePos < MAX_LOGFILE_SIZE_BYTES && futurePos > writePos ) {
    
      #ifdef DEBUG_LOGFILE
        cout<<pstr("#Logging (rp<=wp)")<<(uint16_t)bufferGetRecordSize()<<pstr(" bytes at")
        <<writePos<<endl;
      #endif
    
      logfile.seekSet(writePos);
      logfile.write(bufferGetRecordPtr(), bufferGetRecordSize());
      logSyncTimer.start();
      
      // Update the file write pointer and extents
      writePos=logfile.curPosition();
      Logfile_End=Logfile_End > writePos ? Logfile_End:writePos;
      
      // Update the file header
      logfile.seekSet(Logfile_Data_Start-3*sizeof(writePos));
      logfile.write((void*)&writePos,sizeof(writePos));
      logfile.seekCur(sizeof(readPos));//logfile.write((void*)&readPos,sizeof(readPos));
      logfile.write((void*)&Logfile_End,sizeof(Logfile_End));
	  
      bufferRewind();
	  
      return;
    }
    else {
      logfile.seekSet(Logfile_Data_Start); 
      writePos=logfile.curPosition();
      futurePos=writePos+bufferPos();
    }
  }
	
  if (futurePos<readPos) {
  
    #ifdef DEBUG_LOGFILE
      cout<<pstr("#Logging (wp<rp)")<<(uint16_t)bufferGetRecordSize()<<pstr(" bytes at")
      <<writePos<<endl;
    #endif

    logfile.seekSet(writePos);
    logfile.write(bufferGetRecordPtr(), bufferGetRecordSize());
    logSyncTimer.start();
    
    // Update write pointer
    writePos=logfile.curPosition();
	
	
    // Update the file header
    logfile.seekSet(Logfile_Data_Start-3*sizeof(writePos));
    logfile.write((void*)&writePos,sizeof(writePos));
    //logfile.write((void*)&readPos,sizeof(readPos));
    //logfile.write((void*)&Logfile_End,sizeof(Logfile_End));
	
    bufferRewind();
  }
  else {
    cout<<pstr("#Logfile Full\n");
    bufferRewind();  //log message is lost
  }
  
}


//=============================
// sendData - send the buffer over serial
//=============================
void sendData() {
  if (bufferIsEmpty()) {
    return;	//Nothing to log
  }
  msgID++;
  #ifdef DEBUG_PROTOCOL
    Serial.print(F("#Send mID "));
    Serial.print(msgID);
    Serial.print(F(", length "));
    Serial.println((uint16_t)bufferGetRecordSize());
  #endif
  
  Serial.write('L');
  Serial.write(bufferGetRecordPtr(), bufferGetRecordSize());

  messageConfTimer.reset();
  messageConfTimer.start();
}






//=============================
// goSleep - given a duration and mode,
//  it sleeps for that long
//=============================
void goSleep(uint32_t duration_ms, SleepMode mode) {

  //Log the data so SD card powers down
  logfile.sync();
  logSyncTimer.stop();
  logSyncTimer.reset();
   
  WDT.configureSleep(mode);
  asleep=true;
  #ifdef DEBUG_FAKE_SLEEP
    WDT.fakeSleep(duration_ms);
  #else
    if (duration_ms < WDT.minimumSleepTime_ms()) {
      WDT.fakeSleep(duration_ms);
    }
    else {
      if (powered) {
        MsTimer2::stop();
        power_timer2_disable(); 
        WDT.enableCallback();
        WDT.sleep(duration_ms);
        
        cli();
        if (WDT.running() ) {
          WDT.queueCallbackSwitchToMsTimer2();
        }
        else {
          setTimerUpdateSourceToMsTimer2();
        }
        sei();
        
      }
      else{
        WDT.sleep(duration_ms);
        WDT.enableAutorestart(0);
        if (!WDT.running()) 
          WDT.on(0);
      }
    }
  #endif
  asleep=false;
}

//=============================
// powerUp - Sets timer update source to
//  MsTimer2, stops poll for power timer,
//  sets powered to true
//=============================
void powerUp(void ) {
  if(!powered){
    #ifdef DEBUG_PROTOCOL | DEBUG_SLEEP
      cout<<pstr("#PU\n");
    #endif
    powered=true;
    WDT.queueCallbackSwitchToMsTimer2();
    pollForPowerTimer.reset();
    pollForPowerTimer.stop();
  }
}

//=============================
// powerDown - Sets timer update source to
//  WDT, starts poll for power timer,
//  clears RTC update pending status
//  sets powered to false
//=============================
void powerDown(void) {
  if (powered) {
    #ifdef DEBUG_PROTOCOL | DEBUG_SLEEP
      cout<<pstr("#PD\n");
    #endif
    powered=false;
    setTimerUpdateSourceToWDT();
    pollForPowerTimer.start();
    updateRTCPending=false;
  }
}


//=============================
// setRTCFromSerial - Attemps to grab
// 4 bytes from serial, parse as
// uint32_t
// and use to set the RTC time
// returns true if RTC time was sucessfully set
//=============================
boolean setRTCFromSerial() {
  uint32_t unixtime=0;
  uint8_t byteIn=0;
  uint8_t numBytes;

  delay(5);
  numBytes=Serial.available();

  #ifdef DEBUG_RTC
    cout<<pstr("#Bytes avail: ")<<(uint16_t)numBytes<<endl;
  #endif

  uint8_t i=0;
  while(Serial.available() && i<4) {
    byteIn=Serial.read();
    unixtime |=((uint32_t)byteIn)<<(8*(3-i++));
  }
  
  DateTime now(unixtime);

  #ifdef DEBUG_RTC
    cout<<pstr("#Total bytes in: ")<<(uint16_t)i<<endl;
    cout<<"# Recieved Time: ";Serial.print(unixtime,HEX);cout<<" "<<now<<endl;      
  #endif

  if (now.year()>2010 && now.year()<2030) {
    #ifdef DEBUG_RTC
      cout<<pstr("#Set RTC to: ")<<now<<endl;
    #endif 
    RTC.adjust(now);
    return true;
  }
  else {
    cout<<pstr("#Bad RTC data.\n");
    return false;
  }

}

/*
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


//=============================
// setTimerUpdateSourceToWDT
//  does as named, WDT has  
//  16ms minimum time slice
//=============================
void setTimerUpdateSourceToWDT(void) {
  MsTimer2::stop();
  power_timer2_disable(); 
  WDT.enableAutorestart();
  WDT.on(0);
  WDT.enableCallback();
}


//=============================
// setTimerUpdateSourceToMsTimer2
//  does as named, timeslice is 
//  defined by MSTIMER2_DELTA
//  minimum 1ms,
//	Use with caution, will appear as if elapsed WDT time never happened 
//=============================
void setTimerUpdateSourceToMsTimer2(void) {
  WDT.disableCallback();
  power_timer2_enable();
  MsTimer2::set(MSTIMER2_DELTA, timerUpdater);
  MsTimer2::start(); 
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
