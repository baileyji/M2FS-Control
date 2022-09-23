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


UltravoltMultilamp::UltravoltMultilamp(int enable_pin, int thxe_pin, int benear_pin, int lihe_pin,
              unsigned int vlimit, unsigned int ilimit, SoftWire &i2c)
                     : _enable_pin(enable_pin)
                     , _i2c(i2c)
{
    _ilimit=ilimit > MAX_IOUT_MA ? MAX_IOUT_MA : ilimit;
    _vlimit=vlimit > MAX_VOUT_V ? MAX_VOUT_V : vlimit;
    _lamp_sel_pin[0]=thxe_pin;
    _lamp_sel_pin[1]=benear_pin;
    _lamp_sel_pin[2]=lihe_pin;
}

void UltravoltMultilamp::begin() {
  
    pinMode(_enable_pin, OUTPUT);
    digitalWrite(_enable_pin, LOW);
    for (int i=0; i<3;i++) {
      pinMode(_lamp_sel_pin[i], OUTPUT);
      digitalWrite(_lamp_sel_pin[i], LOW);
    }
    turnOff();
}

bool UltravoltMultilamp::isCurrentMode() {
    return false;
}

bool UltravoltMultilamp::isVoltageMode() {
    return false;
}

voltage_t UltravoltMultilamp::getVoltageLimit() {
    return _vlimit;
}

voltagef_t UltravoltMultilamp::getVoltage() {
    return isEnabled() ? (voltagef_t) ((float)_vlimit): 0.0;
}

bool UltravoltMultilamp::setVoltageLimit(voltage_t limit) {
    _vlimit = limit > MAX_VOUT_V ? MAX_VOUT_V : limit;
    uint16_t out = round(((float)_vlimit)*VOLTS_TO_ADC);
    Serial.print("Set VDAC to ");Serial.println(out);
    _mcp4725SetVoltage(LAMP_4_V_ADDR, out, false);
    delay(1);
}

current_t UltravoltMultilamp::getCurrentLimit() {
    return _ilimit;
}

currentf_t UltravoltMultilamp::getCurrent() {
    return isEnabled() ? (currentf_t) ((float) _ilimit): 0.0;
}

bool UltravoltMultilamp::setCurrentLimit(current_t limit) {
    _ilimit = limit > MAX_IOUT_MA ? MAX_IOUT_MA : limit;
    uint16_t out = round(((float)_ilimit)*MILLIAMPS_TO_ADC);
//    Serial.print("Set IDAC to ");Serial.println(out);
    _mcp4725SetVoltage(LAMP_4_I_ADDR, out, false);
    delay(1);
}

void UltravoltMultilamp::turnOff() {
    digitalWrite(_enable_pin, LOW);    
    for (int i=0; i<3;i++) 
      digitalWrite(_lamp_sel_pin[i], LOW);
    _lamp=255;
    _mcp4725SetVoltage(LAMP_4_I_ADDR, 0, false);
    _mcp4725SetVoltage(LAMP_4_V_ADDR, 0, false);
}

bool UltravoltMultilamp::isEnabled() {
    return digitalRead(_enable_pin);
}

bool UltravoltMultilamp::isOn() {
    return digitalRead(_enable_pin) && _ilimit>0 && _vlimit>0;
}

uint8_t UltravoltMultilamp::getSelectedLamp() {
//  for (int i=0; i<2;i++) 
//      if (digitalRead(_lamp_sel_pin[i]))
//        return i;
//  return 255;
  return _lamp;
}

bool UltravoltMultilamp::_selectLamp(uint8_t lamp) {
    if (lamp>2) return false;
    if (lamp!=_lamp) {
        turnOff();
        delay(5);
    }
    digitalWrite(_lamp_sel_pin[lamp], HIGH);
    _lamp=lamp;
    return true;
}

void UltravoltMultilamp::turnOn(current_t current, uint8_t lamp) {
    if (current==0) { 
      turnOff();
      return;
    }
    if (!_selectLamp(lamp)) 
      return;
    setCurrentLimit(current);
    setVoltageLimit(_vlimit);
    delay(1);
    digitalWrite(_enable_pin, HIGH);
}



/**************************************************************************/
/*!
    @brief  Sets the output voltage to a fraction of source vref.  (Value
            can be 0..4095)

    @param[in]  output
                The 12-bit value representing the relationship between
                the DAC's input voltage and its output voltage.
    @param[in]  writeEEPROM
                If this value is true, 'output' will also be written
                to the MCP4725's internal non-volatile memory, meaning
                that the DAC will retain the current voltage output
                after power-down or reset.
    @param i2c_frequency What we should set the I2C clock to when writing
    to the DAC, defaults to 400 KHz
    @returns True if able to write the value over I2C
*/
/**************************************************************************/
#define MCP4725_I2CADDR_DEFAULT (0x62) ///< Default i2c address
#define MCP4725_CMD_WRITEDAC (0x40)    ///< Writes data to the DAC
#define MCP4725_CMD_WRITEDACEEPROM (0x60) ///< Writes data to the DAC and the EEPROM (persisting the assigned
bool UltravoltMultilamp::_mcp4725SetVoltage(uint8_t addr, uint16_t output, bool writeEEPROM) {

  uint8_t packet[3];
  packet[0] = writeEEPROM ? MCP4725_CMD_WRITEDACEEPROM: MCP4725_CMD_WRITEDAC;
  packet[1] = output / 16;        // Upper data bits (D11.D10.D9.D8.D7.D6.D5.D4)
  packet[2] = (output % 16) << 4; // Lower data bits (D3.D2.D1.D0.x.x.x.x)

  _i2c.beginTransmission(addr);
  if (_i2c.write(packet, 3) != 3) {
//    Serial.println("Write packet failed");
    return false;
  }
  if (_i2c.endTransmission(true) != 0) {
//    Serial.println("end transmission failed");
    return false;
  }
  return true;
}
