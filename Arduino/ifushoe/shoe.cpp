#import "shoe.h"

ShoeDrive::ShoeDrive(uint8_t pipe_servo_pin, uint8_t pipe_pot_pin, uint8_t height_servo_pin,
                     uint8_t height_pot_pin, uint8_t height_sensor_pin,
                     uint8_t motorsoff_pin, uint8_t motorson_pin, Servo *p, Servo *h)
                     : _pipe_pin(pipe_servo_pin)
                     , _pipe_pot_pin(pipe_pot_pin)
                     , _height_pin(height_servo_pin)
                     , _height_pot_pin(height_pot_pin)
                     , _sensor_pin(height_sensor_pin)
                     , _motorsoff_pin(motorsoff_pin)
                     , _motorson_pin(motorson_pin) 
                     , _pipe_filter(1, EWMA_SAMPLES)     //about 10 samples
                     , _height_filter(1, EWMA_SAMPLES)
                     , _pipe_motor(p)
                     , _height_motor(h) {
}
int feedback_update_msg=0;

void ShoeDrive::init() {
  pinMode(_motorson_pin, OUTPUT);
  pinMode(_motorsoff_pin, OUTPUT);
  digitalWrite(_motorson_pin, HIGH);
  digitalWrite(_motorsoff_pin, HIGH);
  pinMode(_sensor_pin, INPUT);
  digitalWrite(_sensor_pin, HIGH);
  motorsPowered=true;
  powerOffMotors();

  _timeLastPipeMovement=0;
  _timeLastHeightMovement=0;
  _moveInProgress=0;
  _samplet=0;

  _cfg.pos = getLivePosition();
//  _cfg.pos.pipe=_pipe_filter.filter((MAX_ADC+1)/2);   //in ADC units, 512 is the midpoint
//  _cfg.pos.height=_height_filter.filter((MAX_ADC+1)/2);
  _cfg.pipe_tol = DEFAULT_TOL;
  _cfg.height_tol = DEFAULT_TOL;
  _cfg.desired_slit = UNKNOWN_SLIT;
  for (uint16_t i=0;i<N_SLIT_POS;i++) _cfg.pipe_pos[i]=125*i+200; //550 685
  _cfg.height_pos[0]=225;
  _cfg.height_pos[1]=945;
  _cfg.idle_disconnected=DEFAULT_IDLE_DISCONNECTED;

}

ShoeDrive::~ShoeDrive() {
//  _pipe_motor.~Servo();
//  _height_motor.~Servo(); 
}

void ShoeDrive::defineTol(char axis, uint8_t tol) {
  if (axis=='H' && tol<=MAX_HEIGHT_TOL) _cfg.height_tol=tol;
  else if (axis=='P' && tol<=MAX_PIPE_TOL) _cfg.pipe_tol=tol;
}

void ShoeDrive::powerOffMotors() {
  if (motorsPowered) {
    if (_pipe_motor->attached()) _pipe_motor->detach();
    if (_height_motor->attached()) _height_motor->detach();
    digitalWrite(_motorsoff_pin, LOW);
    delay(MOTOR_RELAY_HOLD_MS);
    digitalWrite(_motorsoff_pin, HIGH);
    motorsPowered=false;
  }
}

void ShoeDrive::powerOnMotors() {
  if (!motorsPowered) {
    digitalWrite(_motorson_pin, LOW);
    delay(MOTOR_RELAY_HOLD_MS);
    digitalWrite(_motorson_pin, HIGH);
    motorsPowered=true;
  }
}

void ShoeDrive::stop() {
//  shoepos_t pos = getLivePosition();
//  _pipe_motor->writeMicroseconds(pos.pipe+1000);
//  _height_motor->writeMicroseconds(pos.height+1000);
//  delay(200);
  _pipe_motor->detach();
  _height_motor->detach();
  _cfg.desired_slit=UNKNOWN_SLIT;
  _moveInProgress=0;
}

