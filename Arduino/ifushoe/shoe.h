#ifndef __Shoe_H__
#define __Shoe_H__

/*

The zero position of the organ pipes (first organ pipe) occurs when post 
hole axis is 5.65 mm from the front face of the actuator.
The pipes are 2.5 mm apart, so the positions relative to the front face are:

Nominal positions are then (position-3mm)*(

Post     Position   Nominal
-lim        4.65    15
1           5.65    24
2           8.15    46 
3          10.65    68
4          13.15    91
5          15.65    114
6          18.15    136
+lim       22.51    175

The mechanical limits on this scale happen at 4.65 and 22.51.
Pipes have about 13.55mm travel  ~20um adc count
Height has about 16.60mm travel  ~20um/adc count
 */


#include <Arduino.h>
#include <Servo.h>
#include <EwmaT.h>
//#include "ewmat64.h"
#include <stdio.h>
//#include <Streaming.h>

#define DEBUG_FEEDBACK


#define E_PIPESTALL   0b0100
#define E_HEIGHTSTALL 0b0001
#define E_HEIGHTSTUCK 0b0010

#define N_HEIGHT_POS 2
#define N_SLIT_POS 6

#define MAX_SHOE_POS 1000


#define UP_NDX 1
#define DOWN_NDX 0

#define DEFAULT_IDLE_DISCONNECTED false
#define MOTOR_RELAY_HOLD_MS 100  //blind guess
#define SAMPLE_INTERVAL_MS 2
#define EWMA_SAMPLES 25 //7
#define RC_PULSE_DELAY 400

#define MOVING 0xFE
#define UNKNOWN_SLIT 0xFF
#define DEFAULT_TOL 33   // about 0.33mm, 20mm/180 per unit, more than 25 is right out!
#define MAX_HEIGHT_TOL 100
#define MAX_PIPE_TOL 35

#define MAX_ADC 1023
#define ADU_PER_STEP 1.024// 1.0929
#define ADU_TO_STEP 0.9765625// 1.0929

#define MOVING_PIPE_TOL 3
#define MOVING_HEIGHT_TOL 2
#define MOVING_TIMEOUT_MS 1250

typedef struct shoepos_t {
  uint16_t height;
  uint16_t pipe;
} shoepos_t;

typedef struct shoecfg_t {
  uint16_t height_pos[N_HEIGHT_POS];  //in Servo units
  uint16_t pipe_pos[N_SLIT_POS];  // same as height_pos
  uint8_t pipe_tol;  //in Servo units
  uint8_t height_tol;  //in Servo units
  shoepos_t pos;  //filtered pos in Servo units
  uint8_t desired_slit;
  bool idle_disconnected;
} shoecfg_t;


class ShoeDrive {

  public:
    ShoeDrive(uint8_t pipe_servo_pin, uint8_t pipe_pot_pin, uint8_t height_servo_pin, uint8_t height_pot_pin, uint8_t height_sensor_pin,
              uint8_t motorsoff_pin, uint8_t motorson_pin, Servo *p, Servo *h);//, EwmaT<uint64_t> &a, EwmaT<uint64_t> &b);
    ~ShoeDrive();

    void init();
    void stop();
    void powerOnMotors();
    void powerOffMotors();
    void run(); //1ms when idle

    void tellCurrentPosition();
    shoepos_t getFilteredPosition();  //From feedback
    shoepos_t getLivePosition(); //reads ADCs
    shoepos_t getCommandedPosition(); //from servo
    bool getOffWhenIdle();
    void toggleOffWhenIdle();

    void tellStatus();
    
    void tellCurrentSlit();
    uint8_t getCurrentSlit(); //0-5 or 0xFF = INTERMEDIATE, 0xFE = MOVING
    uint16_t getSlitPosition(uint8_t slit);
    uint16_t getHeightPosition(uint8_t height);
    int16_t getPositionError();
    int16_t getDistanceFromSlit(uint8_t i);
    
    bool moveInProgress();  //true if a move from one slit to another is in progress
    bool pipeMoving();  //indicates literal movement
    bool heightMoving(); //indicates literal movement

    void defineTol(char axis, uint8_t tol);
    void defineSlitPosition(uint8_t slit, uint16_t pos);
    void defineSlitPosition(uint8_t slit);
    void defineHeightPosition(uint8_t height, uint16_t pos);
    void defineHeightPosition(uint8_t height);
    
    void moveToSlit(uint8_t slit);
    void movePipe(uint16_t pos);
    void moveHeight(uint16_t pos);

    bool safeToMovePipes();
    bool fibersAreUp();
    bool downButtonPressed();

    void getState(shoecfg_t &data);
    void restoreState(shoecfg_t data);

    bool idle();  //return true when in position and nothing will move when run is called

    uint16_t errors;
    bool motorsPowered;

  private:
    void _wait(uint32_t time_ms);
    void _updateFeedbackPos();
    uint8_t _currentPipeIndex();
    void ShoeDrive::_movePipe(uint16_t pos);
    void ShoeDrive::_moveHeight(uint16_t pos);
    uint8_t _sensor_pin;
    uint8_t _pipe_pin;
    uint8_t _pipe_pot_pin;
    uint8_t _height_pin;
    uint8_t _height_pot_pin;
    uint8_t _motorsoff_pin;
    uint8_t _motorson_pin;
    shoecfg_t _cfg;
    shoepos_t _feedback_pos;
    shoepos_t _movepos; //for detecting movement
    uint32_t _timeLastPipeMovement;
    uint32_t _timeLastHeightMovement;
    uint32_t _samplet;
    //0 idle, 1 pipe, 2 height, 7 up move commanded, 8 pipe move commanded, 9 down move commanded ,10 starting move
    uint8_t _moveInProgress;  
    Servo *_pipe_motor;
    Servo *_height_motor;
    EwmaT<uint64_t> _pipe_filter; //in adc units
    EwmaT<uint64_t> _height_filter;  // in adc units

};
#endif
