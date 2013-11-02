/*
 *  Timer.cpp
 *  
 *
 *  Created by John Bailey on 10/19/11.
 *  Copyright 2011 __MyCompanyName__. All rights reserved.
 *
 */

#include "Timer.h"
Timer::Timer(char ID, uint32_t duration) {
	_id=ID;
	set(duration);
}

Timer::~Timer(void) {
}


char Timer::getID(void) {
	return _id;
}

void Timer::reset(void) {
	uint8_t oldSREG = SREG;
	cli();
	_currentTime = _dur;
	SREG = oldSREG;
}


void Timer::set(uint32_t duration) {
	//We don't need interrupt guards as run==false prevents
	//	incrementing and run is written atomically.
	_run=false;
	_dur=duration;
	if (duration>0){
		_dir=-1;
		_currentTime=duration;
	}
	else {
		_dir=1;
		_currentTime=0;
	}
}


uint32_t Timer::value(void) {
	uint32_t temp;
	uint8_t oldSREG = SREG;
	cli();
	temp=_currentTime;
	SREG = oldSREG;
	return temp;
}

void Timer::increment(uint32_t delta) {
	if (_run) {
		if (_dir>0) {
			_currentTime+=delta;
		}
		else if (_currentTime > delta) {
			_currentTime-=delta;
		} else {
			_currentTime=0;
			_run=false;
		}
	}
  //Serial.print("ti:id,ct,d ");Serial.print(_currentTime);
  //Serial.print(", ");Serial.print(_id);
  //Serial.print(", ");Serial.println(delta,DEC);
}
