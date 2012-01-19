/*
 *  WatchdogSleeper.h
 *  
 *
 *  Created by John Bailey on 10/22/11.
 *  Copyright 2011 __MyCompanyName__. All rights reserved.
 *
 */

#ifndef __WatchdogSleeper_H__
#define __WatchdogSleeper_H__
#include <avr/sleep.h>
#include <avr/wdt.h>
#include <avr/power.h>
#include <avr/interrupt.h>
#include <WProgram.h>

// WDTON fuse must not be programmed
// WDE bit needs to be 0 in WDTCSR
// WDIE bit needs to be 1 in WDTCSR


#define WDT_CALIBRATION_PRESCALE_V 1
#define WDT_CALIBRATION_PRESCALE_V_MS_OVERESTIMATE 45
#define MAX_PRESCALER 9

extern "C" void WDT_vect(void);

typedef enum SleepMode { SLEEP_IDLE,  SLEEP_HARD } TokenType;

typedef void(*callback_t)(uint32_t);

class WatchdogSleeper {
  
private:

  
  volatile callback_t __WDT_Callback_Func;
  volatile boolean _WDT_Callback_Enabled;
  volatile boolean _WDT_ISR_Called;
  volatile boolean _update_timer0_millis;
  volatile uint32_t _WDT_timer0_millis_increment;
  volatile uint8_t _WDT_timer0_overflow_count_increment;
  volatile boolean _sleepCanceled;
	volatile boolean _autorestart;
  volatile uint8_t _prescaler;
	
	volatile boolean _switchUpdateSourceToMsTimer2Queued;
  
  SleepMode _config;
  boolean _disable_BOD;

  volatile float _cycles2ms;
  



public:
  WatchdogSleeper(void);
  ~WatchdogSleeper(void);
  
  
  //============================
  // configureSleep - Select the 
  //	sleep configuration
  //============================
  inline void configureSleep(SleepMode mode){
    _config=mode;
  }
  int32_t sleep(uint32_t sleepDuration);
  //============================
  // cancelSleep - Cancel sleep
  //============================
  inline void cancelSleep() {
    _sleepCanceled=true;
  }
  inline boolean sleepCanceled() {
    return _sleepCanceled;
  }
  
  
  void registerCallback(callback_t func);
  boolean enableCallback(void);
  boolean disableCallback(void);
	
	inline void queueCallbackSwitchToMsTimer2(void) {
    _switchUpdateSourceToMsTimer2Queued=true;
  }
  
  
  void off(void);
  void on(uint8_t prescaler);
  //============================
  // enableAutorestart - Enable
  //	automatic restart of WDT
  // 
  //============================
  inline boolean running(void) {
    return _WD_CONTROL_REG & (1<<WDIE);
  }
  inline void enableAutorestart(void) {
    _prescaler=0;
    _autorestart=true;
  }
  inline void enableAutorestart(uint8_t prescaler) {
    _prescaler=(prescaler > MAX_PRESCALER)? MAX_PRESCALER:prescaler;
    _autorestart=true;
  }
  //============================
  // disableAutorestart - Disable
  //	automatic restart of WDT
  //============================
  inline void disableAutorestart() {
    _autorestart=false;
  }

  uint8_t readPrescaler(void);
  inline uint32_t getTimer0Increment(void) {
    return _WDT_timer0_millis_increment;
  }  
  uint32_t readPrescalerAsMS(void);
  
  
  void calibrate(void);
  inline float clockRatekHz(){
    return 1.0/_cycles2ms;
  }
  uint32_t WDTCycles2MS(uint32_t cycles);
  uint32_t MS2WDTCycles(uint32_t duration_ms);
  //============================
  // minimumSleepTime_ms - Return the 
  //	minimum sleep cycle time
  //  See datasheet pages 41 (BOD) and 28 (CKSEL)
  //  Note, 2ms assumes SUT of 16K clock + 0ms
  //============================
  inline uint8_t minimumSleepTime_ms(void) {
    return 16;//2 for powerup, but WDT's shortest period is 16ms
  }
  void fakeSleep(uint32_t sleepDuration_ms);
  
private:
  uint32_t __powerDown(uint32_t wdt_cycles);
  uint8_t __Cycles2Prescaler(uint32_t cycles);
  uint32_t __Prescaler2Cycles(uint8_t prescaler);
  friend void WDT_vect(void);

};

#endif
