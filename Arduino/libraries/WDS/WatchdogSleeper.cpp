/*
 *  WatchdogSleeper.cpp
 *  
 *
 *  Created by John Bailey on 10/22/11.
 *  Copyright 2011 __MyCompanyName__. All rights reserved.
 *
 */

#include "WatchdogSleeper.h"

#define UINT32_MAX 0xFFFFFFFF
#define F_CPU_MHZ 8
//#define DEBUG_SLEEP

extern "C" volatile uint32_t timer0_millis;

WatchdogSleeper::WatchdogSleeper(void) {
  
  _WDT_ISR_Called=false;
  
  _sleepCanceled = false;
  _config=SLEEP_HARD;
  _disable_BOD=true;
  _prescaler=0;
  _sleepIsFake=false;
  
	_switchUpdateSourceToMsTimer2Queued=false;
	
  _cycles2ms=0.0078125;	//1/128

  _update_timer0_millis=false;
  _WDT_timer0_millis_increment=WDTCycles2MS(__Prescaler2Cycles(readPrescaler()));
  _WDT_timer0_overflow_count_increment=31; //?????????????;
  
  _WDT_Callback_Enabled=false;
  __WDT_Callback_Func=NULL;
	
}

WatchdogSleeper::~WatchdogSleeper(void) {
}  

// Calibrate watchdog timer with millis() timer(timer0)
void WatchdogSleeper::calibrate() {
	_cycles2ms=millis();
	if (_cycles2ms < 2 ) {
		delay(2);
		_cycles2ms=millis();
	}
	on(WDT_CALIBRATION_PRESCALE_V);
	delay(WDT_CALIBRATION_PRESCALE_V_MS_OVERESTIMATE);
}

uint32_t WatchdogSleeper::readPrescalerAsMS(void) {
  return WDTCycles2MS(__Prescaler2Cycles(readPrescaler()));
}



//Returns any overshoot in the power down time as negative, 
// undershoot is returned as positive 
// sleepDuration shall be no greater greater than max signed long
// disables WDT autorestart if enabled
// This may undersleep by up to 8 seconds: to wit
//	WDT running, go to sleep just before it expires, full
//	dureation of elapsed WDT accredited to sleep
int32_t WatchdogSleeper::sleep(uint32_t sleepDuration_ms) {
  
  uint8_t ADCSRA_save, prr_save, WDTps;
  uint32_t sleepCycles, sleptDuration_ms;

  //Store modules power states
  ADCSRA_save=ADCSRA; 
  prr_save=PRR;
  
  switch (_config) {
	case SLEEP_HARD:
	  ADCSRA &= ~(1<<ADEN);  // adc disable
//	  PRR = 0xEF;			 // modules off, this breaks things, need to review datasheet
	  set_sleep_mode(SLEEP_MODE_PWR_DOWN);
	  break;
	case SLEEP_IDLE:
	  set_sleep_mode(SLEEP_MODE_IDLE);
	  break;
	default:
	  break;
  }

  if (sleepDuration_ms < minimumSleepTime_ms()) {
    fakeSleep(sleepDuration_ms);
  }
  else {
    
    _sleepIsFake=false;
    
    //How many cycles shall we sleep
    sleepCycles=MS2WDTCycles(sleepDuration_ms);

    //Sleep
    uint32_t cyclesSlept=__powerDown(sleepCycles);
    
    //How long did we sleep
    sleptDuration_ms = WDTCycles2MS(cyclesSlept);
  }
  
  // Modules to former state
  ADCSRA &= ~(1<<ADEN);		// adc disable (just in case it was reenabled in an interrupt)
  PRR = prr_save;
  ADCSRA = ADCSRA_save;  
  
	
//  if (_sleepCanceled) Serial.println("#Sleep Canceled");
	
  return (int32_t) sleepDuration_ms - (int32_t) sleptDuration_ms;
}

