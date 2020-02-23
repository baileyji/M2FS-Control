#ifndef __Shoe_H__
#define __Shoe_H__

#include <Arduino.h>
#include <Servo.h>
#include <EwmaT.h>
//#include "ewmat64.h"
#include <stdio.h>

#define E_PIPESTALL   0b0100
#define E_HEIGHTSTALL 0b0001
#define E_HEIGHTSTUCK 0b0010

#define N_HEIGHT_POS 2
#define N_SLIT_POS 6

#define MAX_SHOE_POS 180

#define PIPE_CLEARANCE_HEIGHT 100

#define UP_NDX 1
#define DOWN_NDX 0


#define MOVING_TIMEOUT_MS 20

typedef struct shoepos_t {
  uint16_t height;
  uint16_t pipe;
} shoepos_t;

typedef struct shoecfg_t {
  uint16_t height_pos[N_HEIGHT_POS];
  uint16_t pipe_pos[N_HEIGHT_POS];
} shoecfg_t;


class ShoeDrive {

  public:
    ShoeDrive(uint8_t pipe_servo_pin, uint8_t pipe_pot_pin, uint8_t height_servo_pin, uint8_t height_pot_pin, uint8_t height_sensor_pin,Servo *p, Servo *h);//, EwmaT<uint64_t> &a, EwmaT<uint64_t> &b);
    ~ShoeDrive();

    void init();

    void stop();

    void tellCurrentPosition();
    shoepos_t getCurrentPosition();  //From feedback
    shoepos_t getCommandedPosition(); //from servo
    
    void tellCurrentSlit();
    uint8_t getCurrentSlit(); //0-5 or 0xFF = INTERMEDIATE, 0xFE = MOVING
    
    void tellSlitPosition(uint8_t slit);
    uint16_t getSlitPosition(uint8_t slit);
    
    bool moving();  //true if a move from one slit to another is in progress
    bool pipeMoving();  //indicates literal movement
    bool heightMoving(); //indicates literal movement

    void defineSlitPosition(uint8_t slit, uint16_t pos);
    void defineSlitPosition(uint8_t slit);
    
    void moveToSlit(uint8_t slit);
    void movePipe(uint16_t pos);
    void moveHeight(uint16_t pos);

    bool safeToMovePipes();
    bool fibersAreUp();

    void getEEPROMInfo(shoecfg_t &data);
    void restoreEEPROMInfo(shoecfg_t data);

    bool idle();  //return true when in position and nothing will move when run is called
    void motorsOff();  //turn motors off, NO OP unless relays are added 
    void run(); //1ms when idle

    uint16_t errors;

  private:
    uint8_t _currentPipeIndex();
    uint8_t _sensor_pin;
    uint8_t _pipe_pin;
    uint8_t _pipe_pot_pin;
    uint8_t _height_pin;
    uint8_t _height_pot_pin;
    uint16_t _pipePositions[N_SLIT_POS];
    uint16_t _heightPositions[N_HEIGHT_POS];
    uint16_t _positionTolerance;
    shoepos_t _feedback_pos;
    uint8_t _desiredSlit;
    uint32_t _timeLastPipeMovement;
    uint32_t _timeLastHeightMovement;
    uint8_t _moveInProgress;
    Servo *_pipe_motor;
    Servo *_height_motor;
    EwmaT<uint64_t> _pipe_filter; 
    EwmaT<uint64_t> _height_filter; 

};
#endif
