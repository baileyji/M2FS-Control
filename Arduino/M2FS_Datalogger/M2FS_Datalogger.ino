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
#define N_TEMP_SENSORS           3
#define ID "v0.5"
#define ID_SIZE 4
#define LOGFILE_DATA_START (ID_SIZE + 13)  //Header size
#define MESSAGE_CONFIRMATION_TIMEOUT_MS      100
#define TEMP_RESOLUTION 12
#define DS18B20_MAX_CONVERSION_TIME_MS 750
#define MAX_LOGFILE_SIZE_BYTES   0x38400000   //~900MB

//#############################
//       Startup Settings
//#############################
#define START_POWERED		 true

//#############################
//       Debug Defines
//#############################
#define DEBUG_POWERDOWN
//#define DEBUG_RAM
//#define DEBUG_STARTUP //Passes
//#define DEBUG_PROTOCOL
//#define DEBUG_ACCEL
//#define DEBUG_TEMP
//#define DEBUG_RTC
//#define DEBUG_FAKE_SLEEP
//#define DEBUG_SLEEP
//#define DEBUG_LOGFILE
//#define DEBUG_TIMERS
//#define DEBUG_BUFFER
//ArduinoOutStream cout(Serial);  // Serial print stream



//#############################
//             Pins
//#############################
#define SD_CS             10
#define ACCELEROMETER_CS  9
#define ONE_WIRE_BUS      2  // Data wire is plugged into pin 2 on the Arduino
#define BATTERY_PIN       5
#define ACCELEROMETER_INTERRUPT 1       //1=> pin 3, 0=> pin 2
#define ACCELEROMETER_INTERRUPT_PIN 3
#define EJECT_PIN         4

#pragma mark -
#pragma mark Timers

//#############################
//             Timers
//#############################
#define TEMP_UPDATE_TIMER 'T'
#define LOG_TIMER         'L'
#define TEMP_POLL_TIMER   'P'
#define RTC_TIMER         'R'
#define MSTIMER2_DELTA                       2	        // 1<=x< min(interval)
#define TEMP_UPDATE_INTERVAL_MS              60000      //Once per minute
#define RTC_UPDATE_INTERVAL_MS               3600000    //Once per hour
#define LOG_SYNC_TIME_INTERVAL_MS            300000     //Once every five minutes

#define NUM_NAP_RELATED_TIMERS   3                      //must be <= NUM_TIMERS
#define NUM_TIMERS               4

volatile bool timerUpdateSourceIsWDT;

Timer logSyncTimer(LOG_TIMER, LOG_SYNC_TIME_INTERVAL_MS);
Timer updateTempsTimer(TEMP_UPDATE_TIMER, TEMP_UPDATE_INTERVAL_MS);
Timer pollTempsTimer(TEMP_POLL_TIMER, DS18B20_MAX_CONVERSION_TIME_MS);
Timer updateRTCTimer(RTC_TIMER, RTC_UPDATE_INTERVAL_MS);

//Timers that should not be used in determining nap times must be placed at the end of the array
Timer* const timers[NUM_TIMERS]={&logSyncTimer, &updateTempsTimer,
                                 &pollTempsTimer, &updateRTCTimer};

#pragma mark -
#pragma mark Globals
//#############################
//             Globals
//#############################

WatchdogSleeper WDT;

RTC_DS1337 RTC;                 //Real Time Clock object

SdFat SD;                       //SD card filesystem object

SdFile logfile;                 // file for logging
uint32_t writePos, readPos;
uint32_t Logfile_End;

OneWire oneWire(ONE_WIRE_BUS);  // Instantiate a oneWire instance

DallasTemperature dallasSensors(&oneWire);  // Instantiate Dallas Temp sensors on oneWire

bool messageResponseExpected=false;
uint32_t msgID=0;

bool powered=false;

uint8_t systemStatus=0;   //x,newheader,header,accel,temps,RTC,sd,logfile
#define SYS_NOMINAL     0x3F
#define SYS_FILE_OK     0x01
#define SYS_SD_OK       0x02
#define SYS_RTC_OK      0x04
#define SYS_TEMP_OK     0x08
#define SYS_ADXL_OK     0x10
#define SYS_HEADER_OK   0x20
#define SYS_HEADER_NEW  0x40


