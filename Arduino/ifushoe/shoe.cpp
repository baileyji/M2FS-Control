#import "shoe.h"
#include <stdio.h>



ShoeDrive::ShoeDrive(uint8_t pipe_servo_pin, uint8_t pipe_pot_pin, uint8_t height_servo_pin, uint8_t height_pot_pin, uint8_t height_sensor_pin) 
                     : _pipe_pin(pipe_servo_pin)
                     , _pipe_pot_pin(pipe_pot_pin)
                     , _height_pin(height_servo_pin)
                     , _height_pot_pin(height_pot_pin)
                     , _sensor_pin(height_sensor_pin) 
{
//  _pipe_pin=pipe_servo_pin;
//  _pipe_pot_pin=pipe_pot_pin;
//  _height_pin=height_servo_pin;
//  _height_pot_pin=height_pot_pin;
//  _sensor_pin=height_sensor_pin;
  _pipe_motor.attach(_pipe_pin, 1000, 2000);
  _height_motor.attach(_height_pin, 1000, 2000);
}

ShoeDrive::~ShoeDrive() {
  _pipe_motor.~Servo();
  _height_motor.~Servo(); 
}

void ShoeDrive::stop() {
  shoepos_t pos = getCurrentPosition();
  _pipe_motor.write(pos.pipe);
  _height_motor.write(pos.height);
}

void ShoeDrive::tellCurrentSlit() {
  char buf[32];
  int16_t pipe=analogRead(_pipe_pot_pin);
  int16_t height=analogRead(_height_pot_pin);
  sprintf(buf, "Pipe=%4d Height=%4d", pipe, pipe);
  Serial.println(buf);
}

int8_t ShoeDrive::getCurrentSlit(){return 1;} //0-6 or -1 


void ShoeDrive::tellCurrentPosition() {
  shoepos_t pos = getCurrentPosition();
  Serial.print(pos.pipe);Serial.print(", ");Serial.print(pos.height);
}

shoepos_t ShoeDrive::getCurrentPosition() {
  shoepos_t pos;
  pos.height = analogRead(_height_pot_pin);
  pos.pipe = analogRead(_pipe_pot_pin);
  return pos;
}

//Tells the position programed for a specifc slit
void ShoeDrive::tellSlitPosition(uint8_t slit) {
  Serial.print(_slitPositions[max(min(slit, N_SLIT_POS-1),0)]);
}

uint16_t ShoeDrive::getSlitPosition(uint8_t slit) {
  return _slitPositions[max(min(slit, N_SLIT_POS-1),0)];
}

bool ShoeDrive::moving(){return false;}
bool ShoeDrive::pipesMoving(){return false;}  //indicates literal movement
bool ShoeDrive::heightMoving(){return false;} //indicates literal movement
    
void ShoeDrive::defineSlitPosition(uint8_t slit, long position){
  if (slit>N_SLIT_POS-1) return;
  _slitPositions[slit] = position;  
}

void ShoeDrive::defineSlitPosition(uint8_t slit){
  if (slit>N_SLIT_POS-1) return;
  _slitPositions[slit] = _pipe_motor.read();    
}

void ShoeDrive::moveToSlit(uint8_t slit){}

void ShoeDrive::movePipe(uint8_t pos){
  _pipe_motor.write(pos);  
}

void ShoeDrive::moveHeight(uint8_t pos){
  _height_motor.write(pos);  
}

void ShoeDrive::lowerFibers(){}
void ShoeDrive::raiseFibers(){}
bool ShoeDrive::areFibersLowered(){}

void ShoeDrive::getEEPROMInfo(uint16_t data[N_SLIT_POS+N_HEIGHT_POS]) {
  for (uint8_t i=0; i<N_SLIT_POS; i++) data[i]=_slitPositions[i];
  for (uint8_t i=0; i<N_HEIGHT_POS; i++) data[i+N_SLIT_POS]=_heightPositions[i];
}

void ShoeDrive::restoreEEPROMInfo(uint16_t data[N_SLIT_POS+N_HEIGHT_POS]) {
  for (uint8_t i=0; i<N_SLIT_POS; i++) _slitPositions[i]=data[i];
  for (uint8_t i=0; i<N_HEIGHT_POS; i++) _heightPositions[i]=data[i+N_SLIT_POS];
}

void ShoeDrive::run(){
  //update analong to monitor movement  
}
