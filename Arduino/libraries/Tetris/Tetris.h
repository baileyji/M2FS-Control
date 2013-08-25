#ifndef __Tetris_H__
#define __Tetris_H__

#if ARDUINO < 100
#include <WProgram.h>
#else  // ARDUINO
#include <Arduino.h>
#endif  // ARDUINO

#include <AccelStepper.h>


//SLIT_SPACING 220um
//SLIT1 180um
//SLIT2 125um
#define DEFAULT_POS_SLIT1 -2275 //-2500
#define DEFAULT_POS_SLIT2 -3100 //-3400
#define DEFAULT_POS_SLIT3 -3850 //-4250
#define DEFAULT_POS_SLIT4 -4500 //-5025
#define DEFAULT_POS_SLIT5 -5175 //-5775
#define DEFAULT_POS_SLIT6 -5800 //-6525
#define DEFAULT_POS_SLIT7 -6100 //-7250
#define DEFAULT_BACKLASH 145 //<= 3deg 
#define MAX_HARDSTOP_DISTANCE 10000
#define MOTOR_HOME_POSITION DEFAULT_POS_SLIT2
#define USTEPPING 4 //Function of circuit board, fixed forever

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
    void tellBacklash();
    int32_t currentPosition();
    void tellSlitPosition(uint8_t slit);
    int32_t getSlitPosition(uint8_t slit);
    void stop();
    bool moving();
    bool isCalibrated();
    char getCurrentSlit();//0-6 if calibrated and currentposition==respective nominal slit position, else -1 
    
    void definePosition(long p);
    void setSpeed(int s);
    void setAcceleration(long s);
    void setBacklash(unsigned int b);
    uint16_t getBacklash();
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