/*
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
#define ID "v0.1"
#define ID_SIZE 4
#define MESSAGE_CONFIRMATION_TIMEOUT_MS      100
#define TEMP_RESOLUTION 12
#define DS18B20_MAX_CONVERSION_TIME_MS 750

//#############################
//       Startup Settings
//#############################
#define START_POWERED		 true

//#############################
//       Debug Defines
//#############################
#define DEBUG_POWERDOWN
#define DEBUG_RAM
#define DEBUG_STARTUP //Passes
#define DEBUG_PROTOCOL
#define DEBUG_ACCEL
#define DEBUG_TEMP
#define DEBUG_RTC
//#define DEBUG_FAKE_SLEEP
#define DEBUG_SLEEP
#define DEBUG_LOGFILE
#define DEBUG_TIMERS
ArduinoOutStream cout(Serial);  // Serial print stream
*/


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
#define TEMP_UPDATE_TIMER 'T'
#define TEMP_POLL_TIMER   'P'
#define RTC_TIMER         'R'
#define MSTIMER2_DELTA                       2	      // should be less than smallest timeout interval
#define TEMP_UPDATE_INTERVAL_MS              30000    //Once per minute
#define RTC_UPDATE_INTERVAL_MS               36000    //Once per hour

#define NUM_NAP_RELATED_TIMERS   2 //must be <= NUM_TIMERS
#define NUM_TIMERS               3

volatile bool timerUpdateSourceIsWDT;

Timer updateTempsTimer(TEMP_UPDATE_TIMER, TEMP_UPDATE_INTERVAL_MS);
Timer pollTempsTimer(TEMP_POLL_TIMER, DS18B20_MAX_CONVERSION_TIME_MS);
Timer updateRTCTimer(RTC_TIMER, RTC_UPDATE_INTERVAL_MS);

//Timers that should not be used in determining nap times must be placed at the end of the array
Timer* const timers[NUM_TIMERS]={ &updateTempsTimer,
    &pollTempsTimer, &updateRTCTimer};

extern "C" volatile uint32_t timer0_millis;

#pragma mark -
#pragma mark Globals

//#############################
//             Globals
//#############################

WatchdogSleeper WDT;

RTC_DS1337 RTC;                 //Real Time Clock object

OneWire oneWire(ONE_WIRE_BUS);  // Instantiate a oneWire instance

DallasTemperature dallasSensors(&oneWire);  // Instantiate Dallas Temp sensors on oneWire

bool messageResponseExpected=false;
uint32_t msgID=0;

bool powered=false;
volatile bool asleep=false;

uint8_t systemStatus=0;   //x,newheader,header,accel,temps,RTC,sd,logfile
#define SYS_NOMINAL     0x3F
#define SYS_FILE_OK     0x01
#define SYS_SD_OK       0x02
#define SYS_RTC_OK      0x04
#define SYS_TEMP_OK     0x08
#define SYS_ADXL_OK     0x10
#define SYS_HEADER_OK   0x20
#define SYS_HEADER_NEW  0x40


float temps[N_TEMP_SENSORS];

bool updateRTCPending=false;

uint32_t resetTime;

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
    
    // Restart WDT if in autorestart mode else disable the WD interrupt
    if (WDT._autorestart) WDT.on(WDT._prescaler);
    else _WD_CONTROL_REG &= (~(1<<WDIE));
    
    // Self-calibrate if required
    if (WDT._cycles2ms > 1)
        if (timer0_millis > WDT._cycles2ms)
            WDT._cycles2ms=(timer0_millis - WDT._cycles2ms)/
            WDT.__Prescaler2Cycles(WDT_CALIBRATION_PRESCALE_V);
    
    // Do the callback, if enabled
    if (WDT._WDT_Callback_Enabled) WDT.__WDT_Callback_Func();
    
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
// Timer updated callback function
//=============================
void timerUpdater(void) {
    uint32_t increment;
    if (timerUpdateSourceIsWDT)
        increment=WDT.getTimerCallbackIntervalMS();
    else
        increment=MSTIMER2_DELTA;
    //Serial.print("#TimersTick: ");Serial.println(increment);
    for (int i=0; i<NUM_TIMERS; i++)
        timers[i]->increment(increment);
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
    
    // Disable Timer1 
    power_timer1_disable();
    
    // Disable Timer2
    power_timer2_disable(); //Needed by MsTimer2, but we turn it on and off
    
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
    updateTempsTimer.start();
    updateRTCTimer.start();
    
    // Initialize the temp sensors
    #ifdef DEBUG_STARTUP
        Serial.print(F("#Init temp..."));
    #endif
    dallasSensors.begin();
    dallasSensors.setResolution(TEMP_RESOLUTION);
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
    
    // Initialize power mode
    powered=START_POWERED;
    if (!powered) setTimerUpdateSourceToWDT();
    else setTimerUpdateSourceToMsTimer2();
    
    #ifdef DEBUG_STARTUP | DEBUG_RAM
        cout<<pstr("#Free RAM:")<<FreeRam()<<endl;
    #endif
    
    Serial.print(F("#Startup:"));Serial.println(systemStatus,HEX);
    
}


