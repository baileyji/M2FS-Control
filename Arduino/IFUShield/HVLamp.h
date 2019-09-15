#ifndef __HVLamp_H__
#define __HVLamp_H__

#if ARDUINO < 100
#include <WProgram.h>
#else  // ARDUINO
#include <Arduino.h>
#endif  // ARDUINO

#include <Adafruit_MCP4725.h>


#define VDAC_ADDR 0x62
#define IDAC_ADDR 0x63

#define MAX_VOUT_V 1000
#define MAX_IOUT_MA 30
#define MAX_V_LIM 800
#define MAX_I_LIM 10

#define VOLTS_TO_ADC 0x0FFF/MAX_VOUT_V
#define MILLIAMPS_TO_ADC 0x0FFF/MAX_IOUT_MA

//TODO Verify these aren't affected by setpoints
#define ADC_TO_VOLTS 1000/1023.0
#define ADC_TO_MILLIAMPS 30/1023.0

#define N_LAMPS 3

//TODO switch from 1 HV supply + relays

typedef enum {THXE_LAMP=0, BENEAR_LAMP=1, LIHE_LAMP=2, NONE_LAMP=3, MULTIPLE_LAMP=4} lamp_t;

typedef unsigned int current_t;
typedef unsigned int voltage_t;

typedef struct {lamp_t lamp; current_t current; voltage_t voltage;} lampstatus_t;

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

class HVLamp
{

  public:
    HVLamp();
    ~HVLamp();
    void begin();
    
    bool isCurrentMode();
    bool isVoltageMode();
    
    voltage_t getVoltage();
    voltage_t getVoltageLimit();
    bool setVoltage(voltage_t x);
    current_t getCurrent();
    current_t getCurrentLimit();
    bool setCurrent(current_t x);
    
    bool isEnabled();
    
    void turnOff();
    void turnOn(lamp_t lamp);
    void turnOn(lamp_t lamp, current_t current);
    lampstatus_t getActiveLamp();
    bool isLampEnabled(lamp_t lamp);

    void monitorIgnition(lamp_t lamp, current_t current, uint32_t duration);
  
  private:
    bool _begun;
    voltage_t _vlimit;
    current_t _ilimit;

};
#endif
