// AccelStepperInt.cpp
//
// Copyright (C) 2009 Mike McCauley
// $Id: AccelStepperInt.cpp,v 1.5 2012/01/28 22:45:25 mikem Exp mikem $
#include "AccelStepperInt.h"



//Modified interrupt to handle multiple motors

//Original Note from ATMEL
/*! \brief Timer/Counter1 Output Compare A Match Interrupt.
 *
 *  Timer/Counter1 Output Compare A Match Interrupt.
 *  Increments/decrements the position of the stepper motor
 *  exept after last position, when it stops.
 *  The \ref step_delay defines the period of this interrupt
 *  and controls the speed of the stepper motor.
 *  A new step delay is calculated to follow wanted speed profile
 *  on basis of accel/decel parameters.
 */





#pragma vector=TIMER1_COMPA_vect
__interrupt void multi_stepper_TIMER1_COMPA_interrupt( void )
{
	
	determine motor that are due for update
	
	each stepper has
	
	
  OCR1A = stepper.control.srd.step_delay;
	
  switch(stepper.control.srd.run_state) {
    case STOP:
      stepper.control.step_count = 0;
      stepper.control.rest = 0;
      // Stop Timer/Counter 1.
      TCCR1B &= ~((1<<CS12)|(1<<CS11)|(1<<CS10));
      stepper.control.running = FALSE;
      break;
			
    case ACCEL:
      stepper.drive.StepCounter(stepper.control.srd.dir);
      step_count++;
      srd.accel_count++;
      new_step_delay = srd.step_delay - (((2 * (long)srd.step_delay) + rest)/(4 * srd.accel_count + 1));
      rest = ((2 * (long)srd.step_delay)+rest)%(4 * srd.accel_count + 1);
      // Chech if we should start decelration.
      if(step_count >= srd.decel_start) {
        srd.accel_count = srd.decel_val;
        srd.run_state = DECEL;
      }
      // Chech if we hitted max speed.
      else if(new_step_delay <= srd.min_delay) {
        last_accel_delay = new_step_delay;
        new_step_delay = srd.min_delay;
        rest = 0;
        srd.run_state = RUN;
      }
      break;
			
    case RUN:
      sm_driver_StepCounter(srd.dir);
      step_count++;
      new_step_delay = srd.min_delay;
      // Chech if we should start decelration.
      if(step_count >= srd.decel_start) {
        srd.accel_count = srd.decel_val;
        // Start decelration with same delay as accel ended with.
        new_step_delay = last_accel_delay;
        srd.run_state = DECEL;
      }
      break;
			
    case DECEL:
      sm_driver_StepCounter(srd.dir);
      step_count++;
      srd.accel_count++;
      new_step_delay = srd.step_delay - (((2 * (long)srd.step_delay) + rest)/(4 * srd.accel_count + 1));
      rest = ((2 * (long)srd.step_delay)+rest)%(4 * srd.accel_count + 1);
      // Check if we at last step
      if(srd.accel_count >= 0){
        srd.run_state = STOP;
      }
      break;
  }
  srd.step_delay = new_step_delay;
}