int16_t accel[3];
//0=active, 1 presently inactive, but active data still in fifo
// 2=inactve and only inactive data in fifo
volatile uint8_t inactive=0;
volatile uint8_t ADXLintSource = 0;
volatile bool retrieve_fifo_accels=false;
volatile uint8_t n_in_fifo=0;


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
extern "C" volatile uint32_t timer0_millis;
extern "C" volatile uint32_t timer0_overflow_count;
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



#ifdef DEBUG_ACCEL
typedef struct accel_dbg_nfo {
    uint8_t interrupts;
    uint8_t map;
    uint8_t inactive;
    uint8_t intSource;
    bool rfa;
    uint8_t n_fifo;
    bool aiPin;
} accel_dbg_nfo;
volatile accel_dbg_nfo accelInterruptDbgNfo;
volatile bool printAccelInterruptDbgNfo;
#endif
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
    
    uint8_t interrupts;
    
    ADXL345.readRegister(ADXL_INT_SOURCE, 1, (char*) &ADXLintSource);
    
    if (ADXLintSource & (ADXL_INT_ACTIVITY | ADXL_INT_FREEFALL) ) {
        
        //Add watermark to enabled interrupts
        interrupts = ADXL_INT_FREEFALL | ADXL_INT_ACTIVITY |
                     ADXL_INT_INACTIVITY | ADXL_INT_WATERMARK;
        ADXL345.writeRegister(ADXL_INT_ENABLE, interrupts);

        //Presently Active
        WDT.cancelSleep();
        inactive=0; // will grab data when fifo is full
    }
    
    if (ADXLintSource & ADXL_INT_WATERMARK) {
        ADXL345.readRegister(ADXL_FIFO_STATUS,1, (char*) &n_in_fifo);
        retrieve_fifo_accels=true;
        //Cancel sleep
        WDT.cancelSleep();
        if (inactive==1) {
            //Turn off watermark interrupt
            interrupts = ADXL_INT_FREEFALL | ADXL_INT_ACTIVITY |
                         ADXL_INT_INACTIVITY;
            ADXL345.writeRegister(ADXL_INT_ENABLE, interrupts);
            inactive=2;
        }
    }
    
    if (ADXLintSource & ADXL_INT_INACTIVITY) {
        inactive=1;
        //Turn on activity and freefall interrupts, leave watermark enabled, so
        //we get rest of data and turn off inactivity
        //interrupts = ADXL_INT_FREEFALL | ADXL_INT_ACTIVITY |
        //             ADXL_INT_WATERMARK | ADXL_INT_INACTIVITY;
        //ADXL345.writeRegister(ADXL_INT_ENABLE, interrupts);
    }
    
    
    
    #ifdef DEBUG_ACCEL
        printAccelInterruptDbgNfo=true;
        accelInterruptDbgNfo.rfa=retrieve_fifo_accels;
        accelInterruptDbgNfo.intSource=ADXLintSource;
        accelInterruptDbgNfo.inactive=inactive;
        
        ADXL345.readRegister(ADXL_INT_ENABLE, 1, (char*) &interrupts);
        accelInterruptDbgNfo.interrupts=interrupts;
        
        uint8_t map;
        ADXL345.readRegister(ADXL_INT_MAP, 1, (char*) &map);
        accelInterruptDbgNfo.map=map;
        
        accelInterruptDbgNfo.aiPin=digitalRead(ACCELEROMETER_INTERRUPT_PIN);
        
        ADXL345.readRegister(ADXL_FIFO_STATUS,1, (char*) &n_in_fifo);
        accelInterruptDbgNfo.n_fifo=n_in_fifo;
        
       Serial.println(F("#Hit"));
    #endif
    
}




