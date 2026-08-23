#include "Ultravolt.h"



Ultravolt::Ultravolt(int enable_pin, int imode_pin, int csel_pin, unsigned int vlimit, unsigned int ilimit, 
                     Adafruit_MCP4725 &vdac, Adafruit_MCP4725 &idac, Adafruit_TLA202x &adc)
                     : _enable_pin(enable_pin)
                     , _csel_pin(csel_pin)
                     , _imode_pin(imode_pin)
                     , _vdac(vdac)
                     , _idac(idac)
                     , _adc(adc)  //ain0=imon ain1=vmon
 {
    _ilimit=ilimit > MAX_IOUT_MA ? MAX_IOUT_MA : ilimit;
    _vlimit=vlimit > MAX_VOUT_V ? MAX_VOUT_V : vlimit;
 }


void Ultravolt::begin() {
  
    pinMode(_enable_pin, OUTPUT);
    pinMode(_csel_pin, OUTPUT);
    pinMode(_imode_pin, INPUT_PULLUP);      //Pulled low (max 100mA sink) when in vmod or i mode

    digitalWrite(_enable_pin, LOW);

    digitalWrite(_csel_pin, HIGH);
    delayMicroseconds(SEL_PIN_DELAY_US);

    _adc.begin(0x49);
    _adc.setMode(TLA202x_MODE_ONE_SHOT);
    _adc.setRange(TLA202x_RANGE_6_144_V);
    _adc.setDataRate(TLA202x_RATE_1600_SPS);
    _adc.setMux(TLA202x_MUX_AIN0_GND);

    _vdac.setVoltage(0, false);
    _idac.setVoltage(0, false);

    digitalWrite(_csel_pin, LOW);

    turnOff();
}

bool Ultravolt::isCurrentMode() {
    return !digitalRead(_imode_pin); //pulled low in current mode
}

bool Ultravolt::isVoltageMode() {
    return !isCurrentMode();
}

voltage_t Ultravolt::getVoltageLimit() {
    return _vlimit;
}

voltagef_t Ultravolt::getVoltage() {
    float ana;

    if (!isEnabled()) {
        return 0.0;
    }

    digitalWrite(_csel_pin, HIGH);
    delayMicroseconds(SEL_PIN_DELAY_US);
    ana = _adc.readOnce(TLA202x_CHANNEL_1);
    digitalWrite(_csel_pin, LOW);
    return (voltagef_t) ana * ADC_TO_VOLTS;
}

bool Ultravolt::setVoltageLimit(voltage_t limit) {
    _vlimit = limit > MAX_VOUT_V ? MAX_VOUT_V : limit;
    digitalWrite(_csel_pin, HIGH);
    delayMicroseconds(SEL_PIN_DELAY_US);

    uint16_t out = round(VOLTS_TO_DAC * (float) _vlimit);

    //Serial.print("Set VDAC to ");Serial.println(out);
    _vdac.setVoltage(out, false); //don't persist the voltage to eeprom

    delayMicroseconds(SEL_PIN_DELAY_US);
    digitalWrite(_csel_pin, LOW);
}

current_t Ultravolt::getCurrentLimit() {
    return _ilimit;
}

currentf_t Ultravolt::getCurrent() {
    float ana; 
    if (!isEnabled()) {
        return 0.0;
    }

    digitalWrite(_csel_pin, HIGH);
    delayMicroseconds(SEL_PIN_DELAY_US);
    ana = _adc.readOnce(TLA202x_CHANNEL_0);
    digitalWrite(_csel_pin, LOW);
    // Serial.print("get IDAC ");Serial.print(ana);Serial.print(".  ");Serial.println((currentf_t) ana * ADC_TO_MILLIAMPS);
    return (currentf_t) ana * ADC_TO_MILLIAMPS;
}

bool Ultravolt::setCurrentLimit(current_t limit) {
    _ilimit = limit > MAX_IOUT_MA ? MAX_IOUT_MA : limit;
    digitalWrite(_csel_pin, HIGH);
    delayMicroseconds(SEL_PIN_DELAY_US);

    uint16_t out = round(((float)_ilimit)*MILLIAMPS_TO_DAC);
    // Serial.print("Set IDAC to ");Serial.println(out);
    _idac.setVoltage(out, false); //don't persist to eeprom

    delayMicroseconds(SEL_PIN_DELAY_US);
    digitalWrite(_csel_pin, LOW);
}


void Ultravolt::turnOff() {
    digitalWrite(_enable_pin, LOW);
    
    digitalWrite(_csel_pin, HIGH);
    delayMicroseconds(SEL_PIN_DELAY_US);
    _vdac.setVoltage(0, false); //don't persist to eeprom
    _idac.setVoltage(0, false); //don't persist to eeprom
    delayMicroseconds(SEL_PIN_DELAY_US);
    digitalWrite(_csel_pin, LOW);

}

bool Ultravolt::isEnabled() {
    return digitalRead(_enable_pin);
}

bool Ultravolt::isOn() {
    return digitalRead(_enable_pin) && _ilimit>0 && _vlimit>0;
}

void Ultravolt::turnOn() {
    turnOn(_ilimit);
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

        Serial.print(t);
        Serial.print(", ");
        Serial.print(i);
        Serial.print(", ");
        Serial.print(v);
        Serial.print(", ");
        Serial.print(im);

        delta=micros()-t;
        duration_us = delta> duration_us ? 0: duration_us-delta;
    }
}