void WatchdogSleeper::fakeSleep(uint32_t sleepDuration_ms) {
  uint8_t ADCSRA_save, prr_save, WDTps;
  uint32_t sleepCycles, sleptDuration_ms;
  
  //Store modules power states
  ADCSRA_save=ADCSRA; 
  prr_save=PRR;
  ADCSRA &= ~(1<<ADEN);

  _sleepCanceled=false;
  _sleepIsFake=true;
  while(sleepDuration_ms > 0 && !_sleepCanceled) {
    delay(FAKE_SLEEP_INTERVAL_MS);
    sleepDuration_ms--;
    if (_WDT_Callback_Enabled) __WDT_Callback_Func();
  }
  
  // Modules to former state
  ADCSRA &= ~(1<<ADEN);		// adc disable (just in case it was reenabled in an interrupt)
  PRR = prr_save;
  ADCSRA = ADCSRA_save;  
  
  
}


//============================
// __powerDown - Power down to the set mode
//	for wdt_cycles. Power down can be canceled 
//	by calling cancelSleep(). Returns the number 
//	of cycles slept in increments of the WDT interrupt.
//	If wdt_cycles is not divisible by 2048, the remainder will be unslept.
//  Other interrupts MUST not mess with the WDT while this is running.
//============================
inline uint32_t WatchdogSleeper::__powerDown(uint32_t wdt_cycles) {
  
  uint8_t prescaler;
  uint32_t cyclesRemaining=wdt_cycles;
  boolean alreadyRunning;
  
  _sleepCanceled=false;
  while(cyclesRemaining > 2047 && !_sleepCanceled) {
    
    
    // Enable the WDT with the computed prescale value
    prescaler=__Cycles2Prescaler(cyclesRemaining);
		
    cli();
    
    _autorestart=false;
    _WDT_ISR_Called=false;
    _update_timer0_millis=true;
		
    if (running()) {
      #ifdef DEBUG_SLEEP
        Serial.println("#Sleep remainder of WDT.");
      #endif
      alreadyRunning=true;
    }
    else {
      alreadyRunning=false;
      on(prescaler);
    }
    
    sleep_enable();
    if (_disable_BOD) {
      MCUCR |= (1<<BODS) | (1<<BODSE);
      MCUCR &= ~(1<<BODSE);  // must be done right before sleep
    }
    sei();
    sleep_cpu();
    sleep_disable();
    
    
    // If we awoke prematurely, idle
    if (!_sleepCanceled && !_WDT_ISR_Called && running()) {
      #ifdef DEBUG_SLEEP
        Serial.println("#Awoke prematurely");
      #endif
      while (!_sleepCanceled && !_WDT_ISR_Called);
    }
      
    if (_WDT_ISR_Called && !alreadyRunning) {
      uint32_t temp=__Prescaler2Cycles(prescaler);
      cyclesRemaining=(temp > cyclesRemaining) ? 0: cyclesRemaining-temp;
    }

  }
  #ifdef DEBUG_SLEEP
    if (_sleepCanceled) {
      Serial.println("#Sleeping Canceled");
    }
  #endif
  
  return wdt_cycles - cyclesRemaining;
  
}


/*
 so if we are sleeping with say an 8s WDT, then get an interrupt and cancel sleep .5s in
 we wake, WDT ISR not been called, so timers have not been updated
 we return (wdt is still running), do whatever needs doing,
 check if we can go back to sleep, we can so we do, resetting the WDT, and never accounting for the
 elapsed time
 
 to FIX:
	if told to sleep and WDT running, don't restart it, just start the sleep with it as is
  if powering up, don't switch timer update source until WDT expires 
		done. Timer, WatchdogSleeper, & MsTimer2 classes are somewhat interlinked in the fix.
		not clean. 
 
 NB Starting timers after starting the update source will get interesting after 
	if the update source has granularity >= timer duration
*/
 
//============================
// readPrescaler - Return the 
//	current value of the prescaler
//============================
uint8_t WatchdogSleeper::readPrescaler() {
  return ((_WD_CONTROL_REG & (1<<WDP3)) >> (WDP3-WDP2-1) ) |
  (_WD_CONTROL_REG & ((1<<WDP2) | (1<<WDP1) | (1<<WDP0)));
}



