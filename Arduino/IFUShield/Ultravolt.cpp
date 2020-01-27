#include "Ultravolt.h"



Ultravolt::Ultravolt(int imon_pin, int vmon_pin, int enable_pin, int vmode_pin, int imode_pin, 
                     int isel_pin, int vsel_pin, unsigned int vlimit, unsigned int ilimit, 
                     Adafruit_MCP4725 &dac)
                     : _enable_pin(enable_pin)
                     , _imon_pin(imon_pin)
                     , _vmon_pin(vmon_pin)
                     , _vmode_pin(vmode_pin)
                     , _imode_pin(imode_pin)
                     , _vsel_pin(vsel_pin)
                     , _isel_pin(isel_pin)
                     , _dac(dac)
 {
    _ilimit=ilimit > MAX_IOUT_MA ? MAX_IOUT_MA : ilimit;
    _vlimit=vlimit > MAX_VOUT_V ? MAX_VOUT_V : vlimit;
 }



Ultravolt::~Ultravolt() {
}

void Ultravolt::begin() {
  
    pinMode(_enable_pin, OUTPUT);
    digitalWrite(_enable_pin, LOW);
    
    pinMode(_imon_pin, INPUT); //analog
    digitalWrite(_imon_pin, LOW);
    pinMode(_vmon_pin, INPUT); //analog
    digitalWrite(_vmon_pin, LOW);


    //Pulled low (max 100mA sink) when in vmod or i mode
    pinMode(_vmode_pin, INPUT);
    digitalWrite(_vmode_pin, HIGH);
    pinMode(_imode_pin, INPUT);
    digitalWrite(_imode_pin, HIGH);
    
    digitalWrite(_isel_pin, LOW);
    pinMode(_isel_pin, OUTPUT);
    digitalWrite(_vsel_pin, LOW);
    pinMode(_vsel_pin, OUTPUT);
            
    turnOff();
}

bool Ultravolt::isCurrentMode() {
    return !digitalRead(_imode_pin); //pulled low in current mode
}

bool Ultravolt::isVoltageMode() {
    return !digitalRead(_vmode_pin); //pulled low in voltage mode
}

voltage_t Ultravolt::getVoltageLimit() {
    return _vlimit;
}

voltagef_t Ultravolt::getVoltage() {
    unsigned int ana=analogRead(_vmon_pin);
    //Serial.print("Read VANA of ");Serial.println(ana);
    return isEnabled() ? (voltagef_t) ((float)ana)*ADC_TO_VOLTS: 0.0;
}

bool Ultravolt::setVoltageLimit(voltage_t limit) {
    _vlimit = limit > MAX_VOUT_V ? MAX_VOUT_V : limit;
    digitalWrite(_vsel_pin, HIGH);
    delayMicroseconds(SEL_PIN_DELAY_US);
    uint16_t out = round(((float)_vlimit)*VOLTS_TO_ADC);
    //Serial.print("Set VDAC to ");Serial.println(out);
    _dac.setVoltage(out, false); //don't persist the voltage to eeprom
    delayMicroseconds(SEL_PIN_DELAY_US);
    digitalWrite(_vsel_pin, LOW);
}

current_t Ultravolt::getCurrentLimit() {
    return _ilimit;
}

currentf_t Ultravolt::getCurrent() {
    unsigned int ana=analogRead(_imon_pin);
    //Serial.print("Read IANA of ");Serial.println(ana);
    return isEnabled() ? (currentf_t) ((float)ana)*ADC_TO_MILLIAMPS: 0.0;
}

bool Ultravolt::setCurrentLimit(current_t limit) {
    _ilimit = limit > MAX_IOUT_MA ? MAX_IOUT_MA : limit;
    digitalWrite(_isel_pin, HIGH);
    delayMicroseconds(SEL_PIN_DELAY_US);
    uint16_t out = round(((float)_ilimit)*MILLIAMPS_TO_ADC);
    //Serial.print("Set IDAC to ");Serial.println(out);
    _dac.setVoltage(out, false); //don't persist to eeprom
    delayMicroseconds(SEL_PIN_DELAY_US);
    digitalWrite(_isel_pin, LOW);
}


void Ultravolt::turnOff() {
    digitalWrite(_enable_pin, LOW);
    
    digitalWrite(_isel_pin, HIGH);
    delayMicroseconds(SEL_PIN_DELAY_US);
    _dac.setVoltage(0, false); //don't persist to eeprom
    delayMicroseconds(SEL_PIN_DELAY_US);
    digitalWrite(_isel_pin, LOW);
    
    digitalWrite(_vsel_pin, HIGH);
    delayMicroseconds(SEL_PIN_DELAY_US);
    _dac.setVoltage(0, false); //don't persist to eeprom
    delayMicroseconds(SEL_PIN_DELAY_US);
    digitalWrite(_vsel_pin, LOW);
}

bool Ultravolt::isEnabled() {
    return digitalRead(_enable_pin);
}

bool Ultravolt::isOn() {
    return digitalRead(_enable_pin) && _ilimit>0 && _vlimit>0;
}

void Ultravolt::turnOn() {
    setVoltageLimit(_vlimit);
    setCurrentLimit(_ilimit);
    digitalWrite(_enable_pin, HIGH);
}

void Ultravolt::turnOn(current_t current) {
    if (current==0) { 
      turnOff();
      return;
    }
    setCurrentLimit(current);
    setVoltageLimit(_vlimit);
    digitalWrite(_enable_pin, HIGH);
}

void Ultravolt::monitorIgnition(uint32_t duration_ms) {
  //~1ms granularity as implemented
    unsigned long t;
    uint32_t duration_us=duration_ms*1000, delta=0;
    currentf_t i;
    voltagef_t v;
    bool im, vm;

    turnOff();
    delay(250);
    turnOn();
    
    while (duration_us>0) {
        t=micros();
        i=getCurrent();
        im=isCurrentMode();
        v=getVoltage();
        vm=isVoltageMode();

        Serial.print(t);
        Serial.print(", ");
        Serial.print(i);
        Serial.print(", ");
        Serial.print(v);
        Serial.print(", ");
        Serial.print(im);
        Serial.print(", ");
        Serial.println(vm);

        delta=micros()-t;
        duration_us = delta> duration_us ? 0: duration_us-delta;
    }
}
