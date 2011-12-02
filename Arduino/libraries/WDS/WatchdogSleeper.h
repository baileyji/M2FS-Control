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
	
	volatile boolean _switchUpdateSourceToMsTimer2Queued;
  
  SleepMode _config;
  boolean _disable_BOD;

  volatile float _cycles2ms;
  



public:
  WatchdogSleeper(void);
  ~WatchdogSleeper(void);
  
  void configureSleep(SleepMode mode);
  int32_t sleep(uint32_t sleepDuration);
  void cancelSleep(void);
  boolean sleepCanceled();
  void resetSleepCanceled(void);
  
  
  void registerCallback(callback_t func);
  boolean enableCallback(void);
  boolean disableCallback(void);
	
	void queueCallbackSwitchToMsTimer2(void);
  
  void off(void);
  void on(uint8_t prescaler);
  void enableAutorestart(void);
  void disableAutorestart(void);

  uint8_t readPrescaler(void);
  uint32_t getTimer0Increment(void);
  uint32_t readPrescalerAsMS(void);
  
  
  void calibrate(void);
  uint32_t WDTCycles2MS(uint32_t cycles);
  uint32_t MS2WDTCycles(uint32_t duration_ms);
  uint8_t minimumSleepTime_ms(void);
  void fakeSleep(uint32_t sleepDuration_ms);
  
private:
  uint32_t __powerDown(uint32_t wdt_cycles);
  uint8_t __Cycles2Prescaler(uint32_t cycles);
  uint32_t __Prescaler2Cycles(uint8_t prescaler);
  friend void WDT_vect(void);

};

#endif