//=============================
// Callback for file timestamps
//=============================
void dateTime(uint16_t* date, uint16_t* time) {
    DateTime now =RTC.now();// DateTime(1999,1,1,0,0,0);//
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
    updateRTCTimer.increment(updateRTCTimer.duration());
    
    // Initialize Accelerometer
    #ifdef DEBUG_STARTUP
        Serial.print(F("#Init ADXL..."));
    #endif
    attachInterrupt(ACCELEROMETER_INTERRUPT, accelerometerISR, FALLING);
    ADXL345.init(ACCELEROMETER_CS);
    ADXL345.readRegister(ADXL_INT_SOURCE, 1, (char*) &ADXLintSource);
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
        resetMillis();
        
        #ifdef DEBUG_STARTUP
            Serial.println(F("done"));
        #endif
    }
    
    // Initialize SD card
    #ifdef DEBUG_STARTUP
        cout<<pstr("#Init SD...\n");
    #endif

    char name[] = "LOG.BIN";

    if (!SD.init(SPI_FULL_SPEED, SD_CS)) {
        Serial.print(F("E"));
        SD.initErrorPrint();
        errorLoop();
    }
    else {
        systemStatus|=SYS_SD_OK;
    }
    
    if (SD.exists(name)) {
        //Try to read header info and resume operation
        logfile.open(name, O_RDWR);
        if (!logfile.isOpen()) {
            Serial.println(F("#file.reopen"));
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
        if (header_size != LOGFILE_DATA_START ||
            Logfile_End > MAX_LOGFILE_SIZE_BYTES ||
            writePos > Logfile_End||
            readPos > Logfile_End ) {
            Serial.println(F("#Bad Header"));
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
            Serial.println(F("#file.open"));
            errorLoop();
        }
        systemStatus|=SYS_FILE_OK;
        
        readPos=writePos=Logfile_End=LOGFILE_DATA_START;
        
        logfile.write((uint8_t) LOGFILE_DATA_START); //Header Size
        logfile.write(ID,ID_SIZE);		 //File Info
        logfile.write((void*)&writePos,sizeof(writePos));
        logfile.write((void*)&readPos,sizeof(readPos));
        logfile.write((void*)&Logfile_End,sizeof(Logfile_End));
        syncLogfile();
        
        systemStatus|=SYS_HEADER_NEW;
    }
    #ifdef DEBUG_STARTUP
        cout<<pstr("#done. File:")<<name<<endl;
    #endif

    
    
    // Initialize power mode
    powered=START_POWERED;
    if (powered) setTimerUpdateSourceToMsTimer2();
    else setTimerUpdateSourceToWDT();
    
    #ifdef DEBUG_RAM
        Serial.print(F("#Free RAM:"));Serial.println(FreeRam());
    #endif
    
    Serial.print(F("#Startup:"));Serial.println(systemStatus,HEX);
    
}


