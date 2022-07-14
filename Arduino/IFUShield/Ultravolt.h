#ifndef __Ultravolt_H__
#define __Ultravolt_H__

#if ARDUINO < 100
#include <WProgram.h>
#else  // ARDUINO
#include <Arduino.h>
#endif  // ARDUINO
#include <SoftWire.h>
#include <Adafruit_MCP4725.h>

#define LAMP_4_I_ADDR 0x63
#define LAMP_4_V_ADDR 0x62

#define MAX_VOUT_V 1000  //Ultravolt can go to 1000
#define MAX_IOUT_MA 20  //ultravolt can go to 30  //photron says 20 ok

#define VOLTS_TO_ADC (0x0FFF/1000.0)  // 0-4095
#define MILLIAMPS_TO_ADC (0x0FFF/30.0)

//TODO Verify these aren't affected by setpoints
#define ADC_TO_VOLTS (1000/1023.0)
#define ADC_TO_MILLIAMPS (30/1023.0)

#define SEL_PIN_DELAY_US 25    //~10 I2C clocks

typedef unsigned int current_t;
typedef float currentf_t;
typedef unsigned int voltage_t;
typedef float voltagef_t;

class UltravoltMultilamp {
  public:
    UltravoltMultilamp(int enable_pin, int thxe_pin, int benear_pin, int lihe_pin, 
              unsigned int vlimit, unsigned int ilimit, SoftWire &i2c);
    void begin();
    bool isCurrentMode();
    bool isVoltageMode();
    
    voltagef_t getVoltage();
    voltage_t getVoltageLimit();
    bool setVoltageLimit(voltage_t limit);
    
    currentf_t getCurrent();
    current_t getCurrentLimit();
    uint8_t getSelectedLamp();  //255 if none selected
    bool setCurrentLimit(current_t limit);
    
    bool isEnabled();
    
    void turnOff();
    void turnOn(current_t current, uint8_t lamp);
    bool isOn();
    
  private:
    SoftWire &_i2c;
    bool _mcp4725SetVoltage(uint8_t addr, uint16_t output, bool writeEEPROM);
    bool _selectLamp(uint8_t lamp);
    voltage_t _vlimit;
    current_t _ilimit;
    int _enable_pin;
    int _lamp_sel_pin[3];
    uint8_t _lamp;
};

class Ultravolt {
  
  public:
    Ultravolt(int imon_pin, int vmon_pin, int enable_pin, int vmode_pin, int imode_pin, 
              int isel_pin, int vsel_pin, unsigned int vlimit, unsigned int ilimit, Adafruit_MCP4725 &dac);
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
