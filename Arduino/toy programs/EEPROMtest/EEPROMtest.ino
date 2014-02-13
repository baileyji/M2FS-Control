#include <EEPROM.h>

void setup() {
  Serial.begin(115200);
  
  EEPROM.write(0,81);
  Serial.println((int) EEPROM.read(0));
  EEPROM.write(1,231);
  Serial.println((int) EEPROM.read(1));
  
  int32_t a=124791, b=0;
  Serial.print("Val in EEPROM:");Serial.println((int32_t)EEPROMread32bitval(0));

  Serial.print("Wrt to EEPROM:");Serial.println(a);
  EEPROMwrite32bitval(0, a);
  Serial.print("Val in EEPROM:");Serial.println((int32_t)EEPROMread32bitval(0));
  
  a=-1932791;
  
  Serial.print("Wrt to EEPROM:");Serial.println(a);
  EEPROMwrite32bitval(0, a);
  Serial.print("Val in EEPROM:");Serial.println((int32_t)EEPROMread32bitval(0));
 
}

void loop(){}
/*
void EEPROMwrite32bitval(uint16_t addr, uint32_t val) {
  uint8_t out;
  
  out=(uint8_t) ((val>>0)  & 0x000000FF);
  //Serial.print("Writing byte:");Serial.println(out,BIN);
  //EEPROM.write(addr,0);
  EEPROM.write(addr++, out);
  
  out=(uint8_t) ((val>>8)  & 0x000000FF);
  //Serial.print("Writing byte:");Serial.println(out,BIN);
  //EEPROM.write(addr,0);
  EEPROM.write(addr++, out);
  
  out= (uint8_t) ((val>>16) & 0x000000FF);
  //Serial.print("Writing byte:");Serial.println(out,BIN);
  //EEPROM.write(addr,0);
  EEPROM.write(addr++, out);
  
  out= (uint8_t) ((val>>24) & 0x000000FF);
  //Serial.print("Writing byte:");Serial.println(out,BIN);
  //EEPROM.write(addr,0);
  EEPROM.write(addr,out);
  
  Serial.print("Wrote        :");Serial.println(val,BIN);
}


uint32_t EEPROMread32bitval(uint16_t addr) {
  uint32_t returnVal=0;
  uint8_t in;
  //Serial.print("uint32 start:");Serial.println(returnVal,BIN);

  in=EEPROM.read(addr++);
  //Serial.print("Reading byte:");Serial.println(in,BIN);
  returnVal |= in;
  //Serial.print("uint32 now  :");Serial.println(returnVal,BIN);
  
  in=EEPROM.read(addr++);
  //Serial.print("Reading byte:");Serial.println(in,BIN); 
  returnVal |= ((uint32_t)in)<<8;
  //Serial.print("uint32 now  :");Serial.println(returnVal,BIN);
  
  in=EEPROM.read(addr++);
  //Serial.print("Reading byte:");Serial.println(in,BIN);
  returnVal |= ((uint32_t)in)<<16;
  //Serial.print("uint32 now  :");Serial.println(returnVal,BIN);
  
  in=EEPROM.read(addr++);
  //Serial.print("Reading byte:");Serial.println(in,BIN);
  returnVal |= ((uint32_t)in)<<24;
  //Serial.print("uint32 now  :");Serial.println(returnVal,BIN);
  
  Serial.print("Read         :");Serial.println(returnVal,BIN);
  return returnVal;
}
*/
void EEPROMwrite32bitval(uint16_t addr, uint32_t val) {
  EEPROM.write(addr++, (uint8_t) ((val)     & 0x000000FF));
  EEPROM.write(addr++, (uint8_t) ((val>>8)  & 0x000000FF));
  EEPROM.write(addr++, (uint8_t) ((val>>16) & 0x000000FF));
  EEPROM.write(addr,   (uint8_t) ((val>>24) & 0x000000FF));
}
uint32_t EEPROMread32bitval(uint16_t addr) {
  uint32_t returnVal=0;
  returnVal |= ((uint32_t) EEPROM.read(addr++));
  returnVal |= ((uint32_t) EEPROM.read(addr++)) <<8;
  returnVal |= ((uint32_t) EEPROM.read(addr++)) <<16;
  returnVal |= ((uint32_t) EEPROM.read(addr))   <<24;
  return returnVal;
}