void errorLoop(void) {
    while(1) {
        //cout<<pstr("Fatal Error: ");
        Serial.println(F("Fatal Error: "));
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
    
    // Serial Monitoring
    if (messageResponseExpected && Serial.available()==0) {
        delay(MESSAGE_CONFIRMATION_TIMEOUT_MS);
    }
    
    if(messageResponseExpected && Serial.available()==0) {
        #ifdef DEBUG_PROTOCOL
            Serial.print(F("#T/O mID "));Serial.println(msgID);
        #endif
        bufferRewind();
        powerDown();
    }
    else if(messageResponseExpected && Serial.available()) {
        #ifdef DEBUG_PROTOCOL
            uint8_t temp=Serial.peek();
            Serial.print(F("#Bytes Avail:"));Serial.println(Serial.available());
            Serial.print(F("#Byte In:"));Serial.println(temp);
            Serial.print(F("#Conf mID "));Serial.println(msgID);
            Serial.print(F("#Time: "));Serial.println(millis());
        #endif
        
        messageResponseExpected=false;
        uint8_t byteIn=Serial.read();
        
        if (byteIn=='#') {
            //Message sucessfully sent, may also have a time update pending
            if (Serial.peek()=='t' && updateRTCPending)
                byteIn=Serial.read();
        }
        
        if (byteIn=='t') {
            updateRTCTimer.reset();
            updateRTCTimer.start();
            updateRTCPending=false;
            setRTCFromSerial();
        }
        
        bufferRewind(); //Just assume the message was confirmed
        
    }
    
    // Reset millis()
    // Goal is to keep millis in sync with the time of day
    if (needToResetMillis()) {
        resetMillis();
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
    
    
    /////////////////////////////////////////////
    // bufferPut calls should go after here ?? //
    /////////////////////////////////////////////
    
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
    
    /////////////////////////////////////////////
    // bufferPut calls should go prior to here //
    /////////////////////////////////////////////
    
    
    // Save or send the log data
    if(!bufferIsEmpty()) {
        
        uint32_t unixtime=RTC.now().unixtime();
        uint32_t millisTime=millis();
        
        bufferPut(&unixtime,4);
        bufferPut(&millisTime,4);
        sendData();
        
    }
    
    
    // RTC monitoring
    // updateRTCPending prevents spamming if the host never sends good values
    if (updateRTCTimer.expired() && !updateRTCPending && powered) {
        requestTime();
    }
    
    
    // Determine how much time we can sleep
    if (!messageResponseExpected) {
        //Find min value of running timers
        uint32_t availableNaptimeMS=determineTimeUntilNextNapTimerExpires();
        //if mstimer fired then the min is too large by MSTIMER2_DELTA
        // if wdtimer fired it is to large by WDT.getTimer0Increment
        #ifdef DEBUG_SLEEP
            cout<<"#Sleep time avail: "<<availableNaptimeMS<<" ms.\n";
        #endif
        goSleep(availableNaptimeMS, SLEEP_HARD);
    }

    #ifdef DEBUG_TIMERS
        for (char i=0; i<NUM_TIMERS; i++) {
            cout<<pstr("#Timer ")<<timers[i]->getID();
            cout<<":"<<timers[i]->value()<<endl;
        }
    #endif
}


//=============================
// determineTimeUntilNextNapTimerExpires -- Do what it says
//=============================
uint32_t determineTimeUntilNextNapTimerExpires(void) {
    uint32_t timeLeft;
    if (timers[0]->running() || timers[0]->expired())
        timeLeft=timers[0]->value();
    else
        timeLeft=MAX_UINT32;

    for (uint8_t i=1; i<NUM_NAP_RELATED_TIMERS; i++) {
        if ((timers[i]->running() || timers[i]->expired()) &&
            timers[i]->value() < timeLeft)
            timeLeft=timers[i]->value();
    }
    
    //Clock is at //8000 cycles/ms no way that function execution affects
    // return value
    return timeLeft;
}


//=============================
// goSleep - given a duration and mode,
//  it sleeps for that long
//=============================
void goSleep(uint32_t duration_ms, SleepMode mode) {
    
    #ifdef DEBUG_SLEEP
        cout<<"#Sleep "<<mode<<" "<<duration_ms<<" ms.\n";
        Serial.flush();
        uint32_t timepoint; timepoint=millis();
    #endif
    
    if (duration_ms==0)
        return;
        
    WDT.configureSleep(mode);
    asleep=true;
    #ifdef DEBUG_FAKE_SLEEP
    cout<<"#Feigning sleep\n";
    WDT.fakeSleep(duration_ms);
    #else
    if (duration_ms < WDT.minimumSleepTime_ms()) {
        #ifdef DEBUG_SLEEP
            cout<<"#Feigning sleep\n";
        #endif
        WDT.fakeSleep(duration_ms);
        duration_ms=0;
    }
    else {
        //Make sure we don't put gibberish on the line
        Serial.flush();
        
        if (powered) {
            /*
            MsTimer2::stop();
            power_timer2_disable();
            
            WDT.enableCallback();
            */
            cli();
            setTimerUpdateSourceToWDT();
            sei();
            
            duration_ms=WDT.sleep(duration_ms);
            
            cli();
            if (WDT.running()) WDT.queueCallbackSwitchToMsTimer2();
            else setTimerUpdateSourceToMsTimer2();
            sei();
        }
        else{
            duration_ms=WDT.sleep(duration_ms);
            
            WDT.enableAutorestart(0);
            if (!WDT.running()) 
                WDT.on(0);
        }
    }
    #endif
    asleep=false;
    
    #ifdef DEBUG_SLEEP
        if (duration_ms < 0)
            cout<<"#Overslept: "<<millis()-timepoint-duration_ms<<" ms.\n";
        else if (duration_ms >1)
            cout<<"#Underslept: "<<duration_ms<<" ms.\n";
    #endif
}



bool needToResetMillis() {
    DateTime now=RTC.now();
    if ( (now.unixtime() % 86400 == 0) && resetTime!=now.unixtime()){
        resetTime=now.unixtime();
        return true;
    }
    else
        return false;
}

//=============================
// powerDown - Sets timer update source to
//  WDT, starts poll for power timer,
//  clears RTC update pending status
//  sets powered to false
//=============================
void powerDown(void) {
    if (powered) {
        #ifdef DEBUG_PROTOCOL | DEBUG_SLEEP | DEBUG_POWERDOWN
            cout<<pstr("#PD\n");
        #endif
        powered=false;
        setTimerUpdateSourceToWDT();
        messageResponseExpected=false;
        updateRTCPending=false;
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
        Serial.print((uint16_t)bufferGetRecordSize());
        Serial.print(F(" at "));
        Serial.println(millis());
    #endif
    Serial.write('L');
    Serial.write(bufferGetRecordPtr(), bufferGetRecordSize());
    messageResponseExpected=true;
}


void requestTime(void) {
    msgID++;
    #ifdef DEBUG_PROTOCOL
        Serial.print(F("#Send mID "));
        Serial.print(msgID);
        Serial.print(F(", t"));
        Serial.print(F(" at "));
        Serial.println(millis());
    #endif
    Serial.write('t');
    updateRTCPending=true;
    messageResponseExpected=true;
}


//=============================
// setRTCFromSerial - Attemps to grab
// 4 bytes from serial, parse as
// uint32_t
// and use to set the RTC time
// returns true if RTC time was sucessfully set
//=============================
bool setRTCFromSerial() {
    uint32_t unixtime=0;
    
    while(!Serial.available());
    
    #ifdef DEBUG_RTC
        cout<<pstr("#Avail:")<<(uint16_t)Serial.available()<<endl;
    #endif
    
    uint8_t i=0;
    while(Serial.available() && i<4) {
        unixtime |=((uint32_t)Serial.read())<<(8*(3-i++));
    }
    
    DateTime now(unixtime);
    
    #ifdef DEBUG_RTC
        cout<<pstr("#Total in:")<<(uint16_t)i<<endl;
        cout<<pstr("#Times:");Serial.println(unixtime,HEX);//cout<<" "<<now<<endl;
    #endif
    
    if (now.year()>2010 && now.year()<2030) {
        #ifdef DEBUG_RTC
            cout<<pstr("#RTC set\n");
        #endif
        RTC.adjust(now);
        return true;
    }
    else {
        #ifdef DEBUG_RTC
            cout<<pstr("#Bad data.\n");
        #endif
        return false;
    }
    
}


//=============================
// setTimerUpdateSourceToWDT
//  does as named, WDT has
//  16ms minimum time slice
//=============================
void setTimerUpdateSourceToWDT(void) {
    MsTimer2::stop();
    power_timer2_disable();
    timerUpdateSourceIsWDT=true; //is atomic
    WDT.enableAutorestart();
    WDT.on(0); //15ms interval
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
    timerUpdateSourceIsWDT=false; //is atomic
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

