#ifndef __Tetris_H__
#define __Tetris_H__

#if ARDUINO < 100
#include <WProgram.h>
#else  // ARDUINO
#include <Arduino.h>
#endif  // ARDUINO

#include <AccelStepper.h>

#define DEFAULT_POS_SLIT1 -290
#define DEFAULT_POS_SLIT2 -510
#define DEFAULT_POS_SLIT3 -745
#define DEFAULT_POS_SLIT4 -935
#define DEFAULT_POS_SLIT5 -1115
#define DEFAULT_POS_SLIT6 -1275
#define DEFAULT_POS_SLIT7 -1435
#define DEFAULT_BACKLASH 10 //10 full steps
#define MOTOR_HOME_POSITION DEFAULT_POS_SLIT2

class Tetris
{

  public:
    Tetris();
    Tetris(int rst_pin, int stby_pin, int dir_pin, int ck_pin, int phase_pin);
    ~Tetris();
    void motorOff();
		void motorPwrOffPos(); //Move to a predefined off position
    bool motorIsOn();
		void motorOn();
    void tellPosition();
    void stop();
    bool moving();
    
    void definePosition(long p);
    void setSpeed(int s);
    void setAcceleration(long s);
    void setBacklash(unsigned int b);
    void positionRelativeMove(long d);
    void positionAbsoluteMove(long p);
    void defineSlitPosition(uint8_t slit);
    void dumbMoveToSlit(uint8_t slit);
    void run();
  	void calibrateToHardStop();
  
  private:
    int _standby_pin;
    int _reset_pin;
    int _clock_pin;
    int _dir_pin;
		int _phase_pin;
		int8_t _lastDir;
    unsigned int _backlash;
		long _slitPositions[7];      
    AccelStepper _motor;

};
#endif