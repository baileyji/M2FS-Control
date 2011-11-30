#include <Wire.h>
#include <RTC_DS1337.h>
#include <SdFat.h>
#include <WatchdogSleeper.h>
#include <Timer.h>

WatchdogSleeper WDT;
RTC_DS1337 RTC;
ArduinoOutStream cout(Serial);  // Serial print stream

// Date/time format operator
ostream& operator << (ostream& os, DateTime& dt) {
  os << dt.year() << '/' << int(dt.month()) << '/' << int(dt.day()) << ' ';
  os << int(dt.hour()) << ':' << setfill('0') << setw(2) << int(dt.minute());
  os << ':' << setw(2) << int(dt.second()) << setfill(' ');
  return os;
}

boolean powered=true;
boolean updateRTCPending=false;
uint32_t msgID=0;

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
#define MSTIMER2_DELTA                 3      2	      // should be less than smallest timeout interval
#define MESSAGE_CONFIRMATION_TIMEOUT_MS      100
#define BATTERY_TEST_INTERVAL_MS             3600000  //Once per hour
#define DS18B20_10BIT_MAX_CONVERSION_TIME_MS 188
#define LOG_SYNC_TIME_INTERVAL_MS            300000   //Once every five minutes???????????
#define TEMP_UPDATE_INTERVAL_MS              30000    //Once per minute
#define RTC_UPDATE_INTERVAL_MS               400  //Once per hour
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
// WDT ISR callback function
//=============================
void timerUpdater(uint32_t delta) {
  for (int i=0; i<NUM_TIMERS; i++)
    timers[i]->increment(delta);
    WDT.cancelSleep();
}



void setup () {
  Serial.begin(115200);
  Wire.begin();
  
  // Initialize the watchdog timer
  WDT.off();
  WDT.calibrate();
  WDT.registerCallback(timerUpdater);
  WDT.enableAutorestart();
  WDT.enableCallback();
  WDT.on(0);
  
  
  // Initialize timers
  batteryCheckTimer.start();
  updateTempsTimer.start();
  updateRTCTimer.start();
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
  }
  
  
  
}

void loop () {
  DateTime now = RTC.now();
    
  if(Serial.available()) {  
    switch (Serial.read()) {
      case '#': //Message sucessfully sent, may also have a time update pending
        cout<<pstr("#Msg Conf for ID ")<<msgID<<endl;
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
        delay(150);
        if (!setRTCFromSerial())
          cout<<pstr("#Setting RTC failed.\n");
        break;

      default:
        break;
    }

    Serial.flush();    
  }
  else if (messageConfTimer.expired())  {
    cout<<pstr("#Msg. Tm. Exp. ID: ")<<msgID<<endl;
    messageConfTimer.stop();
    messageConfTimer.reset();
  }
  
  
  
  
  // RTC monitoring
  // updateRTCPending prevents spamming if the host never sends good values
  if (!updateRTCPending) {
      if (updateRTCTimer.expired()) {
        cout<<"t";
        updateRTCPending=true;
        messageConfTimer.reset();
        messageConfTimer.start();
      }
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
  cout<<pstr("#Bytes avail: ")<<(uint16_t)numBytes<<endl;
  
  uint8_t i=0;
  while(Serial.available() && i<4) {
    byteIn=Serial.read();
    unixtime |=((uint32_t)byteIn)<<(8*(3-i++));
  }

  cout<<pstr("#Total bytes in: ")<<(uint16_t)i<<endl;
  DateTime now(unixtime);
  cout<<"# Recieved Time: ";Serial.print(unixtime,HEX);cout<<" "<<now<<endl;      
       
  if (now.year()>2010 && now.year()<2030) {   
    cout<<pstr("#Set RTC to: ")<<now<<endl;
    RTC.adjust(now);
    return true;
  }
  else {
    cout<<pstr("#Bad data.\n");
    return false;
  }

}
