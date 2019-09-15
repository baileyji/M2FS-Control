#ifndef __Shoe_H__
#define __Shoe_H__

#if ARDUINO < 100
#include <WProgram.h>
#else  // ARDUINO
#include <Arduino.h>
#endif  // ARDUINO

#include <Adafruit_MCP4725.h>

#define N_HEIGHT_POS 2
#define N_SLIT_POS 6

#define PIN_IMON  1
#define PIN_VMON  2
#define PIN_ENABLE 3
#define PIN_VMODE 5
#define PIN_IMODE 4

#define PIN_IMON  1
#define PIN_VMON  2
#define PIN_ENABLE 3
#define PIN_VMODE 5
#define PIN_IMODE 4

#define PIN_IMON  1
#define PIN_VMON  2
#define PIN_ENABLE 3
#define PIN_VMODE 5
#define PIN_IMODE 4

class ShoeDrive
{

  public:
    ShoeDrive();
    ShoeDrive(int pipe_axis_pin, int height_axis_pin, int height_sensor_pin);
    ~ShoeDrive();
    
    void tellSlit();
    int32_t currentPosition();  //TODO struct return
    void tellSlitPosition(uint8_t slit);
    int32_t getSlitPosition(uint8_t slit);
    bool moving();
    bool isCalibrated();
    int getCurrentSlit(); //0-6 or -1 
    
    void defineSlitPosition(uint8_t slit, long position);
    void defineSlitPosition(uint8_t slit);
    void moveToSlit(uint8_t slit);

    void lowerFibers();
    void raiseFibers();
    void areFibersLowered();

    void run();

  
  private:
    unsigned char _homed_move_in_progress;
    unsigned char _calibration_in_progress;
    int _sensor_pin;
    int _height_pin;
    int _pip_pin;
//    int _dir_pin;
//    int _phase_pin;
    long _slitPositions[N_SLIT_POS];
    long _heightPositions[N_HEIGHT_POS];
    AccelStepper _motor;

};
#endif
