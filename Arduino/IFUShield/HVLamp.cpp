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
    
    digitalWrite(PIN_THAR_SEL, LOW);
    digitalWrite(PIN_THNE_SEL, LOW);
    digitalWrite(PIN_NE_SEL, LOW);
    digitalWrite(PIN_HG_SEL, LOW);
    digitalWrite(PIN_HE_SEL, LOW);
    
    pinMode(PIN_HG_SEL, OUTPUT);
    pinMode(PIN_HE_SEL, OUTPUT);
    pinMode(PIN_NE_SEL, OUTPUT);
    pinMode(PIN_THNE_SEL, OUTPUT);
    pinMode(PIN_THAR_SEL, OUTPUT);
    
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
    return (voltage_t) analogRead(PIN_VMON)*ADC_TO_VOLTS;
}

bool HVLamp::setVoltage(voltage_t x) {
    x = x > MAX_V_LIM ? MAX_V_LIM : x;
    x = x > MAX_VOUT_V ? MAX_VOUT_V : x;
    _vlimit = x;
    vdac.setVoltage(x*VOLTS_TO_ADC, false); //don't persist the voltage to eeprom
}

voltage_t HVLamp::getCurrentLimit() {
    return _ilimit;
}

current_t HVLamp::getCurrent() {
    return (current_t) analogRead(PIN_IMON)*ADC_TO_MILLIAMPS;
}

bool HVLamp::setCurrent(current_t x) {
    x = x > MAX_I_LIM ? MAX_I_LIM : x;
    x = x > MAX_IOUT_MA ? MAX_IOUT_MA : x;
    _ilimit = x;
    idac.setVoltage(x*MILLIAMPS_TO_ADC, false); //don't persist to eeprom
}

bool HVLamp::isEnabled() {
    return digitalRead(PIN_ENABLE);
}

lampstatus_t HVLamp::getActiveLamp() {
  lamp_t lamp;
  if (digitalRead(PIN_THAR_SEL)) {
    lamp = THAR_LAMP;
  } else if (digitalRead(PIN_THNE_SEL)) {
    lamp = THNE_LAMP;
  } else if (digitalRead(PIN_NE_SEL)) {
    lamp = NE_LAMP;
  } else if (digitalRead(PIN_HG_SEL)) {
    lamp = HG_LAMP;
  } else {
    lamp = HE_LAMP;
  }
  return {lamp, getVoltage(), getCurrent()};
}

void HVLamp::turnOff() {
    digitalWrite(PIN_ENABLE, LOW);
    setVoltage(0);
    setCurrent(0);
    digitalWrite(PIN_THAR_SEL, LOW);
    digitalWrite(PIN_THNE_SEL, LOW);
    digitalWrite(PIN_NE_SEL, LOW);
    digitalWrite(PIN_HG_SEL, LOW);
    digitalWrite(PIN_HE_SEL, LOW);
    delayMicroseconds(500); //per release in COTO relay datasheet
}

bool HVLamp::isLampEnabled(lamp_t lamp) {
      if (lamp==NONE_LAMP) {
        return !(digitalRead(PIN_THAR_SEL)||digitalRead(PIN_THNE_SEL)||digitalRead(PIN_NE_SEL)||
                 digitalRead(PIN_HG_SEL)||digitalRead(PIN_HE_SEL));
      }
      uint8_t pin;
      switch (lamp) {
        case THAR_LAMP:
            pin=PIN_THAR_SEL;
            break;
        case THNE_LAMP:
            pin=PIN_THNE_SEL;
            break;
        case HG_LAMP:
            pin=PIN_HG_SEL;
            break;
        case NE_LAMP:
            pin=PIN_NE_SEL;
            break;
        case HE_LAMP:
            pin=PIN_HE_SEL;
            break;
        default:
            return false;
    }
    return digitalRead(pin);
}


void HVLamp::turnOn(lamp_t lamp) {
    turnOn(lamp, 8);
}

void HVLamp::turnOn(lamp_t lamp, current_t current) {
    turnOff();
    switch (lamp) {
        case THAR_LAMP:
            digitalWrite(PIN_THAR_SEL, HIGH);
            setVoltage(MAX_V_LIM);
            setCurrent(current);
            break;
        case THNE_LAMP:
            digitalWrite(PIN_THNE_SEL, HIGH);
            setVoltage(MAX_V_LIM);
            setCurrent(current);
            break;
        case HG_LAMP:
            digitalWrite(PIN_HG_SEL, HIGH);
            setVoltage(MAX_V_LIM);
            setCurrent(current);
            break;
        case NE_LAMP:
            digitalWrite(PIN_NE_SEL, HIGH);
            setVoltage(MAX_V_LIM);
            setCurrent(current);
            break;
        case HE_LAMP:
            digitalWrite(PIN_HE_SEL, HIGH);
            setVoltage(MAX_V_LIM);
            setCurrent(current);
            break;
        default:
            return;
    }
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
