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
#define MESSAGE_CONFIRMATION_TIMEOUT_MS      32
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

/*typedef struct datarecord={
  uint32_t unixtime,
  uint32_t mills,
  float temps[],
  float accel[3]
} datarecord;*/

WatchdogSleeper WDT;

RTC_DS1307 RTC;                 //Real Time Clock object

SdFat SD;                       //SD card filesystem object

OneWire oneWire(ONE_WIRE_BUS);  // Instantiate a oneWire instance

DallasTemperature dallasSensors(&oneWire);  // Instantiate Dallas Temp sensors on oneWire 

ArduinoOutStream cout(Serial);  // Serial print stream


char buf[LINE_BUFFER_SIZE];  // backing buffer to bout
fstream logfile;             // file for logging
uint32_t writePos, readPos;


float accel[4][3];
float temps[N_TEMP_SENSORS];
boolean logAccel = false;	//Set when there is data to log
boolean logTemps = false;


boolean powered=false;
boolean updateRTCPending=false;
volatile boolean asleep=false;


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
  
  //Start the serial connection
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


  // Initialize Accelerometer
  cout<<pstr("#Init ADXL...");
  pinMode(ACCELEROMETER_CS, INPUT);
  ADXL345.init(ACCELEROMETER_CS);
  enableAccelerometerInterrupt();  //Create an interrupt that will trigger when activity is detected.
  cout<<pstr("initialized.\n");

  // Initialize the temp sensors
  cout<<pstr("Init Temp...");
  dallasSensors.begin();
  dallasSensors.setResolution(10);  //configure for 10bit, conversions take 187.5 ms max
  dallasSensors.setWaitForConversion(false);
  cout<<pstr("initialized.\n"); //*/

  // Initialize RTC
  cout<<pstr("Init RTC...");
  Wire.begin();
  if (! RTC.isrunning()) {
    cout<<pstr("RTC NOT running\n");
    // following line sets the RTC to the date & time this sketch was compiled
    RTC.adjust(DateTime(__DATE__, __TIME__));
  }
  if (!RTC.begin()) {
    cout<<pstr("RTC f'd\n");
  } else {
    cout<<pstr("RTC init'd.\n");
    // set date time callback function
    SdFile::dateTimeCallback(dateTime);
  }//*/

  // Initialize SD card
  cout<<pstr("#Init SD...");
  // initialize the SD card at SPI_HALF_SPEED to avoid bus errors with
  // breadboards.  use SPI_FULL_SPEED for better performance.
  // if SD chip select is not SS, the second argument to init is CS pin number
  if (!SD.init(SPI_FULL_SPEED, SD_CS)) SD.initErrorHalt();
  // create a new file in root, the current working directory
  char name[] = "LOGGER.CSV";
  logfile.open(name, ios::in | ios::out | ios::trunc);
  if (!logfile.is_open()) 
    error("file.open");
    
  logfile<<pstr("#")<<name<<" "<<time()<<" "<<pstr(ID)<<endl;
  logfile.flush();
  writePos=logfile.tellp();
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
  cout<<pstr("#Free RAM: ")<<FreeRam()<<endl;

}

         
//========================================================
//--------------------------------------------------------
//   loop
//--------------------------------------------------------
//========================================================