// This is called:
//  after each step
//  after user changes:
//   maxSpeed
//   acceleration
//   target position (relative or absolute)
void AccelStepperInt::computeNextStepTime()
{
	/*KNOWN
	 _targetPosition
	 _currentPosition
	 _lastStepTime (may be undefined if starting from stop)
	 _speed
	 _maxSpeed
	 _dir
	 _acceleration
	 current time (e.g. micros())
	 
	 WANT
	 _nextStepTime
	 
	 CASES:
		stopped
	  moving toward goal
	  moving away from goal
	 
	*/
	
	int32_t distanceTo = _targetPos - _currentPos;
	
  if (distanceTo == 0 & _speed==0) 
		_halted=true; // We're there
	
	//Movement is needed
	else {
		
		//If starting from stop
		if (_halted)
		{
			_dir=(distanceTo <0) ? -1:1;
			
			//step next time run is called
			_profileStartTime=_nextStepTime=micros();
			
			//Determine the motion profile
			
			//If move is too short for constant V phase
			if (_accelDecelDist>distanceTo) {
				timeAcceletating=sqrt(distanceTo/acceleration)*1000000;
				timeConstV=0;
			}
			else {
				timeAcceletating=_maxSpeed/_acceleration*1000000;
				timeConstV=(distanceTo - _accelDecelDist)*1000000/_maxSpeed;
			}
			
		}
		//Not starting from stop
		else 
		{

			//Determine if we are headed in the correct direction
			bool headingRightWay=(_dir<0 && distanceTo < 0) || (_dir > 0 && distanceTo > 0) ;
			
			
			//If not headed in right way
			if (!headingRightWay) {

				//Decelerate
				_speed-=
				_nextStepTime=
				
				if (_speed==0)
				{
					//Switch directions
					_dir=-_dir;
					
					_speed+=
					_nextStepTime=
					
					//Start time for the new profile
					_profileStartTime=micros();
					
					//Determine the motion profile
					
					//If move is too short for constant V phase
					if (_accelDecelDist>distanceTo) {
						timeAcceletating=sqrt(distanceTo/acceleration)*1000000;
						timeConstV=0;
					}
					else {
						timeAcceletating=_maxSpeed/_acceleration*1000000;
						timeConstV=(distanceTo - _accelDecelDist)*1000000/_maxSpeed;
					}

				}
				
			}
			//Headed in right way
			else {
				
				//Compute elapsed time
				// NB Moves that take longer than ~71 minutes cant be 
				// tracked and will cause unspecified behavior 
				uint32_t time=micros();
				
				if (time<_profileStartTime) {
					elapsedTime=time+MAX_UINT32-_profileStartTime;
				}
				else {
					elapsedTime=time-_profileStartTime;
				}

				
				//In acceleration phase
				if (elapsedTime < timeAcceletating)
				{
					_speed+=
					_nextStepTime=
				}
				//In constant velocity phase
				else if (elapsedTime < timeAcceletating+timeConstV)
				{
					_speed=_speed;
					_nextStepTime=_lastStepTime + 1000000 / _speed;
				}
				//In decelleration phase
				else
				{
					_speed-=
					if (_speed>0)
					{
						_nextStepTime=
					}
				}
				
			} // headed right way
		} // not halted
	} //movement needed
}

_speed-=_acceleration*(_nextStepTime-_lastStepTime)/100000;
_nextStepTime = _lastStepTime + 1000000 / _speed;

