#ifndef __Shoe_H__
#define __Shoe_H__
#include <Arduino.h>
#include <stdio.h>
#include "JrkG2.h"

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


//B measured at 14.4um per scaled step 9/16/22
//R measured at 16.7um per scaled step 9/16/22
// r pipe at 13.37 um per scaled step 9/17/22  (3.25um in the pololu gui)


#define JrkFeedbackErrorMinimum 0x19  // uint16_t,
#define JrkFeedbackErrorMaximum 0x1B  // uint16_t,
#define JrkFeedbackMinimum 0x1D  // uint16_t,
#define JrkFeedbackMaximum 0x1F  // uint16_t,

#define E_HEIGHTSTALL   0b000001
#define E_HEIGHTSTUCK   0b000010
#define E_PIPESTALL     0b000100
#define E_HEIGHTMOVEDUP 0b001000
#define E_RECOVER       0b010000
#define E_PIPESHIFT     0b100000


#define MAX_CURRENT 210  //mA

#define N_UP_POS 6
#define N_DOWN_POS 6
#define N_SLIT_POS 6

#define MAX_SHOE_POS 1000

#define DOWN_NDX 0

#define MOTOR_RELAY_HOLD_MS 6  //DS says 4ms max needed

#define MOVING 0xFE
#define UNKNOWN_SLIT 0xFF
#define HEIGHT_TOL_UP 35
#define DEFAULT_TOL 15   // about 0.33mm, 20mm/1000 per unit, more than 135 is right out!
#define MAX_HEIGHT_TOL 100
#define MAX_PIPE_TOL 35

#define MAX_ADC 1023
#define ADU_PER_STEP 1.024// 1.0929
#define ADU_TO_STEP 0.9765625// 1.0929

#define POS_TO_JRK 4.095
#define JRK_TO_POS (1.0/4.095)

#define MOVING_PIPE_TOL 6
#define MOVING_HEIGHT_TOL 6
#define MOVING_TIMEOUT_MS 250

#define MAX_RETRIES 2

#define SHOE_IDLE 0
#define USER_MOVE_pipe 2
#define USER_MOVE_height 1

#define RECOVERY_MOVE 99
#define RECOVERY_MOVE_pipe 98
#define RECOVERY_MOVE_raise 97
#define SLIT_MOVE 10
#define SLIT_MOVE_lower 9
#define SLIT_MOVE_pipe 8
#define SLIT_MOVE_raise 7

//average spacing is about 180, so about 40%
#define PIPE_SPACING 186
#define PIPE_SPACING_FOR_CLEARNCE 75

#define STALL_DECREMENT 42
#define STALL_LIMIT 840000 //630000


typedef struct stalldata_t {
  uint32_t lastcall;
  int32_t total_pipe;
  int32_t total_height; 
} stalldata_t;

typedef struct shoepos_t {
  uint16_t height;
  uint16_t pipe;
} shoepos_t;

typedef struct shoeerr_t {
  int16_t height;
  int16_t pipe;
} shoeerr_t;

typedef struct shoemoving_t {
  bool height;
  bool pipe;
} shoemoving_t;

typedef struct shoeheading_t {
  int8_t pipe;
  int8_t height;
} shoeheading_t;

typedef struct shoetol_t {
  uint8_t pipe;
  uint8_t height;
} shoetol_t;

typedef struct shoecfg_t {
  uint16_t height_pos[N_SLIT_POS];  //in Servo units
  uint16_t down_pos[N_SLIT_POS];    //in Servo units
  uint16_t pipe_pos[N_SLIT_POS];      // same as height_pos
  uint8_t pipe_tol;  //in Servo units
  uint8_t height_tol;  //in Servo units
  uint8_t desired_slit;
} shoecfg_t;

typedef struct shoestatus_t {
  shoepos_t pos;
  shoepos_t target;
  shoeerr_t error;
  shoeerr_t slerror; //distance from desired slit setpoint
  shoemoving_t moving;
  shoeheading_t heading;
  uint8_t desired_slit;
  
//  uint32_t last_pipe_movement_ms;
//  uint32_t last_height_movement_ms;
//  uint8_t retries_left;
} shoestatus_t;


class ShoeDrive {

  public:
    ShoeDrive(char shoe_name, uint8_t pipe_pot_pin, uint8_t height_pot_pin,
              uint8_t motorsoff_pin, uint8_t motorson_pin, JrkG2I2C *p, JrkG2I2C *h);

    void init();
    void stop();
    void setMotorPower(bool);
    void run(); //1ms when idle

    shoepos_t getFeedbackPosition();  //From feedback
    shoepos_t getCommandedPosition(); //from servo

    void tellStatus();
    
    void tellCurrentSlit();
    uint8_t getCurrentSlit(); //0-5 or 0xFF = INTERMEDIATE, 0xFE = MOVING
    uint16_t getSlitPosition(uint8_t slit);
    uint16_t getHeightPosition(uint8_t height);
    
    bool moveInProgress();  //true if a move from one slit to another is in progress
    bool pipeMoving();  //indicates literal movement
    bool heightMoving(); //indicates literal movement

    void defineTol(char axis, uint8_t tol);
    void defineSlitPosition(uint8_t slit, uint16_t pos);
    void defineHeightPosition(uint8_t height, uint16_t pos);
    void defineDownPosition(uint8_t slit, uint16_t pos);
    
    void moveToSlit(uint8_t slit);
    void movePipe(uint16_t pos);
    void moveHeight(uint16_t pos);
    void downUp();

    bool safeToMovePipes();
    bool fibersAreUp();

    void getState(shoecfg_t &data);
    void restoreState(shoecfg_t data);

    uint16_t errors;
    bool motorsPowered;
    bool keepSafe;

  private:
    char _shoe_name;
    uint8_t _sensor_pin;
    uint8_t _pipe_pot_pin;
    uint8_t _height_pot_pin;
    uint8_t _motorsoff_pin;
    uint8_t _motorson_pin;

    shoecfg_t _cfg;

    void _protectStall();
    bool _detachHeight(uint16_t height); //return true if detach enabled at the passed height
    uint16_t _clearance_height(uint8_t slit, bool tell=false);
    void _updateFeedbackPos();
    shoestatus_t _status();
    uint8_t _currentPipeIndex();
    inline void _movePipe(uint16_t pos);
    inline void _moveHeight(uint16_t pos);
    void _move(JrkG2I2C *axis, uint16_t pos);
    bool _jrk_wants_to_move(JrkG2I2C *axis);
    bool _jrk_stopped(JrkG2I2C *axis);
    int16_t _jrk_dist_to_target(JrkG2I2C *axis);

    uint16_t _safe_pipe_height;  //This changes depending on the move
    uint8_t _retries;
    uint8_t _retry_down;
    shoeheading_t _heading;
    shoepos_t _feedback_pos;
    shoepos_t _movepos; //for detecting movement
    uint32_t _timeLastPipeMovement;
    uint32_t _timeLastHeightMovement;
    bool _height_moving;
    bool _pipe_moving;
    stalldata_t _stallmon;
    
    uint32_t _samplet;

    uint8_t _moveInProgress;       //0 idle, 1 pipe, 2 height, 7 up move commanded, 8 pipe move commanded, 9 down move commanded ,10 starting move
    JrkG2I2C *_pipe_motor;
    JrkG2I2C *_height_motor;
};
#endif