void loop(void){

  obufstream bout(buf, sizeof(buf));
  boolean dataFromLogfile=false;
  uint32_t availableNaptimeMS;
  SleepMode sleepMode;

  // Serial Monitoring
  // Any and all responses should be in the buffer
  // possible responses:
  // '!', '#', '#tmmddyyyyHHMMSS', & 'tmmddyyyyHHMMSS'
  if(Serial.available()) {

    //Possible Responses
    //'!' to a powerup query
    //'#' reply to a datarecord
    //'tmmddyyyyHHMMSS' reply to a time query
    switch (Serial.read()) {
	
      case '!': //We've got Power!!
        //messageConfTimer.stop();
        //messageConfTimer.reset();
        powerUp();
        break;

      case '#': //Message sucessfully sent, may also have a time update pending
        bout.seekp(0);
        //messageConfTimer.stop();
        //messageConfTimer.reset();
        if (Serial.read()!='t')
        break;

      case 't': //timeupdate
        updateRTCTimer.reset();
        updateRTCTimer.start();
        updateRTCPending=false;
        delay(150);
        if (!setRTCFromSerial())
          cout<<pstr("#Setting RTC failed.\n");
        break;

      //Debugging case
      /*case 'p': //timeupdate
	if(powered) {
          powerDown();
        }
        else {
          powerUp();
        }
        break;*/
		
      default:
        break;
    }

    // Make sure no garbage builds up
    messageConfTimer.stop();
    messageConfTimer.reset();
    Serial.flush();
    
  }
  else if (messageConfTimer.expired())  {
    cout<<"#Msg.Tm.Exp.\n";
    messageConfTimer.stop();
    messageConfTimer.reset();
    powerDown();
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
    cout<<"?\n";
    messageConfTimer.reset();
    messageConfTimer.start();
    pollForPowerTimer.reset();
    pollForPowerTimer.start();
  }


  // Temperature Monitoring
  if (updateTempsTimer.expired()) {
    dallasSensors.requestTemperatures(); //Issue a global temperature conversion request
    cout<<"#Requesting T\n";
    pollTempsTimer.reset();
    pollTempsTimer.start();
    updateTempsTimer.reset();
    updateTempsTimer.start();
  }
  if (pollTempsTimer.expired()) {
    cout<<"#Poll T\n";
    getTemperatures();
    pollTempsTimer.reset();
    logTemps=true;
  }

  // Acceleration Monitoring
  if (accelerometerInterrupt & ADXL_INT_WATERMARK) {

    disableAccelerometerInterrupt();
    /*
    cout<<pstr("#Accel. int=")<<((unsigned int)accelerometerInterrupt);
    if (accelerometerInterrupt & ADXL_INT_ACTIVITY)	  cout<<pstr(", activity");
    if (accelerometerInterrupt & ADXL_INT_FREEFALL)	  cout<<pstr(", freefall");
    if (accelerometerInterrupt & ADXL_INT_INACTIVITY) cout<<pstr(", inactivity");
    if (accelerometerInterrupt & ADXL_INT_OVERRUN)	  cout<<pstr(", data dropped");
    if (accelerometerInterrupt & ADXL_INT_WATERMARK)  cout<<pstr(", watermark");
    cout<<". N in FIFO: "<<(unsigned int)n_in_fifo<<endl;
	*/
    
    if (store_fifo_accels) {
      for (uint8_t i=0; i<n_in_fifo;i++) {
        if (i < 3) ADXL345.getAccelerations(accel[i]);
        else ADXL345.getAccelerations(accel[3]);
        //cout<<" "<<accel[0]<<" "<<accel[1]<<" "<<accel[2]<<endl;
        logAccel=true;
      }
    }
    else {
      for (uint8_t i=0; i<n_in_fifo;i++) {
        ADXL345.getAccelerations(accel[0]);
      }
      //cout<<"Purged "<<(unsigned int)n_in_fifo<<" Millis: "<<millis()<<endl;
    }
	
    store_fifo_accels=!currently_inactive;
    accelerometerInterrupt=0;
    enableAccelerometerInterrupt();

  }

  // Necessary to log data to SD card if:
  //  power was lost before getting confirmation of last message sent
  //   determine by waiting until messageConfTimer expires 
  //  logAccel or logTemps is true and we are unpowered
  //Necessary to send data via serial if:
  // powered and log Accel of logTemps is true
  // powered and unsent data exists in the logfile
  // Deal with the unpowered case first
  if (!powered) {

    //Deal with the possibility of a lost message
    if (bout.tellp()>0) {
      if (dataFromLogfile) {
        logfile.seekg(-bout.tellp(),ios::cur);	//rewind readPos
        readPos=logfile.tellg();
        bout.seekp(0);
      }
      else {
        logData(bout);
      }
    }

    // Gather any data that needs to be logged and insert it into the
    //  output buffer in the proper format
    formatLogMessage(bout);
	  
    if (bout.tellp()>0) {
      logData(bout);
    }
    
  }
  else {
    
    formatLogMessage(bout);
    
    if (bout.tellp()==0) {
      dataFromLogfile=false;//getNextLoggedData(bout);
    }
    
    if (bout.tellp()>0) {
      cout<<bout.buf();
      messageConfTimer.reset();
      messageConfTimer.start();
    }
    
  }

  // Log the data
  if (logSyncTimer.expired()) {
      cout<<pstr("#Logfile flush\n");
      logfile.flush();
      logSyncTimer.stop();
      logSyncTimer.reset();
      // timer is started when data is written to the log file
  }
  
  // RTC monitoring
  // updateRTCPending prevents spamming if the host never sends good values
  if (powered) {
    if (!updateRTCPending) {
      if (updateRTCTimer.expired()) {
        cout<<"t\n";
        updateRTCPending=true;
        messageConfTimer.reset();
        messageConfTimer.start();
      }
    }
  }
      
  // Conserve power
  //How long can we sleep
  if (messageConfTimer.running() || messageConfTimer.expired()) {
    sleepMode=SLEEP_IDLE;
    availableNaptimeMS=0;//messageConfTimer.value();
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

  /*if (availableNaptimeMS > 15000) {
    cout<<"# Timer Values:\n";
    for (int i=0; i<NUM_TIMERS; i++) {
      cout<<"#   "<<timers[i]->getID()<<" "<<(timers[i]->running() ? 'r':(timers[i]->expired() ? 'e':'s'));
      cout<<" "<<timers[i]->value()<<endl;
    }
  }
  
  if (availableNaptimeMS == 0) {
    cout<<"# Timer Values:\n";
    for (int i=0; i<NUM_TIMERS; i++) {
      cout<<"#   "<<timers[i]->getID()<<" "<<(timers[i]->running() ? 'r':(timers[i]->expired() ? 'e':'s'));
      cout<<" "<<timers[i]->value()<<endl;
    }
  }//*/

  if (availableNaptimeMS > 100) {
    cout<<"#Sleep "<<availableNaptimeMS<<" ms.\n";
    uint32_t timepoint; timepoint=millis();

    goSleep(availableNaptimeMS, sleepMode);

    cout<<"#Overslept "<<millis()-timepoint-availableNaptimeMS<<" ms.\n";
  }
}



boolean needToResetMillis() {
  return false; 
}


//=============================
// goSleep - given a duration and mode,
//  it sleeps for that long
//=============================
void goSleep(uint32_t duration_ms, SleepMode mode) {
      logfile.flush();
      logSyncTimer.stop();
      logSyncTimer.reset();
   
  WDT.configureSleep(mode);
  asleep=true;
  //delay(duration_ms);
  WDT.sleep(duration_ms);
  WDT.enableAutorestart();
  WDT.on(0);
  asleep=false;
}


//=============================
// time - Returns the time
//=============================
inline char* time() {
  //DateTime now=RTC.now();
  //return now.unixtime();
  return "Now";
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
    setTimerUpdateSourceToWDT();//setTimerUpdateSourceToMsTimer2();
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
  cout<<Serial.available()<<endl;
  if (Serial.available() >= 20) {
    
    char date[11], time[8];
    for (int i=0;i<11;i++)
      date[i]=Serial.read();
    Serial.read();
    for (int i=0;i<8;i++)
      time[i]=Serial.read();
      
    DateTime now(date, time);
    cout<<pstr("#Set RTC to: ")<<now<<endl;
    RTC.adjust(DateTime(date, time));      
    return true;
  }
  while (Serial.available()) cout<<Serial.read()<<" ";
  cout<<endl;
  return false;
}

		
//=======================================
// getNextLoggedData() - Grabs the next logged line
//  from the logfile. Returns true if a line was
//  grabbed, false otherwise.
//  Requires buff.width() >= longest log message
//=======================================
boolean getNextLoggedData(obufstream &buff) {
	
  if (readPos!=writePos) {
    uint32_t count;
    
    logfile.seekg(readPos);
    logfile.getline(buff.buf(), buff.width(), '\n');
    count=logfile.gcount();

    if (logfile.fail()) {
      //Should never happen, we can't log lines longer that buff.width() by design
      cout<<pstr("#logfile.fail, in getNextLoggedData. ")<<readPos<<" "<<writePos<<" "<<(uint16_t)logfile.rdstate()<<endl;
      logfile.clear(logfile.rdstate() & ~ios_base::failbit);
      return false;
    } else if (logfile.eof()) {
      //Should never happen, logged lines always terminate with \n by design
      cout<<pstr("#logfile.eof, in getNextLoggedData. ")<<readPos<<" "<<writePos<<endl;
      return false;
    }

    buff.seekp(count);

    //If we've reach the end of file rewind
    if (logfile.peek()==-1) 
      logfile.seekg(0);

    readPos=logfile.tellg();
    return true;

  }

  return false; //We've reported all the logged data	
}


//=======================================
// logData() - Writes the contents of buff
//	 to logfile, requires buff end in endl
//	 fails if out of space
//=======================================
void logData(obufstream &buff) {
  if (buff.tellp()==0) {
    return;	//Nothing to log
  }
  uint32_t futurePos;
  
            //can wp be < rp && (fp overflow || fp >= max filesize) 
  futurePos=writePos + buff.tellp();
  if ( writePos >= readPos || futurePos < writePos) {
    if (futurePos < MAX_LOGFILE_SIZE_BYTES && futurePos > writePos ) {
      logfile.seekp(writePos);
      logfile<<buff.buf();
      logSyncTimer.start();
      
      // Debugging messages
      //cout<<'#'<<buff.buf();
      cout<<pstr("# case1 wp=")<<writePos<<" "<<readPos<<" "<<futurePos<<endl;

      writePos=logfile.tellp();
      buff.seekp(0);
      return;
    }
    else {
      logfile.seekp(0);
      writePos=logfile.tellp();
      futurePos=writePos+buff.tellp();
    }
  }
	
  if (futurePos<readPos) {
    logfile.seekp(writePos);
    logfile<<buff.buf();
    logSyncTimer.start();
    
    // Debugging messages
    //cout<<'#'<<buff.buf();
    cout<<pstr("# case2 wp=")<<writePos<<" "<<readPos<<" "<<futurePos<<endl;
    
    writePos=logfile.tellp();
    buff.seekp(0);
  }
  else {
    //cout<<'#'<<buff.buf();
    cout<<pstr("# case3(error) wp=")<<writePos<<" "<<readPos<<" "<<futurePos<<endl;
    //error("Out of space.");
    buff.seekp(0);  //log message is lost
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
		
		
//=======================================
// getTemperatures() - Fetches the temperature
//	 from each sensor
//=======================================
void getTemperatures() {
  //Get the results of the last conversion for each sensor on the bus
  for(unsigned char i=0; i<N_TEMP_SENSORS; i++)
    temps[i]=dallasSensors.getTempCByIndex(i);//20.34;//dallasSensors.getTempCByIndex(i);
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

//=============================
// formatLogMessage - Format the 
//  log message for output
//=============================
void formatLogMessage(obufstream &bout) { 
  if (logAccel) {
    logAccel=false;
    bout <<"A,"<<time()<<","<<accel[0][0]<<","<<accel[0][1]<<","<<accel[0][2]<<endl;
  }
  if (logTemps){
    logTemps=false;
    bout<<"T,"<<time()<<",";
    for (int i=0;i<N_TEMP_SENSORS-1;i++)
      bout<<temps[i]<<",";
    bout<<temps[N_TEMP_SENSORS-1]<<endl;
  }
}


//=======================================
// enableAccelerometerInterrupt() - Enables
//	 the accelerometer ISR
//=======================================
void enableAccelerometerInterrupt() {
	attachInterrupt(1, accelerometerISR, FALLING);  
}

//=======================================
// disableAccelerometerInterrupt() - Disables
//	 the accelerometer ISR
//=======================================
void disableAccelerometerInterrupt() {
	detachInterrupt(1);
}
