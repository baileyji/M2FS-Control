#ifndef __Tetris_H__
#define __Tetris_H__

#if ARDUINO < 100
#include <WProgram.h>
#else  // ARDUINO
#include <Arduino.h>
#endif  // ARDUINO

#include <AccelStepper.h>

#define DEFAULT_POS_SLIT1 -2275  //-2400 -2100 -2275
#define DEFAULT_POS_SLIT2 -3100  //-3100 -3000 -3100
#define DEFAULT_POS_SLIT3 -3850  //-4000 -3800 -3850
#define DEFAULT_POS_SLIT4 -4500  //-4900 -4600 -4500
#define DEFAULT_POS_SLIT5 -5175 //-5800 xxxxx -5175
#define DEFAULT_POS_SLIT6 -5800 //-6700 xxxxx -5800
#define DEFAULT_POS_SLIT7 -6100 //-7600 -9000 -6150 (can barely get there with #18)
#define DEFAULT_BACKLASH 0 //<10 usteps
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
    int32_t currentPosition();
    void tellSlitPosition(uint8_t slit);
    void stop();
    bool moving();
    bool isCalibrated();
    char getCurrentSlit();//0-6 if calibrated and currentposition==respective nominal slit position, else -1 
    
    void definePosition(long p);
    void setSpeed(int s);
    void setAcceleration(long s);
    void setBacklash(unsigned int b);
    void positionRelativeMove(long d);
    void positionAbsoluteMove(long p);
    void positionRelativeMoveFS(long d); //Move in full steps
    void positionAbsoluteMoveFS(long p); //Move in full steps
    void defineSlitPosition(uint8_t slit, long position);
    void defineSlitPosition(uint8_t slit);
    void dumbMoveToSlit(uint8_t slit);
    void run();
  	void calibrateToHardStop();
  
  private:
    unsigned char _calibration_in_progress;
    int _standby_pin;
    int _reset_pin;
    int _clock_pin;
    int _dir_pin;
    int _phase_pin;
    int8_t _lastDir;
    bool _calibrated;
    unsigned int _backlash;
    long _slitPositions[7];      
    AccelStepper _motor;

};
#endif