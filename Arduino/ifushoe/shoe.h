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
#include <stdio.h>

//#define DEBUG_FEEDBACK


#define ENABLE_DETACH true
#define RC_PULSE_DELAY 403  // LAC averages 4 RC pulses in multiples of 20ms (so 80ms min) 
#define RC_PULSE_DELAY_SHORT 90



#define E_HEIGHTSTALL   0b000001
#define E_HEIGHTSTUCK   0b000010
#define E_PIPESTALL     0b000100
#define E_HEIGHTMOVEDUP 0b001000
#define E_RECOVER       0b010000
#define E_PIPESHIFT     0b100000
//
//#define N_HEIGHT_POS 7
#define N_UP_POS 6
#define N_DOWN_POS 6
#define N_SLIT_POS 6

#define MAX_SHOE_POS 1000


#define DOWN_NDX 0

#define DEFAULT_IDLE_DISCONNECTED true
#define MOTOR_RELAY_HOLD_MS 8  //ds says 4ms max needed
#define SAMPLE_INTERVAL_MS 2
#define EWMA_SAMPLES 25 //7



#define MOVING 0xFE
#define UNKNOWN_SLIT 0xFF
#define DEFAULT_TOL 33   // about 0.33mm, 20mm/1000 per unit, more than 135 is right out!
#define MAX_HEIGHT_TOL 100
#define MAX_PIPE_TOL 35

#define MAX_ADC 1023
#define ADU_PER_STEP 1.024// 1.0929
#define ADU_TO_STEP 0.9765625// 1.0929

#define MOVING_PIPE_TOL 3
#define MOVING_HEIGHT_TOL 3
#define MOVING_TIMEOUT_MS 1250

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

typedef struct shoecfg_t {
  uint16_t height_pos[N_SLIT_POS];  //in Servo units
  uint16_t down_pos[N_SLIT_POS];    //in Servo units
  uint16_t pipe_pos[N_SLIT_POS];      // same as height_pos
  uint8_t pipe_tol;  //in Servo units
  uint8_t height_tol;  //in Servo units
  shoepos_t pos;  //filtered pos in Servo units
  uint8_t desired_slit;
  bool idle_disconnected;
} shoecfg_t;

typedef struct shoestatus_t {
  shoepos_t pos;
  shoepos_t target;
  shoeerr_t error;
  shoemoving_t moving;
  shoeheading_t heading;
} shoestatus_t;



class ShoeDrive {

  public:
    ShoeDrive(char shoe_name, uint8_t pipe_servo_pin, uint8_t pipe_pot_pin, uint8_t height_servo_pin, uint8_t height_pot_pin, uint8_t height_sensor_pin,
              uint8_t motorsoff_pin, uint8_t motorson_pin, Servo *p, Servo *h);
    ~ShoeDrive();

    void init();
    void stop();
    void setMotorPower(bool);
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
    int16_t getPipeError();
    int16_t getHeightError();
    
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

    bool idle();  //return true when in position and nothing will move when run is called

    uint16_t errors;
    bool motorsPowered;

  private:
    char _shoe_name;
    uint8_t _retries;
    bool _detachHeight(uint16_t height); //return true if detach enabled at the passed height
    uint16_t safe_pipe_height;  //This changes depending on the move
    uint16_t _clearance_height(uint8_t slit, bool tell=false);
    void _wait(uint32_t time_ms);
    void _updateFeedbackPos();
    shoestatus_t _status();
    uint8_t _currentPipeIndex();
//    uint8_t _currentHeightIndex();
    inline void _movePipe(uint16_t pos, uint16_t wait, bool detach);
    inline void _moveHeight(uint16_t pos, uint16_t wait, bool detach);
    void _move(Servo *axis, uint16_t pos, uint16_t wait, bool detach);
    shoeheading_t _heading;
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
    bool _height_moving;
    bool _pipe_moving;

};
#endif