uint8_t ShoeDrive::getCurrentSlit(){ //0-5 or 0xFF = INTERMEDIATE/UNKNOWN, 0xFE = MOVING
  uint8_t ndx;
  if (_moveInProgress) return MOVING;
  ndx = _currentPipeIndex();
  if (!fibersAreUp() || ndx==UNKNOWN_SLIT) return UNKNOWN_SLIT;
  else return ndx;
} 

void ShoeDrive::tellCurrentSlit() {
  uint8_t slit = getCurrentSlit();
  if (slit==UNKNOWN_SLIT) Serial.print(F("INTERMEDIATE"));
  else if (slit==MOVING) Serial.print(F("MOVING"));
  else Serial.print(slit+1);
}


shoepos_t ShoeDrive::getFilteredPosition() {
  //Filtered, Not instant, requires run() to be called regularly
  return _cfg.pos;
}

shoepos_t ShoeDrive::getLivePosition() {
  shoepos_t pos;
  //reverse it for electrical reasons
  pos.pipe=round(ADU_TO_STEP*(float)(MAX_ADC-analogRead(_pipe_pot_pin)));
  pos.height=round(ADU_TO_STEP*(float)(MAX_ADC-analogRead(_height_pot_pin)));
  return pos;
}

shoepos_t ShoeDrive::getCommandedPosition() {
  shoepos_t pos;
  pos.pipe= _pipe_motor->readMicroseconds()-1000;
  pos.height= _height_motor->readMicroseconds()-1000;
  return pos;
}


bool ShoeDrive::getOffWhenIdle() {
  return _cfg.idle_disconnected;
}

void ShoeDrive::toggleOffWhenIdle() {
  _cfg.idle_disconnected=!_cfg.idle_disconnected;
}


void ShoeDrive::tellStatus() {

  shoepos_t pos;
  delay(SAMPLE_INTERVAL_MS);
  feedback_update_msg=1;
  _updateFeedbackPos();

  Serial.println(F("Shoe Status: (pipe, height)"));
  uint64_t tmp;
  tmp=_pipe_filter.output();
  Serial.print(" ADC: "); 
  if (tmp>=0xffffffff) Serial.print("***");
  else Serial.print((uint32_t)tmp);
  Serial.print(", "); 
  tmp=_height_filter.output();
  if (tmp>=0xffffffff) Serial.print("***");
  else Serial.println((uint32_t)tmp);
  Serial.print(F(" Pos (live): ")); Serial.print(_cfg.pos.pipe);
  pos=getLivePosition();
  Serial.print(" ("); Serial.print(pos.pipe);Serial.print("), "); Serial.print(_cfg.pos.height);
  Serial.print(" (");Serial.print(pos.height);Serial.print(")\n");
  Serial.print(F(" Attached: "));Serial.print(_pipe_motor->attached());Serial.print(", ");Serial.println(_height_motor->attached());

  pos=getCommandedPosition();
  Serial.print(F("Servo: "));Serial.print(pos.pipe);Serial.print(", ");Serial.println(pos.height);
  Serial.print(F("Time: "));Serial.print(millis()-_timeLastPipeMovement);
  Serial.print(", ");Serial.println(millis()-_timeLastHeightMovement);
  Serial.print(F("Moving: "));Serial.print(pipeMoving());Serial.print(", ");
  Serial.println(heightMoving());

  Serial.print(F("Slit: "));
  tellCurrentSlit();
  Serial.println();
  
  Serial.print(F("Errors: "));Serial.print(errors, BIN);
  Serial.print(F(" MiP: "));Serial.print(_moveInProgress);
  Serial.print(F(" Button: "));Serial.print(downButtonPressed());
  Serial.print(F(" Safe: "));Serial.print(safeToMovePipes());
  Serial.print(F(" Relay: "));Serial.print(motorsPowered);
  Serial.print(F(" Idleoff: "));Serial.print(_cfg.idle_disconnected);
  Serial.print(F(" curPipeNdx: "));Serial.println(_currentPipeIndex());
  Serial.print(F("Desired Slit: ")); Serial.println((uint16_t) _cfg.desired_slit);
  Serial.print(F("Pipe Delta: ")); Serial.print(getPositionError()); Serial.print(F(" Tol: ")); Serial.println(_cfg.pipe_tol);
    
  Serial.print(F("Slits:\n"));
  Serial.print(F(" Down: "));Serial.print(_cfg.height_pos[DOWN_NDX]);
  Serial.print(F(" Up: "));Serial.println(_cfg.height_pos[UP_NDX]);
  for(uint8_t i=0;i<N_SLIT_POS;i++) {
    Serial.print(" ");
    Serial.print(_cfg.pipe_pos[i]);
  }
  Serial.println();
}


