/*
TODO:
figure out why timer oly being decremented by 15 ms when sleep lasts for more than a second


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
#define ID "M2FS Datalogger test version"
#define ID_SIZE 28

#define DEBUG
//#define DEBUG_STAY_POWERED

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
#define MESSAGE_CONFIRMATION_TIMEOUT_MS      100
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
Timer pollTempsTimer(TEMP_POLL_TIMER, DS18B20_10BIT_MAX_CONVERSION_TIME_MS);
Timer pollADXLTimer(ADXL_POLL_TIMER, ADXL_FIFO_RATE); 
Timer updateRTCTimer(RTC_TIMER, RTC_UPDATE_INTERVAL_MS);
//How often do we check to see if we've be brought online
Timer pollForPowerTimer(POWER_TIMER, EXTERNAL_POWER_TEST_INTERVAL_MS);
//How long do we wiat after sending a message before panicing and going into offline mode
Timer messageConfTimer(MESSAGE_TIMER, MESSAGE_CONFIRMATION_TIMEOUT_MS);

//Timers that should not be used in determining nap times must be placed at the end of the array 
Timer* const timers[NUM_TIMERS]={
  &logSyncTimer, &updateTempsTimer, &pollTempsTimer, &pollForPowerTimer, &pollADXLTimer, //Nap related
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
  //WDT.enableAutorestart();
  //WDT.on(0);
  
  // Initialize timers
  batteryCheckTimer.start();
  updateTempsTimer.start();
  updateRTCTimer.start();


  // Initialize Accelerometer
  cout<<pstr("#Init ADXL...");
  ADXL345.init(ACCELEROMETER_CS);
  pollADXLTimer.reset();
  pollADXLTimer.start();
  //delay(5);
  attachInterrupt(ACCELEROMETER_INTERRUPT, accelerometerISR, FALLING);
  cout<<pstr("initialized.\n");

  // Initialize the temp sensors
  cout<<pstr("#Init Temp...");
  dallasSensors.begin();
  dallasSensors.setResolution(10);  //configure for 10bit, conversions take 187.5 ms max
  dallasSensors.setWaitForConversion(false);
  cout<<pstr("initialized.\n"); //*/

  // Initialize RTC
  cout<<pstr("#Init RTC...");
  if (! RTC.isrunning()) {
    cout<<pstr("RTC start\n");
    // following line sets the RTC to the date & time this sketch was compiled
    RTC.adjust(DateTime(__DATE__, __TIME__));
    RTC.begin();
  }
  if ( !RTC.isrunning()) {
    cout<<pstr("#RTC fail\n");
  }
  else {
    cout<<pstr("RTC init'd.\n");
    // set date time callback function
    SdFile::dateTimeCallback(dateTime);
  }

  // Initialize SD card
  char name[] = "LOG.CSV";
  cout<<pstr("#Init SD...");
  // initialize the SD card at SPI_HALF_SPEED to avoid bus errors with
  // breadboards.  use SPI_FULL_SPEED for better performance.
  // if SD chip select is not SS, the second argument to init is CS pin number
  if (!SD.init(SPI_FULL_SPEED, SD_CS)) SD.initErrorHalt();
  
  
  Logfile_Data_Start=ID_SIZE + 13;  //Header size
  
  if (SD.exists(name)) {
    //Try to read header info and resume operation
    logfile.open(name, O_RDWR);
    if (!logfile.isOpen()) 
      error("file.open");
	  
    int16_t header_size=logfile.read();
    logfile.seekSet(ID_SIZE+1);
    logfile.read((void*)&writePos,sizeof(writePos));
    logfile.read((void*)&readPos,sizeof(readPos));
    logfile.read((void*)&Logfile_End,sizeof(Logfile_End));
    
    //Sanity check
    if (writePos > MAX_LOGFILE_SIZE_BYTES ||
      readPos > MAX_LOGFILE_SIZE_BYTES ||
      Logfile_End > MAX_LOGFILE_SIZE_BYTES) {
      cout<<pstr("#Log header corrupt");
    }
     
  }
  
  if (!logfile.isOpen()) {
    // create a new file in root, the current working directory
    logfile.open(name, O_RDWR | O_TRUNC | O_CREAT);
    if (!logfile.isOpen()) 
      error("file.open"); 
  
    readPos=writePos=Logfile_End=Logfile_Data_Start;
	
    logfile.write((uint8_t) Logfile_Data_Start); //Header Size
    logfile.write(ID,ID_SIZE);		 //File Info
    logfile.write((void*)&writePos,sizeof(writePos));
    logfile.write((void*)&readPos,sizeof(readPos));
    logfile.write((void*)&Logfile_End,sizeof(Logfile_End));
    logfile.sync();
  }
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

  #ifdef DEBUG
    cout<<pstr("#Free RAM: ")<<FreeRam()<<endl;
  #endif
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
    uint8_t temp=Serial.peek();
    #ifdef DEBUG
      //cout<<pstr("#Byte In:")<<temp<<".\n";
    #endif
    switch (Serial.read()) {
	
      case '!': //We've got Power!!
        powerUp();
        messageConfTimer.stop();
        messageConfTimer.reset();
        break;

      case '#': //Message sucessfully sent, may also have a time update pending
        #ifdef DEBUG
          cout<<pstr("#Msg Conf for ID ")<<msgID<<endl;
        #endif
        bufferRewind();
        messageConfTimer.stop();
        messageConfTimer.reset();
        if (Serial.read()!='t')
          break;

      case 't': //timeupdate
        updateRTCTimer.reset();
        updateRTCTimer.start();
        updateRTCPending=false;
        messageConfTimer.stop();
        messageConfTimer.reset();
        setRTCFromSerial();
        break;

      default:
        #ifdef DEBUG
          cout<<pstr("#Msg Conf for ID ")<<msgID<<endl;
        #endif
        bufferRewind();
        messageConfTimer.stop();
        messageConfTimer.reset();
        break;
    }

    // Make sure no garbage builds up
    Serial.flush();
    
  }
  else if (messageConfTimer.expired())  {
    #ifdef DEBUG
      cout<<pstr("#Msg. Tm. Exp. ID: ")<<msgID<<endl;
    #endif
    messageConfTimer.stop();
    messageConfTimer.reset();
    #ifdef DEBUG_STAY_POWERED
      bufferRewind();
      cout<<pstr("Powerdown skipped.\n");
    #else
      powerDown();
    #endif
  }

  // See if we need to remove SD card
  if (!digitalRead(EJECT_PIN)) {
    delay(500);
    if (!digitalRead(EJECT_PIN)) {
      logfile.close();
      cout<<pstr("#Safe to remove SD card.\n");
      return; //End program (need to test this works)
    }
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
        temps[i]=dallasSensors.getTempCByIndex(i);//20.34;//dallasSensors.getTempCByIndex(i);
    bufferPut(temps, N_TEMP_SENSORS*sizeof(float));
    pollTempsTimer.reset();
  }


  // Acceleration Monitoring
  if (accelerometerInterrupt & ADXL_INT_WATERMARK) {
    
    #ifdef DEBUG_ACCEL
      cout<<pstr("# Accel. int=");Serial.print(accelerometerInterrupt,HEX);
      if (accelerometerInterrupt & ADXL_INT_DATAREADY)	  cout<<pstr(", data ready");
      if (accelerometerInterrupt & ADXL_INT_ACTIVITY)	  cout<<pstr(", activity");
      if (accelerometerInterrupt & ADXL_INT_FREEFALL)	  cout<<pstr(", freefall");
      if (accelerometerInterrupt & ADXL_INT_INACTIVITY) cout<<pstr(", inactivity");
      if (accelerometerInterrupt & ADXL_INT_OVERRUN)	  cout<<pstr(", data dropped");
      if (accelerometerInterrupt & ADXL_INT_WATERMARK)  cout<<pstr(", watermark");
      cout<<". N in FIFO: "<<(unsigned int)n_in_fifo<<endl;
    #endif

    
    if (store_fifo_accels) {
      if (n_in_fifo < 32) delay(40*(32-n_in_fifo)+10);  //40 is for sample rate of 25Hz
      for (uint8_t i=0; i<n_in_fifo;i++) {
        ADXL345.getRawAccelerations(accel);
        //cout<<"#  "<<accel[0]<<" "<<accel[1]<<" "<<accel[2]<<endl;
        bufferPut(accel,6);
      }
    }
    else {
      for (uint8_t i=0; i<n_in_fifo;i++) {
        ADXL345.getRawAccelerations(accel);
      }
      //cout<<"Purged "<<(unsigned int)n_in_fifo<<" Millis: "<<millis()<<endl;
    }
    pollADXLTimer.reset();
    pollADXLTimer.start();
    #ifdef DEBUG_ACCEL
      if (digitalRead(3)) cout<<pstr("#Accel int. inactive")<<endl;
      else cout<<pstr("#Accel int. active: BAD")<<endl;
    #endif

    store_fifo_accels=!currently_inactive;

  }
    
    
    
  // Upload old data
  if (powered && bufferIsEmpty()) {
    //cout<<"#GLDfF\n";
    //cout<<pstr("# buffer: ")<<(unsigned int) bufferSpaceRemaining()<<" "<<(unsigned int)bufferPos()<<endl;
    dataFromLogfile=getLogDataFromFile();
    //cout<<pstr("# buffer: ")<<(unsigned int) bufferSpaceRemaining()<<" "<<(unsigned int)bufferPos()<<endl;
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
      cout<<pstr("#Logfile sync\n");
      logfile.sync();
      logSyncTimer.stop();
      logSyncTimer.reset();
  }
  
  
  
  // RTC monitoring
  // updateRTCPending prevents spamming if the host never sends good values
  if (powered) {
    if (!updateRTCPending) {
      if (updateRTCTimer.expired()) {
        cout<<"t";
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
    //cout<<"# Message Naptime: "<<availableNaptimeMS<<endl;
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
        //cout<<"#  "<<temp<<endl;
        availableNaptimeMS=temp;
      }
    }
  }

  // Go to sleep to conserve power
  if (availableNaptimeMS > 100) {
    cout<<"#Sleep "<<availableNaptimeMS<<" ms.\n";
    uint32_t timepoint; timepoint=millis();

    goSleep(availableNaptimeMS, sleepMode);
    if (availableNaptimeMS < 0) 
      cout<<"#Overslept: "<<millis()-timepoint-availableNaptimeMS<<" ms.\n";
  }
  
  while(messageConfTimer.running()); //MUST expire before next loop or bad things happen
  
}



