#import "shoe.h"


ShoeDrive::ShoeDrive(uint8_t pipe_servo_pin, uint8_t pipe_pot_pin, uint8_t height_servo_pin, uint8_t height_pot_pin, uint8_t height_sensor_pin, Servo *p, Servo *h)
                     : _pipe_pin(pipe_servo_pin)
                     , _pipe_pot_pin(pipe_pot_pin)
                     , _height_pin(height_servo_pin)
                     , _height_pot_pin(height_pot_pin)
                     , _sensor_pin(height_sensor_pin)
                     , _pipe_filter(1,10)     //about 10 samples
                     , _height_filter(1,10)
                     , _pipe_motor(p)
                     , _height_motor(h)
{

}

void ShoeDrive::init() {
  _pipe_motor->attach(_pipe_pin, (uint16_t) 1000, (uint16_t) 2000);
  _height_motor->attach(_height_pin, (uint16_t) 1000, (uint16_t) 2000);


  _feedback_pos.pipe=_pipe_filter.filter(analogRead(_pipe_pot_pin));
  _feedback_pos.height=_height_filter.filter(analogRead(_height_pot_pin));
  
  _positionTolerance = 6;  // about 120um, 20mm/1023 per unit
  _desiredSlit=0;
  _timeLastPipeMovement=0;
  _timeLastHeightMovement=0;
  _moveInProgress=0;
  
}

ShoeDrive::~ShoeDrive() {
//  _pipe_motor.~Servo();
//  _height_motor.~Servo(); 
}

uint8_t ShoeDrive::_currentPipeIndex() {
  uint16_t pos=getCurrentPosition().pipe;
  for (uint8_t i;i<N_SLIT_POS;i++)
    if (abs(pos - _pipePositions[i]) < _positionTolerance) 
      return i;
  return 0xff;
}

void ShoeDrive::stop() {
  shoepos_t pos = getCurrentPosition();
  _pipe_motor->write(pos.pipe);
  _height_motor->write(pos.height);
  _moveInProgress=false;
}

uint8_t ShoeDrive::getCurrentSlit(){ //0-5 or 0xFF = INTERMEDIATE, 0xFE = MOVING
  uint8_t ndx;
  if (_moveInProgress) return 0xFE;
  ndx = _currentPipeIndex();
  if (!fibersAreUp() || ndx==0xFF) return 0xFF;
  else return ndx;
} 

void ShoeDrive::tellCurrentSlit() {
  uint8_t slit = getCurrentSlit();
  if (slit==0xFF) Serial.print(F("INTERMEDIATE"));
  else if (slit==0xFE) Serial.print(F("MOVING"));
  else Serial.print(slit);
}

shoepos_t ShoeDrive::getCurrentPosition() {
  return _feedback_pos;
}

shoepos_t ShoeDrive::getCommandedPosition() {
  shoepos_t pos;
  pos.pipe = _pipe_motor->read();
  pos.height = _height_motor->read();
  return pos;
}

void ShoeDrive::tellCurrentPosition() {
  Serial.print(_feedback_pos.pipe);Serial.print(", ");Serial.print(_feedback_pos.height);
}

uint16_t ShoeDrive::getSlitPosition(uint8_t slit) {
  return _pipePositions[max(min(slit, N_SLIT_POS-1),0)];
}

//Tells the position programed for a specifc slit
void ShoeDrive::tellSlitPosition(uint8_t slit) {
  Serial.print(getSlitPosition(slit));
}

bool ShoeDrive::moving() {
  return _moveInProgress>0;
}

bool ShoeDrive::pipeMoving() { //indicates literal movement
  return millis()-_timeLastPipeMovement < MOVING_TIMEOUT_MS;
}  

bool ShoeDrive::heightMoving() { //indicates literal movement
  return millis()-_timeLastHeightMovement < MOVING_TIMEOUT_MS;
}
    
void ShoeDrive::defineSlitPosition(uint8_t slit, uint16_t pos){
  if (slit>N_SLIT_POS-1) return;
  _pipePositions[slit] = pos;  
}

void ShoeDrive::defineSlitPosition(uint8_t slit){
  if (slit>N_SLIT_POS-1) return;
  _pipePositions[slit] = _pipe_motor->read();    
}

void ShoeDrive::moveToSlit(uint8_t slit) { ///kick off a move
  if (slit>N_SLIT_POS-1) return;
  if (_desiredSlit!=slit) {
    _moveInProgress=10;
    _desiredSlit=slit;
  }
}

void ShoeDrive::movePipe(uint16_t pos){
  Serial.print("Moving pipe to ");Serial.println(pos);
  _pipe_motor->write(pos);  
}

void ShoeDrive::moveHeight(uint16_t pos){
  _height_motor->write(pos);  
}


bool ShoeDrive::safeToMovePipes() {
  return _feedback_pos.height<PIPE_CLEARANCE_HEIGHT && _height_motor->read()==_heightPositions[DOWN_NDX];
}

bool ShoeDrive::fibersAreUp() {
  return _height_motor->read()==_heightPositions[UP_NDX] && !heightMoving();//&& digitalRead(_sensor_pin);
}

void ShoeDrive::getEEPROMInfo(shoecfg_t &data) {
  for (uint8_t i=0; i<N_SLIT_POS; i++) data.pipe_pos[i]=_pipePositions[i];
  for (uint8_t i=0; i<N_HEIGHT_POS; i++) data.height_pos[i]=_heightPositions[i];
}

void ShoeDrive::restoreEEPROMInfo(shoecfg_t data) {
  for (uint8_t i=0; i<N_SLIT_POS; i++) _pipePositions[i]=data.pipe_pos[i];
  for (uint8_t i=0; i<N_HEIGHT_POS; i++) _heightPositions[i]=data.height_pos[i];
}

void ShoeDrive::run(){

  // Monitor position
  shoepos_t pos;
  uint32_t t =millis();
  pos.pipe=_pipe_filter.filter(analogRead(_pipe_pot_pin));
  pos.height=_height_filter.filter(analogRead(_height_pot_pin));
  
  if (pos.pipe!=_feedback_pos.pipe) {
    _feedback_pos.pipe = pos.pipe;
    _timeLastPipeMovement=t;
  }
  
  if (pos.height!=_feedback_pos.height) {
    _feedback_pos.height = pos.height;
    _timeLastHeightMovement=t;
  }

  //Execute move: lower, wait, move pipes, wait, raise, wait, done
  bool _heightMoving = heightMoving();
  bool _pipeMoving = pipeMoving();
  
  switch (_moveInProgress) {
    case 10: //new move, lower cassette
      _height_motor->write(_heightPositions[DOWN_NDX]);
      _moveInProgress--;
      errors=0;
      break;
    case 9: // move pipes
      if (safeToMovePipes()) {
        _pipe_motor->write(_pipePositions[_desiredSlit]);
        _moveInProgress--;
        errors=0;
      } else if (!_heightMoving) errors|=E_HEIGHTSTALL;
      break;
    case 8: // raise cassette
      if (!_pipeMoving && _currentPipeIndex()==_desiredSlit) {
        _height_motor->write(_heightPositions[UP_NDX]);
        _moveInProgress--;
        errors=0;
      } else if (!_pipeMoving) errors|=E_PIPESTALL;
      break;
    case 7:
      if (!_heightMoving && fibersAreUp()) {
        _moveInProgress=0;
        errors=0;
      } else if (!_heightMoving) errors|=E_HEIGHTSTUCK;
      break;
    case 0: //no move in progress
      break;
    default:
      break;
  }

}
