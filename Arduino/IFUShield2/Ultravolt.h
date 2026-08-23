#ifndef __Ultravolt_H__
#define __Ultravolt_H__

#if ARDUINO < 100
#include <WProgram.h>
#else  // ARDUINO
#include <Arduino.h>
#endif  // ARDUINO
#include <Adafruit_MCP4725.h>
#include <Adafruit_TLA202x.h>


#define MAX_VOUT_V 1000  //Ultravolt can go to 1000
#define MAX_IOUT_MA 20  //ultravolt can go to 30  //photron says 20 ok

#define VOLTS_TO_DAC (0x0FFF/1000.0)  // 0-4095
#define MILLIAMPS_TO_DAC (0x0FFF/30.0)

//TODO Verify these aren't affected by setpoints
#define ADC_TO_VOLTS (1000.0/5.0)
#define ADC_TO_MILLIAMPS (30.0/5.0)

#define SEL_PIN_DELAY_US 25    //~10 I2C clocks

typedef unsigned int current_t;
typedef float currentf_t;
typedef unsigned int voltage_t;
typedef float voltagef_t;


class Ultravolt {
  
  public:
    Ultravolt(int enable_pin, int imode_pin, int csel_pin, unsigned int vlimit, unsigned int ilimit, 
              Adafruit_MCP4725 &vdac, Adafruit_MCP4725 &idac, Adafruit_TLA202x &adc);
    void begin();
    
    bool isCurrentMode();
    bool isVoltageMode();
    
    voltagef_t getVoltage();
    voltage_t getVoltageLimit();
    bool setVoltageLimit(voltage_t limit);
    
    currentf_t getCurrent();
    current_t getCurrentLimit();
    bool setCurrentLimit(current_t limit);
    
    bool isEnabled();
    
    void turnOff();
    void turnOn();
    void turnOn(current_t current);
    bool isOn();

    void monitorIgnition(uint32_t duration_ms);
  
  private:
    Adafruit_MCP4725 &_vdac;
    Adafruit_MCP4725 &_idac;
    Adafruit_TLA202x &_adc;
    voltage_t _vlimit;
    current_t _ilimit;
    int _enable_pin;
    int _imode_pin;
    int _csel_pin;

};
#endif