boolean needToResetMillis() {
  return millis() > 86400000; //Reset once per day 
}

//=======================================
// getLogDataFromFile() - Grabs the next logged line
//  from the logfile. Returns true if a line was
//  grabbed, false otherwise.
//  Requires buff.width() >= longest log message
//=======================================
boolean getLogDataFromFile() {
  
  return false;
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
    return;	//Nothing to log
  }
  if (powered) {
    cout<<pstr("#Logging while powered!\n");
    return;
  }
  uint32_t futurePos=writePos + bufferGetRecordSize();
  
      //can wp be < rp && (fp overflow || fp >= max filesize) 
  if ( writePos >= readPos || futurePos < writePos) {
    if (futurePos < MAX_LOGFILE_SIZE_BYTES && futurePos > writePos ) {
      logfile.seekSet(writePos);
      logfile.write(bufferGetRecordPtr(), bufferGetRecordSize());
      logSyncTimer.start();
      
      // Debugging messages
      cout<<pstr("#Logging ")<<(uint16_t)bufferGetRecordSize()<<pstr(" bytes\n");

      writePos=logfile.curPosition();
	  
      Logfile_End=Logfile_End > writePos ? Logfile_End:writePos;
      
      //Update the file header
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
    logfile.seekSet(writePos);
    logfile.write(bufferGetRecordPtr(), bufferGetRecordSize());
    logSyncTimer.start();
    
    // Debugging messages
    cout<<pstr("# case2 wp=")<<writePos<<" rp="<<readPos<<" fp="<<futurePos<<endl;
    
    writePos=logfile.curPosition();
	
	
    //Update the file header
    logfile.seekSet(Logfile_Data_Start-3*sizeof(writePos));
    logfile.write((void*)&writePos,sizeof(writePos));
//    logfile.write((void*)&readPos,sizeof(readPos));
//    logfile.write((void*)&Logfile_End,sizeof(Logfile_End));
	
    bufferRewind();
  }
  else {
    //cout<<'#'<<buff.buf();
    cout<<pstr("# case3(error) wp=")<<writePos<<" "<<readPos<<" "<<futurePos<<endl;
    //error("Out of space.");
    bufferRewind();  //log message is lost
  }
  
  
  //Update Logfile_End as needed, shall always have 

}