void errorLoop(void) {
    while(1) {
        //cout<<pstr("Fatal Error: ");
        Serial.print(F("EFatal Error: "));
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

    bool dataIsFromLogfile=false;
    
    // Serial Monitoring
    if (messageResponseExpected && Serial.available()==0) {
        delay(MESSAGE_CONFIRMATION_TIMEOUT_MS);
    }
    
    if(messageResponseExpected && Serial.available()==0) {
        #if defined(DEBUG_PROTOCOL) || defined(DEBUG_POWERDOWN)
            Serial.print(F("#T/O mID "));Serial.println(msgID);
        #endif
        if (!bufferIsEmpty() ) {
            if (dataIsFromLogfile) ungetLogDataFromFile();
            else logData();
        }
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
        
    }
    
    //Clear the buffer
    bufferRewind();
    
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
    // bufferPut calls should go after here    //
    /////////////////////////////////////////////
    
    // Temperature Monitoring
    if (pollTempsTimer.expired()) {
        #ifdef DEBUG_TEMP
            cout<<"#Poll T\n";
        #endif
        for (unsigned char i=0; i<N_TEMP_SENSORS; i++) {
            temps[i]=dallasSensors.getTempCByIndex(i);
            //NB Returns -127 if a temp sensor is disconnected
            #ifdef DEBUG_TEMP
                cout<<"#T["<<(uint16_t)i<<"]="<<temps[i]<<endl;
            #endif
        }
        bufferPut(temps, N_TEMP_SENSORS*sizeof(float));
        pollTempsTimer.reset();
    }
    
    
    // Acceleration Monitoring
    if (retrieve_fifo_accels) {
        
        if (n_in_fifo < 32) {
            #ifdef DEBUG_ACCEL
                cout<<pstr("#Delay for FIFO\n");
            #endif
            delay(40*(32-n_in_fifo));  //40 is for sample rate of 25Hz
            ADXL345.readRegister(ADXL_FIFO_STATUS, 1, (char*) &n_in_fifo );
        }
        
        #ifdef DEBUG_ACCEL
            Serial.println(F("#Pre-retrieval"));
            printAccelDebugMsg();
        #endif
        
        if (n_in_fifo>32) n_in_fifo=32; //There is an error fifo is only 32 deep
        
        for (uint8_t i=0; i<n_in_fifo;i++) {
            ADXL345.getRawAccelerations(accel);
            bufferPut(accel,6);
        }
        retrieve_fifo_accels=false;
        
        #ifdef DEBUG_ACCEL
            Serial.println(F("#Post-retrieval"));
        #endif
        
    }
    #ifdef DEBUG_ACCEL
        else {
            Serial.println(F("#No retrieval"));
        }
        ADXL345.readRegister(ADXL_INT_SOURCE, 1, (char*) &ADXLintSource);
        printAccelDebugMsg();
        if (!digitalRead(ACCELEROMETER_INTERRUPT_PIN))
            cout<<pstr("# Accel int. active: BAD\n");
    #endif
    
    if (!bufferIsEmpty()) {   // Add a timestamp
        uint32_t timestamp=RTC.now().unixtime();
        bufferPut(&timestamp,4);
        timestamp=millis();
        bufferPut(&timestamp,4);
    }
    /////////////////////////////////////////////
    // bufferPut calls should go prior to here //
    /////////////////////////////////////////////
    
    
    // Upload old data
    if (powered && bufferIsEmpty()) {
        #ifdef DEBUG_LOGFILE
            cout<<"#GLDfF\n";
            cout<<pstr("# buffer: ")<<(unsigned int) bufferSpaceRemaining()<<" "<<(unsigned int)bufferPos()<<endl;
        #endif
        dataIsFromLogfile=getLogDataFromFile();
        #ifdef DEBUG_LOGFILE
            cout<<pstr("# buffer: ")<<(unsigned int) bufferSpaceRemaining()<<" "<<(unsigned int)bufferPos()<<endl;
        #endif
    }
    
    // Save or send the log data
    if (powered) sendData();
    else         logData();
    
    // Sync the logfile
    //   NB timer is started by logData()
    if (logSyncTimer.expired()) {
        syncLogfile();
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
    
    
#ifdef DEBUG_ACCEL
    if(printAccelInterruptDbgNfo) {
        uint8_t interrupts, n_fifo, map, intSource, inact;
        bool aiPin, rfa;
        cli();
        interrupts=accelInterruptDbgNfo.interrupts;
        n_fifo=accelInterruptDbgNfo.n_fifo;
        map=accelInterruptDbgNfo.map;
        intSource=accelInterruptDbgNfo.intSource;
        aiPin=accelInterruptDbgNfo.aiPin;
        inact=accelInterruptDbgNfo.inactive;
        sei();
        
        Serial.println(F("#Hit info"));
        cout<<pstr("# store=");
        if (accelInterruptDbgNfo.rfa) cout<<pstr("t");
        else cout<<pstr("f");
        cout<<" ";
        cout<<pstr("# inactive=")<<(uint16_t) accelInterruptDbgNfo.inactive<<" ";
        _printAccelDebugMsg(interrupts, n_fifo, map, intSource, aiPin);
        printAccelInterruptDbgNfo=false;
    }
    
#endif
    
}


#ifdef DEBUG_ACCEL
void printAccelDebugMsg(void) {
    uint8_t interrupts, n_fifo, map;
    bool aiPin;
    ADXL345.readRegister(ADXL_INT_ENABLE, 1, (char*) &interrupts);
    ADXL345.readRegister(ADXL_FIFO_STATUS,1, (char*) &n_fifo);
    ADXL345.readRegister(ADXL_INT_MAP,1, (char*) &map);
    aiPin=digitalRead(ACCELEROMETER_INTERRUPT_PIN);
    _printAccelDebugMsg(interrupts, n_fifo, map, ADXLintSource, aiPin);
}

void _printAccelDebugMsg(uint8_t interrupts, uint8_t n_fifo,
                         uint8_t map, uint8_t intSource, bool aiPin) {
    cout<<pstr("# fifo=")<<(uint16_t)n_fifo;cout<<" ";
    cout<<pstr("# en="); printIntMeanings(interrupts);cout<<" ";
    cout<<pstr("# src="); printIntMeanings(intSource);cout<<" ";
    cout<<pstr("# map="); printIntMeanings(map);cout<<" ";
    cout<<pstr("# pin=");
    if (!aiPin) cout<<pstr("0");
    else cout<<pstr("1");
    cout<<endl;
}

void printIntMeanings(uint8_t intbyte) {
    if (intbyte & ADXL_INT_DATAREADY)	  cout<<pstr("data ready, ");
    if (intbyte & ADXL_INT_ACTIVITY)	  cout<<pstr("activity, ");
    if (intbyte & ADXL_INT_FREEFALL)	  cout<<pstr("freefall, ");
    if (intbyte & ADXL_INT_INACTIVITY) cout<<pstr("inactivity, ");
    if (intbyte & ADXL_INT_OVERRUN)	  cout<<pstr("data dropped, ");
    if (intbyte & ADXL_INT_WATERMARK)  cout<<pstr("watermark, ");
}
#endif


//=======================================
// getLogDataFromFile() - Grabs the next logged line
//  from the logfile. Returns true if a line was
//  grabbed, false otherwise.
//  Requires buff.width() >= longest log message
//=======================================
bool getLogDataFromFile() {
    
    if (readPos!=writePos) {
        
        logfile.seekSet(readPos);
        uint8_t recordSize=logfile.read();
        if (recordSize != -1) {
            logfile.read(bufferWritePtr(), recordSize);
            bufferIncrementWritePtr(recordSize);
        }
        else {
            #ifdef DEBUG_LOGFILE
                cout<<pstr("#This can't happen.\n"); //Unless no data has been logged
            #endif
        }
        
        //If we've reached the end of file but not the write pointer
        if (logfile.peek()==-1 && logfile.curPosition()!=writePos)
            logfile.seekSet(LOGFILE_DATA_START);
        
        readPos=logfile.curPosition();
        
        //Update the file header
        logfile.seekSet(LOGFILE_DATA_START-2*sizeof(writePos));
        logfile.write((void*)&readPos, sizeof(readPos));
        
        return true;
        
    }
    
    return false; //We've reported all the logged data	
}


void ungetLogDataFromFile() {
    if (readPos == LOGFILE_DATA_START ) {
        //wrap around to end
        logfile.seekCur(Logfile_End-bufferGetRecordSize());
    }
    else {
        logfile.seekCur(-bufferGetRecordSize());	//rewind readPos
    }
    readPos=logfile.curPosition();
    
    //Update the file header
    logfile.seekSet(LOGFILE_DATA_START-2*sizeof(writePos));
    logfile.write((void*)&readPos,sizeof(readPos));
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
    
    //Check to see if writing requires looping around
    // buffer is not large enough to loop AND pass writePos
    // Forces cases:
    //-----read*?----write*--read*?--eof---maxsize----futurew*--LONGOVERFLOW
    //--read*?--futurew*----read*?----write*--read*?--eof--maxsize--LONGOVERFLOW
    // into case
    //write*----read*?---futurew*--------read*?------eof--maxsize--LONGOVERFLOW
    if (futurePos > MAX_LOGFILE_SIZE_BYTES || futurePos < writePos) {
        logfile.seekSet(LOGFILE_DATA_START);
        writePos=logfile.curPosition();
        futurePos=writePos+bufferPos();
    }
    
    //Possible cases:
    //-read*?--write*--read*?---futurew*-----read*?----eof--maxsize--LONGOVERFLOW
    
    //-read*--write*-----futurew*-------eof--maxsize--LONGOVERFLOW
    if ( writePos >= readPos) {
        
        #ifdef DEBUG_LOGFILE
            report_log_action(1);
        #endif
        
        logfile.seekSet(writePos);
        logfile.write(bufferGetRecordPtr(), bufferGetRecordSize());
        logSyncTimer.start();
        
        // Update the file write pointer and extents
        writePos=logfile.curPosition();
        Logfile_End=Logfile_End > writePos ? Logfile_End:writePos;
        
        // Update the file header
        logfile.seekSet(LOGFILE_DATA_START-3*sizeof(writePos));
        logfile.write((void*)&writePos,sizeof(writePos));
        logfile.seekCur(sizeof(readPos));//logfile.write((void*)&readPos,sizeof(readPos));
        logfile.write((void*)&Logfile_End,sizeof(Logfile_End));
        
    }
    //Possible cases:
    //---write*--read*?---futurew*-----read*?----eof--maxsize--LONGOVERFLOW
    
    
    //---write*-----futurew*-----read*----eof--maxsize--LONGOVERFLOW
    else if (futurePos<readPos) {
        
        #ifdef DEBUG_LOGFILE
            report_log_action(0);
        #endif
        
        logfile.seekSet(writePos);
        logfile.write(bufferGetRecordPtr(), bufferGetRecordSize());
        logSyncTimer.start();
        
        // Update write pointer
        writePos=logfile.curPosition();
        
        
        // Update the file header
        logfile.seekSet(LOGFILE_DATA_START-3*sizeof(writePos));
        logfile.write((void*)&writePos,sizeof(writePos));
        //logfile.write((void*)&readPos,sizeof(readPos));
        //logfile.write((void*)&Logfile_End,sizeof(Logfile_End));
    }
    //One possible case left, log is full
    //---write*--read*?---futurew*-------eof--maxsize--LONGOVERFLOW
    else {
        #ifdef DEBUG_LOGFILE
            cout<<pstr("#Logfile Full\n");
        #endif
        //log message is lost
    }
    
}

#ifdef DEBUG_LOGFILE
void report_log_action(uint8_t rpltwp){
    cout<<pstr("#Logging (rp");
    if (rpltwp) cout<<pstr("<=");
    else cout<<pstr(">");
    cout<<pstr("wp) ");
    cout<<(uint16_t)bufferGetRecordSize()<<pstr(" bytes at ")<<writePos<<endl;
}
#endif


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

void syncLogfile(void) {
    #ifdef DEBUG_LOGFILE
        Serial.println(F("#Logfile sync"));
    #endif
    logfile.sync();
    logSyncTimer.stop();
    logSyncTimer.reset();
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
    
    //Log the data so SD card powers down
    syncLogfile();
    
    WDT.configureSleep(mode);
    
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
    
    #ifdef DEBUG_SLEEP
        if (duration_ms < 0)
            cout<<"#Overslept: "<<millis()-timepoint-duration_ms<<" ms.\n";
        else if (duration_ms >1)
            cout<<"#Underslept: "<<duration_ms<<" ms.\n";
    #endif
}



//=============================
// powerDown - Sets timer update source to
//  WDT, starts poll for power timer,
//  clears RTC update pending status
//  sets powered to false
//=============================
void powerDown(void) {
    if (powered) {
        #if defined(DEBUG_PROTOCOL) || defined(DEBUG_SLEEP) || defined(DEBUG_POWERDOWN)
            Serial.println(F("#PD"));
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
        //Serial.print(F("#BuffRSize:"));
        //Serial.println((uint16_t)bufferGetRecordSize());
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
        cout<<pstr("#Times:");Serial.print(unixtime,HEX);cout<<" "<<now<<endl;
    #endif
    
    if (now.year()>2010 && now.year()<2030) {
        RTC.adjust(now);
        resetMillis();
        #ifdef DEBUG_RTC
            DateTime now=RTC.now();
            cout<<pstr("#RTC set:")<<now<<endl;
        #endif
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
// resetMillis - Resets the millis counter to the current point in the day
//=============================
void resetMillis() {
    uint8_t oldSREG;
    uint32_t new_timer0_millis;
    DateTime now=RTC.now();
    
    resetTime=now.unixtime();
    new_timer0_millis=(resetTime % 86400) * 1000;
    
    oldSREG = SREG;
    cli();
    timer0_millis = new_timer0_millis;
    SREG = oldSREG;
}


bool needToResetMillis() {
    DateTime now=RTC.now();
    return ( (now.unixtime() % 86400 == 0) && resetTime!=now.unixtime()) ;
}