uint16_t ShoeDrive::getSlitPosition(uint8_t slit) {
  return _cfg.pipe_pos[max(min(slit, N_SLIT_POS-1),0)];
}


uint16_t ShoeDrive::getHeightPosition(uint8_t height) {
  return _cfg.height_pos[max(min(height, N_HEIGHT_POS-1),0)];
}


void ShoeDrive::tellCurrentPosition() {
  Serial.print("p:"); Serial.print(_cfg.pos.pipe);
  Serial.print(" h:"); Serial.print(_cfg.pos.height);
}


bool ShoeDrive::moveInProgress() {
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
  _cfg.pipe_pos[slit] = pos;

}


void ShoeDrive::defineSlitPosition(uint8_t slit){
  defineSlitPosition(slit, _pipe_motor->readMicroseconds()-1000);    
}

    
void ShoeDrive::defineHeightPosition(uint8_t height, uint16_t pos){
  if (height>N_HEIGHT_POS-1) return;
  _cfg.height_pos[height] = pos;
}


void ShoeDrive::defineHeightPosition(uint8_t height){
  defineHeightPosition(height, _height_motor->readMicroseconds()-1000);  
}


void ShoeDrive::moveToSlit(uint8_t slit) { //kick off a move
  if (slit>N_SLIT_POS-1) return;
  if ((_cfg.desired_slit!=slit ||errors) && _moveInProgress==0) {
    _moveInProgress=10;
    _cfg.desired_slit=slit;
  }
}

void ShoeDrive::movePipe(uint16_t pos){
  // Danger. This does not do any checks.
  Serial.print(F("#Moving pipe to "));Serial.println(pos);
  _moveInProgress=1;
  _cfg.desired_slit=UNKNOWN_SLIT;
  _movePipe(pos);
//  delay(50);
}

void ShoeDrive::_movePipe(uint16_t pos){
  // Danger. This does not do any checks.
  powerOnMotors();
  if (!_pipe_motor->attached()) _pipe_motor->attach(_pipe_pin, (uint16_t) 1000, (uint16_t) 2000);
  _pipe_motor->writeMicroseconds(min(max(pos+1000,1000),2000));
  _timeLastPipeMovement=millis();
}

void ShoeDrive::moveHeight(uint16_t pos){
  // Danger. This does not do any checks.
  Serial.print(F("#Moving H to "));Serial.println(pos);
  _moveInProgress=2;
  _cfg.desired_slit=UNKNOWN_SLIT;
  _moveHeight(pos);
//  delay(50);
}

void ShoeDrive::_moveHeight(uint16_t pos){
  // Danger. This does not do any checks.
  powerOnMotors();
  if (!_height_motor->attached()) _height_motor->attach(_height_pin, (uint16_t) 1000, (uint16_t) 2000);
  _height_motor->writeMicroseconds(min(max(pos+1000,1000),2000));
  _timeLastHeightMovement=millis();
}

bool ShoeDrive::downButtonPressed(){
  return !digitalRead(_sensor_pin);
}