//=============================
// sendData - send the buffer over serial
//=============================
void sendData() {
  if (bufferIsEmpty()) {
    return;	//Nothing to log
  }
  msgID++;
  cout<<"#Send Message: "<<msgID<<pstr(". Length: ")<<(uint16_t)bufferGetRecordSize()<<endl;

  Serial.write('L');
//  Serial.write(thebuffer,thebuffer[0]+1);
  Serial.write(bufferGetRecordPtr(), bufferGetRecordSize());

  messageConfTimer.reset();
  messageConfTimer.start();
}






//=============================
// goSleep - given a duration and mode,
//  it sleeps for that long
//=============================
void goSleep(uint32_t duration_ms, SleepMode mode) {
      //logfile.sync();
      logSyncTimer.stop();
      logSyncTimer.reset();
   
  WDT.configureSleep(mode);
  asleep=true;
  //delay(duration_ms);
  WDT.sleep(duration_ms);
  //WDT.enableAutorestart();
  //WDT.on(0);
  asleep=false;
}

//=============================
// powerUp - Sets timer update source to
//  ???, stops poll for power timer,
//  sets powered to true
//=============================
void powerUp(void ) {
  if(!powered){
    cout<<pstr("#PU\n");
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
    cout<<pstr("#PD\n");
    powered=false;
    setTimerUpdateSourceToWDT();
    pollForPowerTimer.start();
    updateRTCPending=false;
  }
}


//=============================
// setRTCFromSerial - Attemps to grab
// 20 bytes from serial, parse as
// "Dec 26 2009 12:34:56"
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
  ///*
  MsTimer2::stop();
  power_timer2_disable(); 
  //*/
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
  
  //WDT.enableCallback();
  ///*
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