void calcNextStepTimeAccel() {
	_speed-=_acceleration*(_nextStepTime-_lastStepTime)/100000;
	_nextStepTime = _lastStepTime + 1000000 / _speed;


_speed-=_acceleration*(_nextStepTime-_lastStepTime)/100000;
_nextStepTime = _lastStepTime + 1000000 / _speed;


a=_speed - _acceleration*(_nextStepTime-_lastStepTime);
_nextStepTime = _lastStepTime + 1000000 / (_speed - _acceleration*(_nextStepTime-_lastStepTime);;
																					 

_nextStepTime = (_speed + 2* _lastStepTime * _acceleration - 
								 sqrt(_speed^2-4000000*_acceleration))/2/_acceleration
																					 

boolean stepIsDue() {
	
	unsigned long time, nextStepTime;
	
	if (_speed==0) return false;
	// Gymnastics to detect wrapping of either the nextStepTime and/or the current time
  time = micros();
  nextStepTime = _lastStepTime + _stepInterval;
	return (
					( (nextStepTime >= _lastStepTime) && ( (time >= nextStepTime) || (time < _lastStepTime) ) )
					||
					( (nextStepTime <  _lastStepTime) && ( (time >= nextStepTime) && (time < _lastStepTime) ) )
					);
	
}
/*
 speed=0
 dist to go ~=0
 maxSpeed>0
 
 _dir= (_targetPos < _currentPos) ? -1:1;
 
 
 */



// Run the motor to implement speed and acceleration in order to proceed to the target position
// You must call this at least once per step, preferably in your main loop
// If the motor is in the desired position, the cost is very small
// returns true if we are still running to position
boolean AccelStepperInt::run()
{
    if (_targetPos == _currentPos) 
      return false;
    
    if (stepIfNeeded()) 
      computeNextStepTime();
  
    return true;
}



//NOT SURE IF THIS FUNCTION IS NEEDED
boolean AccelStepperInt::runSpeedToPosition()
{
  return _targetPos!=_currentPos ? runSpeed() : false;
}

//THIS CAN BE MADE MORE EFFICIENT BY USING A FUNCTION POINTER
// Subclasses can override
void AccelStepperInt::step(uint8_t step)
{
    switch (_pins)
    {
        case 0:
            step0();
            break;
        
        case 1:
            step1(step);
            break;
        
        case 2:
            step2(step);
            break;
          
        case 4:
            step4(step);
            break;  

        case 8:
            step8(step);
            break;  
    }
}


//Take a step if it is time
boolean AccelStepperInt::stepIfNeeded()
{
	
  if (stepIsDue())
  {
    if (_dir>0) _currentPos += 1;
    else _currentPos -= 1;
		
    step(_currentPos & 0x7); // Bottom 3 bits (same as mod 8, but works with + and - numbers)
    _lastStepTime = micros();
    return true;
  }
  else
  {
    return false;
  }
}


void AccelStepperInt::setMaxSpeed(uint32_t speed)
{
  _maxSpeed = speed;
	_accelDecelDist=_maxSpeed^2/_acceleration;
  computeNextStepTime();
}


// Useful during initialisations or after initial positioning
void AccelStepperInt::setCurrentPosition(long position)
{
  if (_speed!=0) return;  //Require being halted to change defined position -JB
  _targetPos = _currentPos = position;
  computeNextStepTime(); // Expect speed of 0
}


AccelStepperInt::AccelStepperInt(uint8_t pins, uint8_t pin1, uint8_t pin2, uint8_t pin3, uint8_t pin4)
{
  _pins = pins;
	_dir=1;
  _currentPos = 0;
  _targetPos = 0;
  _speed = 0;
  _maxSpeed = 1;
  _acceleration = 1;
  _stepInterval = 0;
  _minPulseWidth = 1;
  _dirInverted = false;
  _stepInverted = false;
  _enablePin = 0xff;
  _lastStepTime = 0;
  _pin1 = pin1;
  _pin2 = pin2;
  _pin3 = pin3;
  _pin4 = pin4;
  enableOutputs();
}

AccelStepperInt::AccelStepperInt(void (*forward)(), void (*backward)())
{
  _pins = 0;
	_dir=1;
  _currentPos = 0;
  _targetPos = 0;
  _speed = 0;
  _maxSpeed = 1;
  _acceleration = 1;
  _stepInterval = 0;
  _minPulseWidth = 1;
  _dirInverted = false;
  _stepInverted = false;
  _enablePin = 0xff;
  _lastStepTime = 0;
  _pin1 = 0;
  _pin2 = 0;
  _pin3 = 0;
  _pin4 = 0;
  _forward = forward;
  _backward = backward;
}

void AccelStepperInt::moveTo(long absolute)
{
	_targetPos = absolute;
  computeNextStepTime();
}

void AccelStepperInt::move(long relative)
{
  moveTo(_currentPos + relative);
}


int32_t AccelStepperInt::speed()
{
  return _speed;
}

void AccelStepperInt::setAcceleration(uint32_t acceleration)
{
  _acceleration = acceleration;
	_accelDecelDist=_maxSpeed^2/_acceleration;
  computeNextStepTime();
}

// 0 pin step function (ie for functional usage)
void AccelStepperInt::step0()
{
  if (_dir > 0)
    _forward();
  else
    _backward();
}

// 1 pin step function (ie for stepper drivers)
// This is passed the current step number (0 to 7)
// Subclasses can override
void AccelStepperInt::step1(uint8_t step)
{
    digitalWrite(_pin2, (_dir>0) ^ _dirInverted); // Direction
  
    // Caution 200ns setup time 
    digitalWrite(_pin1, HIGH ^ _stepInverted);
  
    // Delay the minimum allowed pulse width
    delayMicroseconds(_minPulseWidth);
    digitalWrite(_pin1, LOW ^ _stepInverted);
}


// 2 pin step function
// This is passed the current step number (0 to 7)
// Subclasses can override
void AccelStepperInt::step2(uint8_t step)
{
    switch (step & 0x3)
    {
      case 0: /* 01 */
          digitalWrite(_pin1, LOW);
          digitalWrite(_pin2, HIGH);
          break;

      case 1: /* 11 */
          digitalWrite(_pin1, HIGH);
          digitalWrite(_pin2, HIGH);
          break;

      case 2: /* 10 */
          digitalWrite(_pin1, HIGH);
          digitalWrite(_pin2, LOW);
          break;

      case 3: /* 00 */
          digitalWrite(_pin1, LOW);
          digitalWrite(_pin2, LOW);
          break;
    }
}

// 4 pin step function for half stepper
// This is passed the current step number (0 to 7)
// Subclasses can override
void AccelStepperInt::step4(uint8_t step)
{
    switch (step & 0x3)
    {
      case 0:    // 1010
          digitalWrite(_pin1, HIGH);
          digitalWrite(_pin2, LOW);
          digitalWrite(_pin3, HIGH);
          digitalWrite(_pin4, LOW);
          break;

      case 1:    // 0110
          digitalWrite(_pin1, LOW);
          digitalWrite(_pin2, HIGH);
          digitalWrite(_pin3, HIGH);
          digitalWrite(_pin4, LOW);
          break;

      case 2:    //0101
          digitalWrite(_pin1, LOW);
          digitalWrite(_pin2, HIGH);
          digitalWrite(_pin3, LOW);
          digitalWrite(_pin4, HIGH);
          break;

      case 3:    //1001
          digitalWrite(_pin1, HIGH);
          digitalWrite(_pin2, LOW);
          digitalWrite(_pin3, LOW);
          digitalWrite(_pin4, HIGH);
          break;
    }
}


// 4 pin step function
// This is passed the current step number (0 to 3)
// Subclasses can override
void AccelStepperInt::step8(uint8_t step)
{
    switch (step & 0x7)
    {
        case 0:    // 1000
            digitalWrite(_pin1, HIGH);
            digitalWrite(_pin2, LOW);
            digitalWrite(_pin3, LOW);
            digitalWrite(_pin4, LOW);
            break;
	    
        case 1:    // 1010
            digitalWrite(_pin1, HIGH);
            digitalWrite(_pin2, LOW);
            digitalWrite(_pin3, HIGH);
            digitalWrite(_pin4, LOW);
            break;
	    
        case 2:    // 0010
            digitalWrite(_pin1, LOW);
            digitalWrite(_pin2, LOW);
            digitalWrite(_pin3, HIGH);
            digitalWrite(_pin4, LOW);
            break;
	    
        case 3:    // 0110
            digitalWrite(_pin1, LOW);
            digitalWrite(_pin2, HIGH);
            digitalWrite(_pin3, HIGH);
            digitalWrite(_pin4, LOW);
            break;
	    
        case 4:    // 0100
            digitalWrite(_pin1, LOW);
            digitalWrite(_pin2, HIGH);
            digitalWrite(_pin3, LOW);
            digitalWrite(_pin4, LOW);
            break;
	    
        case 5:    //0101
            digitalWrite(_pin1, LOW);
            digitalWrite(_pin2, HIGH);
            digitalWrite(_pin3, LOW);
            digitalWrite(_pin4, HIGH);
            break;
	    
        case 6:    // 0001
            digitalWrite(_pin1, LOW);
            digitalWrite(_pin2, LOW);
            digitalWrite(_pin3, LOW);
            digitalWrite(_pin4, HIGH);
            break;
	    
        case 7:    //1001
            digitalWrite(_pin1, HIGH);
            digitalWrite(_pin2, LOW);
            digitalWrite(_pin3, LOW);
            digitalWrite(_pin4, HIGH);
            break;
    }
}
    
// Prevents power consumption on the outputs
void AccelStepperInt::disableOutputs()
{   
    if (! _pins) return;

    if (_pins == 1)
    {
        // Invert only applies for stepper drivers.
        digitalWrite(_pin1, LOW ^ _stepInverted);
        digitalWrite(_pin2, LOW ^ _dirInverted);
    }
    else
    {
        digitalWrite(_pin1, LOW);
        digitalWrite(_pin2, LOW);
    }
    
    if (_pins == 4 || _pins == 8)
    {
        digitalWrite(_pin3, LOW);
        digitalWrite(_pin4, LOW);
    }

    if (_enablePin != 0xff)
    {
        digitalWrite(_enablePin, LOW ^ _enableInverted);
    }
}

void AccelStepperInt::enableOutputs()
{
    if (! _pins) return;

    pinMode(_pin1, OUTPUT);
    pinMode(_pin2, OUTPUT);
    if (_pins == 4 || _pins == 8)
    {
        pinMode(_pin3, OUTPUT);
        pinMode(_pin4, OUTPUT);
    }

    if (_enablePin != 0xff)
    {
        pinMode(_enablePin, OUTPUT);
        digitalWrite(_enablePin, HIGH ^ _enableInverted);
    }
}

void AccelStepperInt::setMinPulseWidth(unsigned int minWidth)
{
    _minPulseWidth = minWidth;
}

void AccelStepperInt::setEnablePin(uint8_t enablePin)
{
    _enablePin = enablePin;

    // This happens after construction, so init pin now.
    if (_enablePin != 0xff)
    {
        pinMode(_enablePin, OUTPUT);
        digitalWrite(_enablePin, HIGH ^ _enableInverted);
    }
}

void AccelStepperInt::setPinsInverted(bool direction, bool step, bool enable)
{
    _dirInverted    = direction;
    _stepInverted   = step;
    _enableInverted = enable;
}

// Blocks until the target position is reached
void AccelStepperInt::runToPosition()
{
    while (run());
}

// Blocks until the new target position is reached
void AccelStepperInt::runToNewPosition(long position)
{
    moveTo(position);
    runToPosition();
}


long AccelStepperInt::distanceToGo()
{
  return _targetPos - _currentPos;
}

long AccelStepperInt::targetPosition()
{
  return _targetPos;
}

long AccelStepperInt::currentPosition()
{
  return _currentPos;
}


/*
static uint32_t AccelStepperInt::sqrt_i_asm(uint32_t x) {
 
  uint32_t root;

  /*      ;  Fast and short 32 bits AVR sqrt routine
   ;
   ;  R17:R16=SQRT(R5:R4:R3:R2) rounded to the nearest integer (0.5 rounds up)
   ;
   ;  Registers:
   ;  Destroys the argument in R5:R4:R3:R2
   ;
   ;  Cycles incl call & ret = 271 - 316
   ;
   ;  Stack incl call = 4
   
  asm(
      "Sqrt32:     push  %R18;"      
      "push  %R19;"
      "ldi   %R19,$0xC0;"
      "clr   %R18"                  // rotation mask in R19:R18
      "ldi   %R17,$0x40;"
      "sub   %R16,%R16;"            // developing sqrt in R17:R16, C=0
      "_sq32_1:    brcs  _sq32_2;"  // C --> Bit is always 1
      "cp    %R4,%R16;"
      "cpc   %R5,%R17;"             // Does test value fit?
      "brcs  _sq32_3;"              // C --> nope, bit is 0
      "_sq32_2:    sub   %R4,%R16;"
      sbc   R5,R17            ; Adjust argument for next bit
      or    R16,R18
      or    R17,R19           ; Set bit to 1
      _sq32_3:    lsr   R19
      ror   R18               ; Shift right mask, C --> end loop
      eor   R17,R19
      eor   R16,R18           ; Shift right only test bit in result
      rol   R2                ; Bit 0 only set if end of loop
      rol   R3
      rol   R4
      rol   R5                ; Shift left remaining argument (C used at _sq32_1)
      sbrs  R2,0              ; Skip if 15 bits developed
      rjmp  _sq32_1           ; Develop 15 bits of the sqrt
      brcs  _sq32_4           ; C--> Last bits always 1
      cp    R16,R4
      cpc   R17,R5            ; Test for last bit 1
      brcc  _sq32_5           ; NC --> bit is 0
      
      _sq32_4:    sbc   R3,R19            ; Subtract C (any value from 1 to 0x7f will do)
      sbc   R4,R16
      sbc   R5,R17            ; Update argument for test
      inc   R16               ; Last bit is 1
      
      _sq32_5:    lsl   R3                ; Only bit 7 matters
      rol   R4
      rol   R5                ; Remainder * 2 + C
      brcs  _sq32_6           ; C --> Always round up
      cp    R16,R4
      cpc   R17,R5            ; C decides rounding
      _sq32_6:    adc   R16,R19
      adc   R17,R19           ; Round up if C (R19=0)
      pop   R19
      pop   R18
      : "=r" (root) 
      : "r" (x)
      : ""
  )
}
*/