bool ShoeDrive::safeToMovePipes() {
  //The logic here is as follows:
  // -The read command verifies that the setpoint is down
  // -The down button is pressed
  // -The _cfg.pos.height is below the clearance point
  return (_cfg.pos.height<=_cfg.height_pos[DOWN_NDX]+_cfg.height_tol &&
          (_height_motor->readMicroseconds()-1000)<=_cfg.height_pos[DOWN_NDX]); //&&
          //downButtonPressed());  //TODO UNCOMMENT WHEN BUTTONS WORK
}

bool ShoeDrive::fibersAreUp() {
  //The logic here is as follows:
  // -the read command verifies that the setpoint is UP
  // -the height moving check checks to see if we've stabilized
  // -the down button isn't pressed
  // -we can't check _cfg.pos.height because that is a function of the pipe
  return (_height_motor->readMicroseconds()-1000)>=_cfg.height_pos[UP_NDX] && 
          !heightMoving() && !downButtonPressed();
}

void ShoeDrive::getState(shoecfg_t &data) {
  data=_cfg;
}

void ShoeDrive::restoreState(shoecfg_t data) {
  _cfg = data;
  _cfg.idle_disconnected=false;
}

bool ShoeDrive::idle() {
  return _moveInProgress==0;
}


void ShoeDrive::run(){

  // Monitor position
  _updateFeedbackPos();

  //Execute move: lower, wait, move pipes, wait, raise, wait, done
  bool _heightMoving = heightMoving();
  bool _pipeMoving = pipeMoving();
  
  switch (_moveInProgress) {
    case 10: //new move, lower cassette
      errors=0;
      Serial.print(F("#Starting move to ")); Serial.print((uint16_t)_cfg.desired_slit); Serial.println(F(". Lowering."));
      _moveHeight(_cfg.height_pos[DOWN_NDX]);
      delay(RC_PULSE_DELAY);
      _height_motor->detach();
      _moveInProgress--;
      break;
    case 9: // move pipes
      if (safeToMovePipes()) {
        errors=0;
        Serial.print(F("#Down ("));Serial.print((int)_cfg.pos.height-(int)_cfg.height_pos[DOWN_NDX]);Serial.println(F("), moving pipes."));
        _movePipe(_cfg.pipe_pos[min(_cfg.desired_slit, N_SLIT_POS-1)]);
        delay(RC_PULSE_DELAY);
        _pipe_motor->detach();
        _moveInProgress--;
      } else if (!_heightMoving) {
        if(errors==0) { 
          Serial.print(F("#ERROR: Height stopped above clearance height ("));
          Serial.print((int)_cfg.pos.height-(int)_cfg.height_pos[DOWN_NDX]);Serial.println(F(")."));
          tellStatus();
        }
        errors|=E_HEIGHTSTALL;
        _moveInProgress=0;
      }
      break;
    case 8: // raise cassette
      if (!_pipeMoving) {
        if(_currentPipeIndex()==_cfg.desired_slit) {
          Serial.print(F("#Pipe done ("));Serial.print(getPositionError());Serial.println(F("), raising."));
          _moveHeight(_cfg.height_pos[UP_NDX]);
          delay(RC_PULSE_DELAY);
          _height_motor->detach();
          _moveInProgress--;
          errors=0;
        } else  {
          if(errors==0) {
            Serial.print(F("#ERROR: Pipe stopped outside of tolerance ("));Serial.print(getPositionError());Serial.println(F(")."));
            tellStatus();
          }
          errors|=E_PIPESTALL;
          _moveInProgress=0;
        }
      }
      break;
    case 7: //All done
      if (!_heightMoving) {
        if (fibersAreUp()) {
          Serial.println(F("#Move complete"));
          _moveInProgress=0;
          errors=0;
        } else {
          if(errors==0) {
            Serial.println(F("#ERROR: Fibers not up"));
            tellStatus();
          }
          _moveInProgress=0;
          errors|=E_HEIGHTSTUCK;
        }
      }
      break;
    case 2: //explicit height move
       if (!_heightMoving) _moveInProgress=0;
      break;
    case 1: //explicit pipe move
      if (!_pipeMoving) _moveInProgress=0;
      break;
    case 0: //no move in progress
      if (_cfg.idle_disconnected) powerOffMotors();
      break;
    default:
      break;
  }

}

