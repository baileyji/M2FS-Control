#ifndef __Shoe_H__
#define __Shoe_H__

#include <Arduino.h>
#include <Servo.h>

#define N_HEIGHT_POS 2
#define N_SLIT_POS 6

#define MAX_SHOE_POS 180


typedef struct shoepos_t {
  uint16_t height;
  uint16_t pipe;
} shoepos_t;


class ShoeDrive {

  public:
    ShoeDrive(uint8_t pipe_servo_pin, uint8_t pipe_pot_pin, uint8_t height_servo_pin, uint8_t height_pot_pin, uint8_t height_sensor_pin);
    ~ShoeDrive();
    

    void stop();

    void tellCurrentPosition();
    shoepos_t getCurrentPosition();
    
    void tellCurrentSlit();
    int8_t getCurrentSlit(); //0-6 or -1 
    
    void tellSlitPosition(uint8_t slit);
    uint16_t getSlitPosition(uint8_t slit);
    
    bool moving();  //true if a move from one slit to another is in progress
    bool pipesMoving();  //indicates literal movement
    bool heightMoving(); //indicates literal movement

    
    void defineSlitPosition(uint8_t slit, long position);
    void defineSlitPosition(uint8_t slit);
    void moveToSlit(uint8_t slit);
    void movePipe(uint8_t pos);
    void moveHeight(uint8_t pos);

    void lowerFibers();
    void raiseFibers();
    bool areFibersLowered();

    void getEEPROMInfo(uint16_t data[N_SLIT_POS+N_HEIGHT_POS]);
    void restoreEEPROMInfo(uint16_t data[N_SLIT_POS+N_HEIGHT_POS]);
    
    void run();

  private:
    uint8_t _sensor_pin;
    uint8_t _pipe_pin;
    uint8_t _pipe_pot_pin;
    uint8_t _height_pin;
    uint8_t _height_pot_pin;
    uint16_t _slitPositions[N_SLIT_POS];
    uint16_t _heightPositions[N_HEIGHT_POS];
    Servo _pipe_motor;
    Servo _height_motor;

};
#endif
