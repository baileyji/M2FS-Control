#ifndef __Timer_H__
#define __Timer_H__

#if ARDUINO < 100
#include <WProgram.h>
#else  // ARDUINO
#include <Arduino.h>
#endif  // ARDUINO
class Timer {
  
  private:
	volatile int8_t _dir;
	uint32_t _dur;
	volatile uint32_t _currentTime;
	volatile boolean _run;
	char _id;
	
  public:
	Timer(char ID, uint32_t duration);
	~Timer(void);     // destructor
	inline boolean running(void);
	inline boolean expired(void);
	inline void stop(void);
	inline void start(void);
	inline uint32_t duration(void);
	inline int8_t direction(void);
	void increment(uint32_t delta);
	void reset(void);
	void set(uint32_t duration);
	uint32_t value(void);
	char getID(void); 
};

inline void Timer::stop(void) {
  _run=false;
}

inline void Timer::start(void) {
  _run=true;
}

inline boolean Timer::running(void) {
  return _run;
}

inline uint32_t Timer::duration(void) {
  return _dur;
}

inline int8_t Timer::direction(void) {
  return _dir;
}

inline boolean Timer::expired(void) {
  return _dir<0 && value()==0;
}

#endif