int16_t ShoeDrive::getDistanceFromSlit(uint8_t i) {
  return (int)_cfg.pos.pipe - (int)_cfg.pipe_pos[min(i, N_SLIT_POS-1)];
}

int16_t ShoeDrive::getPositionError() {
  return (int)_cfg.pos.pipe - (int)_cfg.pipe_pos[min(_cfg.desired_slit, N_SLIT_POS-1)];
}


uint8_t ShoeDrive::_currentPipeIndex() {
  //Returns index into pipe pos if within tolerance else 0xff
  for (uint8_t i=0;i<N_SLIT_POS;i++)
    if (abs(getDistanceFromSlit(i)) <= _cfg.pipe_tol)
      return i;
  return 0xff;
}


void ShoeDrive::_wait(uint32_t time_ms) {
  uint32_t tic=millis();
  while (millis()-tic<time_ms) _updateFeedbackPos();
}

void ShoeDrive::_updateFeedbackPos() {  //~500us
  shoepos_t pos;
  int adu;
  float tmp;
  uint32_t t = micros();
  uint32_t t_ms=millis();
  if (t-_samplet>SAMPLE_INTERVAL_MS) {

    _samplet=t;

    adu=analogRead(_pipe_pot_pin);
    tmp=_pipe_filter.filter(MAX_ADC-adu);  //reverse it for electrical reasons
    pos.pipe=round(ADU_TO_STEP*(float)tmp);
#ifdef DEBUG_FEEDBACK
    if (feedback_update_msg>0) {
      Serial.print(F("Pipe ADC: "));Serial.print(MAX_ADC-adu);Serial.println(".");
      Serial.print(F("Filtered: "));Serial.print(tmp);Serial.print("*");Serial.print(ADU_TO_STEP);
      Serial.print("=");Serial.println(pos.pipe);
    }
#endif
    adu=analogRead(_height_pot_pin);
    tmp=_height_filter.filter(MAX_ADC-adu);
    pos.height=round(ADU_TO_STEP*(float)tmp);

#ifdef DEBUG_FEEDBACK
    if (feedback_update_msg>0) {
      Serial.print(F("Height ADC: "));Serial.print(MAX_ADC-adu);Serial.println(".");
      Serial.print(F("Filtered: "));Serial.print(tmp);Serial.print("*");Serial.print(ADU_TO_STEP);
      Serial.print("=");Serial.println(pos.height);
    }
#endif
    uint32_t toc = micros();
#ifdef DEBUG_FEEDBACK
    if (feedback_update_msg>0) {
      Serial.print(F("Update feedback took "));Serial.print(toc-t);Serial.println(" us.");
    }
#endif DEBUG_FEEDBACK
    if (feedback_update_msg>0) feedback_update_msg--;

  }

  if (pos.pipe!=_cfg.pos.pipe) {
    _cfg.pos.pipe=pos.pipe;
  }
  if (abs((int)pos.pipe-(int)_movepos.pipe)>MOVING_PIPE_TOL){
      //Serial.print("P");Serial.print(pos.pipe);Serial.print(" o=");Serial.print(_movepos.pipe);Serial.print(" d=");Serial.println(abs((int)pos.pipe-(int)_movepos.pipe));
      _timeLastPipeMovement=t_ms;
      _movepos.pipe=pos.pipe;
  }

  if (pos.height!=_cfg.pos.height) {
    _cfg.pos.height=pos.height;
//    _timeLastHeightMovement=t_ms;
  }
  if (abs((int)pos.height-(int)_movepos.height)>MOVING_HEIGHT_TOL){
       //Serial.print("H");Serial.print(pos.height);Serial.print(" o=");Serial.print(_movepos.height);Serial.print(" d=");Serial.println(abs((int)pos.height-(int)_movepos.height));
      _timeLastHeightMovement=t_ms;
      _movepos.height=pos.height;
  }

}