//============================
// __Cycles2Prescaler - Compute the
//  prescaler that gives the greatest
//	number of cycles ≤ the number 
//	requested
//============================
uint32_t WatchdogSleeper::__Prescaler2Cycles(uint8_t prescaler) {
  
  //Note: WDT cycles=2^(1+prescaler)*2^10
  return ((uint32_t)1)<<(11+prescaler);
  
}

//============================
// __Cycles2Prescaler - Compute the
//  prescaler that gives the greatest
//	number of cycles ≤ the number 
//	requested
//============================
uint8_t WatchdogSleeper::__Cycles2Prescaler(uint32_t cycles) {
  
  //Note: WDT cycles=2^(1+prescaler)*2^10
  uint8_t prescaler;
  
  prescaler=0;
  cycles=cycles>>11;
  while (cycles >= (1<<prescaler++));
  prescaler-=2;
  if (prescaler>MAX_PRESCALER)
    return MAX_PRESCALER;
  else
    return prescaler;
  
}

//============================
// MS2WDTCycles - Compute the number of
//	WDT cycles corresponding to
//	a given number of milliseconds
//============================
uint32_t WatchdogSleeper::MS2WDTCycles(uint32_t duration_ms){
  return (uint32_t) (((float)duration_ms)/_cycles2ms);
}



//============================
// WDTCycles2MS - Compute the number of
//	milliseconds corresponding to
//	a given number of WDT cycles
//============================
uint32_t WatchdogSleeper::WDTCycles2MS(uint32_t cycles){
  return (uint32_t) (((float) cycles)*_cycles2ms);
}

//============================
// on - Turn on the WDT with given 
// prescaler value
//============================
void WatchdogSleeper::on(uint8_t psVal) {
  _prescaler=psVal;
  // prepare timed sequence first
  uint8_t new_wdtcsr = ((((psVal & 0x08)>>3)<<WDP3) | 
						(psVal & 0x07)		   |
						(1<<WDIE) )			   & 
						~(1<<WDE)			   &
						~(1<<WDCE);		//_WD_CHANGE_BIT->WDCE
  uint8_t oldSREG = SREG;
  cli();
  wdt_reset();
  /* Clear WDRF in MCUSR */
  MCUSR &= ~(1<<WDRF);
  // start timed sequence
  _WD_CONTROL_REG |= (1<<WDCE) | (1<<WDE);
  // set new watchdog timeout value
  _WD_CONTROL_REG = new_wdtcsr;
  _WDT_timer0_millis_increment=WDTCycles2MS(__Prescaler2Cycles(readPrescaler()));
  SREG = oldSREG;
}

//============================
// off - Turn off the WDT
//============================
void WatchdogSleeper::off() {
  uint8_t oldSREG = SREG;
  cli();
  wdt_reset();
  /* Clear WDRF in MCUSR */
  MCUSR &= ~(1<<WDRF);

  /* Write logical one to _WD_CHANGE_BIT and WDE */
  /* Keep old prescaler setting to prevent unintentional time-out */
  _WD_CONTROL_REG |= (1<<WDCE) | (1<<WDE);
  /* Turn off WDT */
  _WD_CONTROL_REG = 0x00;
  SREG = oldSREG;
}


//============================
// registerCallback - Register a 
//	function to call from the WDT ISR
//	Callback must be subsequently
//	enabled with enableCallback.
//============================
void WatchdogSleeper::registerCallback(callback_t func) {
  _WDT_Callback_Enabled=false;
  __WDT_Callback_Func=func;
  
}

//============================
// enableCallback - Enables the callback
//	function if set. Returns true if 
//	callback enabled
//============================
boolean WatchdogSleeper::enableCallback(void) {
  if (__WDT_Callback_Func !=NULL) 
	_WDT_Callback_Enabled=true;
  return _WDT_Callback_Enabled;
}


//============================
// disableCallback - Disables the callback
//	function. Returns true.
//============================
boolean WatchdogSleeper::disableCallback(void) {
  _WDT_Callback_Enabled=false;
  return true;
}


