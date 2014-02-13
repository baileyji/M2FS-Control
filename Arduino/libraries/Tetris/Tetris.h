#ifndef __Tetris_H__
#define __Tetris_H__

#if ARDUINO < 100
#include <WProgram.h>
#else  // ARDUINO
#include <Arduino.h>
#endif  // ARDUINO

#include <AccelStepper.h>


//2.368mm/((4*20*256)/4)
//462.5nm/step


//SLIT_SPACING 220um
//tol 25um 54 steps

//SLIT1 180um
//372.5 um = 805.5 step +- 70.5
//SLIT2 125um
//330 um = 713.5 step +- 66
//SLIT3 95um
//305 um = 659.5 step +- 63
//SLIT4 75um
//286.5um = 619.5 steps +- 61
//SLIT5 58um
//271.5um = 587 step +- 60
//SLIT6 45um

#define N_SLIT_POS 7
#define DEFAULT_POS_SLIT1 -2275 //-2500
#define DEFAULT_POS_SLIT2 -3100 //-3400
#define DEFAULT_POS_SLIT3 -3850 //-4250
#define DEFAULT_POS_SLIT4 -4500 //-5025
#define DEFAULT_POS_SLIT5 -5175 //-5775
#define DEFAULT_POS_SLIT6 -5800 //-6525
#define DEFAULT_POS_SLIT7 0 // Mario's Gort
#define DEFAULT_BACKLASH 0//145 //<=170.7 (3deg/360*(USTEPPING*20*256)) per ds
#define HOME_MOVE_OVERSHOOT 250
#define MAX_HARDSTOP_DISTANCE 10000
#define MOTOR_HOME_POSITION DEFAULT_POS_SLIT7
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
    void homedMoveToSlit(uint8_t slit);
    void run();
  	void calibrateToHardStop();
    void moveToHardStop();
  
  private:
    unsigned char _homed_move_in_progress;
    unsigned char _calibration_in_progress;
    int _standby_pin;
    int _reset_pin;
    int _clock_pin;
    int _dir_pin;
    int _phase_pin;
    int8_t _lastDir;
    bool _calibrated;
    unsigned int _backlash;
    long _slitPositions[N_SLIT_POS];
    long _targetAfterHome;
    AccelStepper _motor;

};
#endif