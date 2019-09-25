#ifndef __Ultravolt_H__
#define __Ultravolt_H__

#if ARDUINO < 100
#include <WProgram.h>
#else  // ARDUINO
#include <Arduino.h>
#endif  // ARDUINO

#include <Adafruit_MCP4725.h>

#define MAX_VOUT_V 1000  //Ultravolt can go to 1000
#define MAX_IOUT_MA 10  //ultravolt can go to 30

#define VOLTS_TO_ADC (0x0FFF/1000.0)
#define MILLIAMPS_TO_ADC (0x0FFF/30.0)

//TODO Verify these aren't affected by setpoints
#define ADC_TO_VOLTS (1000/1023.0)
#define ADC_TO_MILLIAMPS (30/1023.0)

typedef unsigned int current_t;
typedef unsigned int voltage_t;

class Ultravolt {
  
  public:
    Ultravolt(int imon_pin, int vmon_pin, int enable_pin, int vmode_pin, int imode_pin, 
              int isel_pin, int vsel_pin, unsigned int vlimit, unsigned int ilimit, Adafruit_MCP4725 &dac);
    ~Ultravolt();
    void begin();
    
    bool isCurrentMode();
    bool isVoltageMode();
    
    voltage_t getVoltage();
    voltage_t getVoltageLimit();
    bool setVoltageLimit(voltage_t limit);
    
    current_t getCurrent();
    current_t getCurrentLimit();
    bool setCurrentLimit(current_t limit);
    
    bool isEnabled();
    
    void turnOff();
    void turnOn();
    void turnOn(current_t current);
    bool isOn();

    void monitorIgnition(uint32_t duration);
  
  private:
    Adafruit_MCP4725 &_dac;
    voltage_t _vlimit;
    current_t _ilimit;
    int _imon_pin;
    int _vmon_pin;
    int _enable_pin;
    int _vmode_pin;
    int _imode_pin;
    int _isel_pin;
    int _vsel_pin;

};
#endif
