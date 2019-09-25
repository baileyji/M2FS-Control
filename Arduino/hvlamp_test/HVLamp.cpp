#include "HVLamp.h"

Adafruit_MCP4725 vdac, idac;  //must call dac.begin(addr) addr=0x62 & 0x63?

HVLamp::HVLamp() {
    _begun=false;
    _ilimit=0;
    _vlimit=0;
}

HVLamp::~HVLamp() {
}

void HVLamp::begin() {

    if (_begun) return;
    
    //pin modes
    pinMode(PIN_ENABLE, OUTPUT);
    digitalWrite(PIN_ENABLE, LOW);
    
    pinMode(PIN_IMON, INPUT); //analog
    pinMode(PIN_VMON, INPUT); //analog
    digitalWrite(PIN_VMON, LOW);
    digitalWrite(PIN_IMON, LOW);
    
    pinMode(PIN_VMODE, INPUT);
    pinMode(PIN_IMODE, INPUT);
    digitalWrite(PIN_IMODE, HIGH);
    digitalWrite(PIN_VMODE, HIGH);
    
    //Startup
    idac.begin(IDAC_ADDR);
    vdac.begin(VDAC_ADDR);
    
    turnOff();
    
    _begun=true;
}


bool HVLamp::isCurrentMode() {
    return !digitalRead(PIN_IMODE); //pulled low in current mode
}

bool HVLamp::isVoltageMode() {
    return !digitalRead(PIN_VMODE); //pulled low in voltage mode
}

voltage_t HVLamp::getVoltageLimit() {
    return _vlimit;
}

voltage_t HVLamp::getVoltage() {
    Serial.print("Read a voltage of (ADC units)");Serial.println(analogRead(PIN_VMON));
    return isEnabled() ? (voltage_t) analogRead(PIN_VMON)*ADC_TO_VOLTS: 0;
}

bool HVLamp::setVoltage(voltage_t x) {
    x = x > MAX_V_LIM ? MAX_V_LIM : x;
    x = x > MAX_VOUT_V ? MAX_VOUT_V : x;
    _vlimit = x;
    Serial.print("Setting voltage to (DAC units)");Serial.println(x*VOLTS_TO_ADC);
    vdac.setVoltage(x*VOLTS_TO_ADC, false); //don't persist the voltage to eeprom
}

voltage_t HVLamp::getCurrentLimit() {
    return _ilimit;
}

current_t HVLamp::getCurrent() {
    Serial.print("Read a current of (ADC units)");Serial.println(analogRead(PIN_IMON));
    return isEnabled() ? (current_t) analogRead(PIN_IMON)*ADC_TO_MILLIAMPS: 0;
}

bool HVLamp::setCurrent(current_t x) {
    x = x > MAX_I_LIM ? MAX_I_LIM : x;
    x = x > MAX_IOUT_MA ? MAX_IOUT_MA : x;
    _ilimit = x;
    Serial.print("Setting current to (DAC units)");Serial.println(x*MILLIAMPS_TO_ADC);
    idac.setVoltage(x*MILLIAMPS_TO_ADC, false); //don't persist to eeprom
}

bool HVLamp::isEnabled() {
    return digitalRead(PIN_ENABLE);
}

lampstatus_t HVLamp::getActiveLamp() {
  lamp_t lamp=0;
  return {lamp, getVoltage(), getCurrent()};
}

void HVLamp::turnOff() {
    digitalWrite(PIN_ENABLE, LOW);
    setVoltage(0);
    setCurrent(0);
}

bool HVLamp::isLampEnabled(lamp_t lamp) {
    return true;
}


void HVLamp::turnOn(lamp_t lamp) {
    turnOn(lamp, 8);
}

void HVLamp::turnOn(lamp_t lamp, current_t current) {
    turnOff();
//    setVoltage(MAX_V_LIM);
    vdac.setVoltage(4095, false);
    setCurrent(current);
    delayMicroseconds(750); //per switch time in COTO relay datasheet
    digitalWrite(PIN_ENABLE, HIGH);
}


void HVLamp::monitorIgnition(lamp_t lamp, current_t current, uint32_t duration) {
    unsigned long t;
    current_t i;
    voltage_t v;
    bool im, vm;

    if (lamp==NONE_LAMP) return;
    
    turnOn(lamp, current);
    t=micros();
    
    while (duration>0) {
        i=getCurrent();
        im=isCurrentMode();
        v=getVoltage();
        vm=isVoltageMode();
        
        Serial.print(i);
        Serial.print(",");
        Serial.print(v);
        Serial.print(",");
        Serial.print(im);
        Serial.print(",");
        Serial.println(vm);

        while (micros()-t < 1000) t=micros();
        duration--;
    }
}
