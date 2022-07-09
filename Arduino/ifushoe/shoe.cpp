#include "shoe.h"
#include "MemoryFree.h"

ShoeDrive::ShoeDrive(char shoe_name, uint8_t pipe_pot_pin, uint8_t height_pot_pin,
                     uint8_t motorsoff_pin, uint8_t motorson_pin, JrkG2I2C *p, JrkG2I2C *h)
                     : _shoe_name(shoe_name)
                     , _pipe_pot_pin(pipe_pot_pin)
                     , _height_pot_pin(height_pot_pin)
                     , _motorsoff_pin(motorsoff_pin)
                     , _motorson_pin(motorson_pin)
                     , _pipe_motor(p)
                     , _height_motor(h) {
}


void ShoeDrive::init() {
  pinMode(_motorson_pin, OUTPUT);
  pinMode(_motorsoff_pin, OUTPUT);
  digitalWrite(_motorson_pin, HIGH);
  digitalWrite(_motorsoff_pin, HIGH);
  motorsPowered=false;
  setMotorPower(true);
  _pipe_motor->setCoastWhenOff(false);
  _pipe_motor->setCoastWhenOff(false);

  _stallmon.lastcall=0;
  _stallmon.total_pipe=0;
  _stallmon.total_height=0;

  _height_moving=false;
  _pipe_moving=false;
  _timeLastPipeMovement=0;
  _timeLastHeightMovement=0;
  _moveInProgress=0;
  _samplet=0;
  _retries=MAX_RETRIES;
  _heading.pipe=1;
  _heading.height=1;
  _movepos.pipe=
  _movepos.height=

  _cfg.pipe_tol = DEFAULT_TOL;
  _cfg.height_tol = DEFAULT_TOL;
  _cfg.desired_slit = UNKNOWN_SLIT;
  const uint16_t default_heights[N_SLIT_POS] = {858, 839, 557, 530, 492, 220};
  for (uint8_t i=0;i<N_SLIT_POS;i++) {
    _cfg.pipe_pos[i]=119*i+224;
    _cfg.height_pos[i] = default_heights[i];
    _cfg.down_pos[i] = 135;
  }
}

void ShoeDrive::defineTol(char axis, uint8_t tol) {
  if (axis=='H' && tol<=MAX_HEIGHT_TOL) _cfg.height_tol=tol;
  else if (axis=='P' && tol<=MAX_PIPE_TOL) _cfg.pipe_tol=tol;
}

uint16_t ShoeDrive::getSlitPosition(uint8_t slit) {
  return _cfg.pipe_pos[max(min(slit, N_SLIT_POS-1),0)];
}

uint16_t ShoeDrive::getHeightPosition(uint8_t height) {
  return _cfg.height_pos[max(min(height, N_SLIT_POS-1),0)];
}

uint8_t ShoeDrive::getCurrentSlit(){  //0-5 or 0xFF = INTERMEDIATE/UNKNOWN, 0xFE = MOVING
  uint8_t ndx;
  if (_moveInProgress) return MOVING;
  ndx = _currentPipeIndex();
  if (!fibersAreUp() || ndx==UNKNOWN_SLIT) return UNKNOWN_SLIT;
  else return ndx;
}

void ShoeDrive::tellCurrentSlit() {
  uint8_t slit = getCurrentSlit();
  switch (slit) {
    case UNKNOWN_SLIT:
      Serial.print(F("INTERMEDIATE"));
      break;
    case MOVING:
      Serial.print(F("MOVING"));
      break;
    default:
      Serial.print(slit+1);
  }
}

shoepos_t ShoeDrive::getFilteredPosition() {
  //Filtered, Not instant, requires _updateFeedbackPos (generally via run()) to be called regularly
  return _feedback_pos;
}

void ShoeDrive::tellCurrentPosition() {
  Serial.print("p:"); Serial.print(_feedback_pos.pipe);
  Serial.print(" h:"); Serial.print(_feedback_pos.height);
}

bool ShoeDrive::moveInProgress() {
  return _moveInProgress!=SHOE_IDLE;
}

void ShoeDrive::defineSlitPosition(uint8_t slit, uint16_t pos){
  if (slit>N_SLIT_POS-1) return;
  _cfg.pipe_pos[slit] = pos;
}

void ShoeDrive::defineHeightPosition(uint8_t slit, uint16_t pos){
  if (slit>N_SLIT_POS-1) return;
  _cfg.height_pos[slit] = pos;
}

void ShoeDrive::defineDownPosition(uint8_t slit, uint16_t pos){
  if (slit>N_SLIT_POS-1) return;
  _cfg.down_pos[slit] = pos;
}

void ShoeDrive::moveToSlit(uint8_t slit) { //kick off a move
  if (slit>N_SLIT_POS-1) return;
  if ((_cfg.desired_slit!=slit || errors) && _moveInProgress==SHOE_IDLE) {
    _moveInProgress=SLIT_MOVE;
    _retries=MAX_RETRIES;
    _cfg.desired_slit=slit;
  }
}

void ShoeDrive::downUp() {
  if (_moveInProgress!=SHOE_IDLE || _cfg.desired_slit>N_SLIT_POS-1) return;
  _retries=0;
  _moveInProgress=SLIT_MOVE;
}

void ShoeDrive::getState(shoecfg_t &data) {
  data=_cfg;
}

void ShoeDrive::restoreState(shoecfg_t data) {
  _cfg=data;
}

bool ShoeDrive::idle() {
  return _moveInProgress==SHOE_IDLE;
}

uint8_t ShoeDrive::_currentPipeIndex() {
  //Returns index into pipe pos if within tolerance else 0xff
  uint16_t m=2000; //min
  uint8_t ndx=0xff;
  for (uint8_t i=0;i<N_SLIT_POS;i++) {
    uint16_t delta = abs((int)_feedback_pos.pipe - (int)_cfg.pipe_pos[i]);
    if (delta <= _cfg.pipe_tol && delta<m) {
      m=delta;
      ndx=i;
    }
  }
  return ndx;
}


bool ShoeDrive::fibersAreUp() {
  //The logic here is as follows:
  // -verify within tolerance of slits height setting
  // -the height moving check checks to see if we've stabilized
  shoepos_t cur = getFilteredPosition();
  shoepos_t cmd = getCommandedPosition();
  uint16_t err = abs((int)cur.height-(int)_cfg.height_pos[_cfg.desired_slit]);
  
  return (cmd.height==_cfg.height_pos[_cfg.desired_slit] && 
          err < _cfg.height_tol && 
          !heightMoving());
}


bool ShoeDrive::safeToMovePipes() {
  shoepos_t cmd = getCommandedPosition();
//  Serial.print("Cmd: ");Serial.print(cmd.height); Serial.print(" FB: ");Serial.print(_feedback_pos.height);
//  Serial.print(" Safe");Serial.println(_safe_pipe_height);
  return (cmd.height<=_safe_pipe_height && // commanded to a low enough point
          _feedback_pos.height<=(_safe_pipe_height+_cfg.height_tol)); // Clear of the pipes

}

shoestatus_t ShoeDrive::_status() {
  shoestatus_t x;
  x.pos=getFilteredPosition();
  x.target=getCommandedPosition();
  x.error.pipe = (int) _feedback_pos.pipe - (int)x.target.pipe;
  x.error.height = (int) _feedback_pos.height - (int) x.target.height;
  x.moving.height=heightMoving();
  x.moving.pipe=pipeMoving();
  x.heading=_heading;
  x.slerror.pipe=(int)_feedback_pos.pipe - (int)_cfg.pipe_pos[min(_cfg.desired_slit, N_SLIT_POS-1)];
  x.slerror.height=(int)_feedback_pos.height - (int)_cfg.height_pos[min(_cfg.desired_slit, N_SLIT_POS-1)];
  return x;
}

uint16_t ShoeDrive::_clearance_height(uint8_t slit, bool tell=false) {
  //given the current position and a destination slit
  //return the height below which we need to be for pipe safety

  // This function uses _feedback_pos. for figuring out the current pipe position so
  // it both depends on update feedback being called and would return a value
  // that becomes stale if called during a pipe move
  // In other words the assumption is this is called when the pipes aren't on the way

  // If a situation arises where the tab is between two pipes and contact has been made
  // with the longer (absent any significnat bending) the shorter will still be closer.
  // Here the next move will cause grinding and binding, if this causes lowering to fail
  // then we wind up going to the safe slit 1.
  // going to a lower pipe will clear the pipe we are rubbing against (by necessity)
  // going to a higher pipe will move away and so using the higher of the two clearances
  // minimizes any rubbing.

  //During a move however we pass under and inbetween pipes. Here the lower of the two should
  //should be considered if we are raising. However we do not raise unless we are in position.


  int pipe = (int) _feedback_pos.pipe;
  uint16_t m=2000, delta;
  uint8_t current=0;

  //Find the closest pipe index
  for (uint8_t i=0;i<N_SLIT_POS;i++) {
    delta = abs(pipe - (int)_cfg.pipe_pos[i]);
    if (delta<m) {
      m=delta;
      current=i;
    }
  }

  if ((current<N_SLIT_POS-1) &&
      (pipe > (_cfg.pipe_pos[current]+40) ))  // 1/3rd of the way between pipes
    current++;

  //Determine height
  uint16_t clearance=min(_cfg.down_pos[slit], _cfg.down_pos[current]);
  if (tell) {
    Serial.print(F("#Clearance "));Serial.print(clearance);
    Serial.print(F(" move from "));Serial.print((int)current+1);
    Serial.print(" (");Serial.print(pipe);
    Serial.print(F(") to "));Serial.println((int)slit+1);
  }
  return clearance;

}

#pragma mark
//Motor commands

void ShoeDrive::setMotorPower(bool enable) {
  if (enable == motorsPowered)
    return;
  if (!enable) {
    stop();
  } else {
    digitalWrite(_motorson_pin, LOW);
    delay(MOTOR_RELAY_HOLD_MS);
    digitalWrite(_motorson_pin, HIGH);
  }
  motorsPowered=enable;
}



bool ShoeDrive::pipeMoving() { //indicates literal movement
  return millis()-_timeLastPipeMovement < MOVING_TIMEOUT_MS;
}

bool ShoeDrive::heightMoving() { //indicates literal movement
  return millis()-_timeLastHeightMovement < MOVING_TIMEOUT_MS;
}

void ShoeDrive::movePipe(uint16_t pos){
  // Danger. This does not do any real checks.
  if (pos>1000) return;
  _moveInProgress=USER_MOVE_pipe;
  _cfg.desired_slit=UNKNOWN_SLIT;
  _movePipe(pos);
}

void ShoeDrive::moveHeight(uint16_t pos){
  // Danger. This does not do any real checks.
  if (pos>1000) return;
  _moveInProgress=USER_MOVE_height;
  _cfg.desired_slit=UNKNOWN_SLIT;
  _moveHeight(pos);
}

inline void ShoeDrive::_movePipe(uint16_t pos){
  _move(_pipe_motor, pos);
}

inline void ShoeDrive::_moveHeight(uint16_t pos){
  _move(_height_motor, pos);
}


void ShoeDrive::stop() {
  _height_motor->stopMotor();
  _pipe_motor->stopMotor();
  _moveInProgress=SHOE_IDLE;
}

shoepos_t ShoeDrive::getCommandedPosition() {
  shoepos_t pos;
  pos.pipe=_pipe_motor->getTarget()/4;
  pos.height=_height_motor->getTarget()/4;
  return pos;
}

void ShoeDrive::_move(JrkG2I2C *axis, uint16_t pos){
  // Danger. This does not do any checks.
  int8_t heading=0;
  uint16_t last;

  last=axis->getTarget()/4;
  if (pos < last) heading = -1;
  else if (pos > last) heading = 1;

  if (axis==_height_motor) {
    _heading.height=heading==0 ? _heading.height:heading;
    _timeLastHeightMovement=millis();
  } else {
    _heading.pipe=heading==0 ? _heading.pipe:heading;
    _timeLastPipeMovement=millis();
  }

  setMotorPower(true);
  axis->setTarget(pos*4);
}

bool ShoeDrive::_jrk_wants_to_move(JrkG2I2C *axis) {
  int16_t dctarget, dc;
  dctarget=axis->getDutyCycleTarget();
  dc=axis->getDutyCycle();
  return (dc!=0 || dctarget!=0) && !_jrk_stopped(axis);
  //NB when (axis->getErrorFlagsOccurred()&JRK_HALTING_ERRORS)!=0 the motor may be halted even though dctarget==0
}

bool ShoeDrive::_jrk_stopped(JrkG2I2C *axis) {
  uint8_t buf[2];
  uint16_t e;
  axis->getVariables(0x12, 2, buf);
  e=buf[0];
  e|=((uint16_t)buf[1])<<16;
  return (e & (1 << (uint8_t)JrkG2Error::AwaitingCommand));
}


void ShoeDrive::_protectStall(){
  //Stops motor after DC (I*t) exceeds 210mA*3s, decays by .042A/s, increments by current*dt

  uint32_t ms = millis();
  int32_t interval=ms-_stallmon.lastcall;
  _stallmon.lastcall=ms;

  _stallmon.total_pipe += (((int32_t)_pipe_motor->getCurrent())-STALL_DECREMENT)*interval;
  _stallmon.total_pipe = _stallmon.total_pipe<0 ? 0:_stallmon.total_pipe;
  if (_stallmon.total_pipe>STALL_LIMIT) {
    Serial.print(F("#Stallmon: current="));Serial.print(_pipe_motor->getCurrent());
    Serial.print(F(" total="));Serial.println(_stallmon.total_pipe);
    //stall and need to stop
    errors|=E_PIPESTALL;
    _stallmon.total_pipe=0;
    stop();
    Serial.println(F("ERROR: Pipe motor stalled out, idling."));
  }
 
  _stallmon.total_height += (((int32_t)_height_motor->getCurrent())-STALL_DECREMENT)*interval;
  _stallmon.total_height = _stallmon.total_height<0 ? 0:_stallmon.total_height;
  if (_stallmon.total_height>STALL_LIMIT) {
    //stall and need to stop
    errors|=E_HEIGHTSTALL;
    _stallmon.total_height=0;
    stop();
    Serial.println(F("ERROR: Height motor stalled out, idling."));
  }
}


void ShoeDrive::_updateFeedbackPos() { 

  shoepos_t pos;
  int adu;
  float tmp;
  uint32_t t = micros();
  uint32_t t_ms=millis();
  // returns number between 0-4092 that is averaged from configured number of 10bit ADC readings
  pos.pipe=_pipe_motor->getScaledFeedback()/4; 
  pos.height=_height_motor->getScaledFeedback()/4;

  _feedback_pos=pos;
  int deltah=(int)pos.height-(int)_movepos.height;
  int deltap=(int)pos.pipe-(int)_movepos.pipe;

  if (abs(deltap) > MOVING_PIPE_TOL ) {  //movement measured
    if (!_pipe_moving) {
      Serial.print(F("## "));
      Serial.print(_shoe_name);
      Serial.print(F(" Pipe move: "));
      Serial.println(deltap);
    }
    _pipe_moving=true;
    _movepos.pipe=pos.pipe;
    _timeLastPipeMovement=t_ms;
  } else if (_jrk_wants_to_move(_pipe_motor)) { //jrk is trying to move things
    if (!_pipe_moving) {
      Serial.print(F("## "));
      Serial.print(_shoe_name);
      Serial.println(F(" Pipe move wanted"));
    }
    _pipe_moving=true;
    _movepos.pipe=pos.pipe;
    _timeLastPipeMovement=t_ms;
  } else if (t_ms-_timeLastPipeMovement > MOVING_TIMEOUT_MS) { // there has not been recent movement
    if (_pipe_moving) {
      Serial.print(F("## "));
      Serial.print(_shoe_name);
      Serial.println(F(" Pipe stop"));
    }
    _pipe_moving=false;
  }

  if (abs(deltah) > MOVING_HEIGHT_TOL ) {  //movement measured
    if (!_height_moving) {
      Serial.print(F("## "));
      Serial.print(_shoe_name);
      Serial.print(F(" Height move: "));
      Serial.println(deltah);
    }
    _height_moving=true;
    _movepos.height=pos.height;
    _timeLastHeightMovement=t_ms;
  } else if (_jrk_wants_to_move(_height_motor)) { //jrk is trying to move things
    if (!_height_moving) {
      Serial.print(F("## "));
      Serial.print(_shoe_name);
      Serial.println(F(" Height move wanted"));
    }
    _height_moving=true;
    _movepos.height=pos.height;
    _timeLastHeightMovement=t_ms;
  } else if (t_ms-_timeLastHeightMovement > MOVING_TIMEOUT_MS) { // there has not been recent movement
    if (_height_moving) {
      Serial.print(F("## "));
      Serial.print(_shoe_name);
      Serial.println(F(" Height stop"));
    }
    _height_moving=false;
  }
   
}

void ShoeDrive::run(){

  shoestatus_t stat;
  
  // Monitor position
  _updateFeedbackPos();

  //Stall monitor
  _protectStall();
  
  // Build status struct
  stat = _status();

  if (_cfg.desired_slit==UNKNOWN_SLIT) _moveInProgress=SHOE_IDLE;

  //Execute move: lower, wait, move pipes, wait, raise, wait, done
  switch (_moveInProgress) {


    case RECOVERY_MOVE: // A move didn't go as planned
        /* failure modes:
         *
        didn't move down all the way -> move pipes to a higher pipe (if needed) and move up)
        didn't move up all the way -> move down then move up -> try again
        too high during pipe move -> move to higer pipe and move up -> try again
        pipe didn't get to position -> move to high pipe then move up -> try again
        */

        if (!_retries) { //transition to SHOE_IDLE
          tellStatus();
          Serial.print(F("ERROR: Recovery failed after "));Serial.print((int)MAX_RETRIES);
          Serial.println(F(" tries, idling."));
          _moveInProgress=SHOE_IDLE;
        } else {
          Serial.print(F("#Start retry "));Serial.println((int)_retries);
          Serial.print(F("#Free Mem:"));Serial.println(freeMemory());
          tellStatus();
          _retries--;

          if ( (errors & (E_HEIGHTSTALL|E_HEIGHTMOVEDUP|E_RECOVER|E_PIPESHIFT)) | !safeToMovePipes()) {

            // E_HEIGHTSTALL: didn't move down all the way may be down just a bit or just not clear.
            // Lower pipes are slightly more prone to not getting all the way down
            // so move pipes to a higher pipe and move up
            // Pathological case of pipe jammed into the rear of the tab or between tabs is thankfully not physically possible.
            Serial.println(F("#Pipe to SL 1"));
            _movePipe(_cfg.pipe_pos[0]);
            _moveInProgress=RECOVERY_MOVE_pipe;

          } else if (errors & E_PIPESTALL) {

            uint16_t dest = stat.target.pipe - 200;//*stat.heading.pipe;
            Serial.print(F("#Pipe retry "));Serial.print(stat.target.pipe);Serial.print(F(" via "));Serial.println(dest);
            // E_PIPESTALL: pipe didn't get to where it was sent. if height is down we can send it safely where ever,
            // if height isn't safe then simplest to handle it like a height stall (see above)
            _movePipe(dest);
            _movePipe(stat.target.pipe);
            errors=0;
            _moveInProgress=SLIT_MOVE_pipe;

          } else if (errors & E_HEIGHTSTUCK) {
            Serial.println(F("#Raise fail, lower"));
            // E_HEIGHTSTUCK: height didn't up get to where it was sent. if pipes aren't where they need to be then
            // that would cause this (though that isn't possible by sw. design), just lower back down and let the cycle go again
            _moveHeight(_clearance_height(_cfg.desired_slit));
            errors=0;
            _moveInProgress=SLIT_MOVE_lower;
          }
        }
        break;

    case RECOVERY_MOVE_pipe:
      if (stat.moving.pipe) {
         //wait
      } else if (_currentPipeIndex() == 0) { // we can now raise all the way up
          errors=0;
          Serial.print(F("#RECOVERY_MOVE_pipe done: "));Serial.print(stat.error.pipe);Serial.println(F(". Raise"));
          _moveHeight(_cfg.height_pos[0]);
          _moveInProgress=RECOVERY_MOVE_raise;
      } else  { //transition to RECOVERY_MOVE
        _moveInProgress=RECOVERY_MOVE;
        errors|=E_RECOVER;
        Serial.print(F("#RECOVERY_MOVE_pipe failed"));Serial.println(stat.error.pipe);
        tellStatus();
      }
      break;

    case RECOVERY_MOVE_raise:
      if (!stat.moving.height) {
        Serial.print(F("#RECOVERY_MOVE_raise done: "));Serial.println(stat.error.height);
        errors=0;
        _moveInProgress=SLIT_MOVE;
      }
      break;

    /*positions
    _feedback_pos. filtered analog position
    stat.target position being written via PWM
    stat.pos filtered analog position
    stat.error difference between commanded and filtered analog (NOT based on _cfg.desired_slit)
    */
    case SLIT_MOVE: //new move, lower cassette
      errors=0;
      _safe_pipe_height = _clearance_height(_cfg.desired_slit, true);
      Serial.print(F("#Starting move to ")); Serial.print((uint16_t)_cfg.desired_slit+1);
      Serial.print(F(". Lowering, safe height "));Serial.println(_safe_pipe_height);
      _moveHeight(_safe_pipe_height);
      _moveInProgress=SLIT_MOVE_lower;
      break;
      
    case SLIT_MOVE_lower:  //lowering in process
      if (safeToMovePipes()) { //transition to SLIT_MOVE_pipes
        errors=0;
        Serial.print(F("#Down ("));Serial.print(stat.error.height);Serial.println(F("), moving pipe."));
        _movePipe(_cfg.pipe_pos[_cfg.desired_slit]);
        _moveInProgress=SLIT_MOVE_pipe;
      } else if (errors || !stat.moving.height){ //transition to RECOVERY_MOVE we are stalled breaks if stall timeout is too short to detect real movement
        Serial.print(F("#WARN: Height not down ")); Serial.println(stat.error.height);
        errors|=E_HEIGHTSTALL;
        _moveInProgress=RECOVERY_MOVE;
      }
      break;
      
    case SLIT_MOVE_pipe: // moving pipes into position
      if (stat.moving.pipe) {
        _safe_pipe_height = _clearance_height(_cfg.desired_slit);
        if (!safeToMovePipes()) { // transition to RECOVERY_MOVE else nothing to do but wait
          Serial.print(F("#WARN: Height moved too high: "));Serial.print(stat.error.height);Serial.println(F(". Stoping pipe."));
          _movePipe(stat.pos.pipe);
          _moveInProgress=RECOVERY_MOVE;
          errors|=E_HEIGHTMOVEDUP;
        }
      } else if (_currentPipeIndex() == _cfg.desired_slit) { // transition to SLIT_MOVE_raise
          errors=0;
          Serial.print(F("#Pipe done ("));Serial.print(stat.error.pipe);Serial.println(F("), raising."));
          _moveHeight(_cfg.height_pos[_cfg.desired_slit]);
          _moveInProgress=SLIT_MOVE_raise;
      } else  { //transition to RECOVERY_MOVE
        Serial.print(F("#WARN: Pipe error too large: "));Serial.println(stat.error.pipe);
        errors|=E_PIPESTALL;
        _moveInProgress=RECOVERY_MOVE;
      }
      break;
    case SLIT_MOVE_raise: // raising cassette
      if (stat.moving.height) {
        if (_currentPipeIndex() != _cfg.desired_slit) { //pipe shifted abort, else nothing to do but wait
          Serial.print(F("#WARN: Pipe shifted "));Serial.print(stat.error.pipe);Serial.println(F(". Lowering."));
          _moveHeight(_clearance_height(_cfg.desired_slit));
          errors|=E_PIPESHIFT;
          _moveInProgress=RECOVERY_MOVE;
        }
      } else if (fibersAreUp()) { //transition to SHOE_IDLE
          Serial.print(F("#Raised ("));Serial.print(stat.error.height);Serial.print(F("). Slit "));Serial.println((int) _cfg.desired_slit+1);
          _moveInProgress=SHOE_IDLE;
          errors=0;
      } else { //transition to RECOVERY_MOVE
          Serial.print(F("#WARN: Height stopped too low:"));Serial.println(stat.error.height);
          errors|=E_HEIGHTSTUCK;
          _moveInProgress=RECOVERY_MOVE;
      }
      break;
    case USER_MOVE_height:
       if (!stat.moving.height) _moveInProgress=SHOE_IDLE;  //transition to SHOE_IDLE
      break;
    case USER_MOVE_pipe:
      if (!stat.moving.pipe) _moveInProgress=SHOE_IDLE;     //transition to SHOE_IDLE
      break;
    case SHOE_IDLE:
      stop();
      break;
    default:
      break;
  }

}


void ShoeDrive::tellStatus() {

  shoestatus_t stat;
  _updateFeedbackPos();
  stat=_status();

  Serial.print(F("==="));Serial.print(_shoe_name);
  Serial.println(F(" Shoe Status===\n (pipe, height)"));
  Serial.print(" ADC: ");
    Serial.print(analogRead(_pipe_pot_pin));Serial.print(", ");Serial.println(analogRead(_height_pot_pin));

  Serial.print(F(" Servo: "));Serial.print(stat.target.pipe);Serial.print(F(", "));Serial.println(stat.target.height);
  Serial.print(F(" Pos: "));Serial.print(stat.pos.pipe);Serial.print(F(", "));Serial.println(stat.pos.height);
  Serial.print(F(" Err: ")); Serial.print(stat.error.pipe);Serial.print(F(", "));Serial.println(stat.error.height);

  Serial.print(F(" Moving: "));Serial.print(stat.moving.pipe);Serial.print(F(", "));Serial.println(stat.moving.height);
  Serial.print(F("  ms since move: "));
    Serial.print(millis()-_timeLastPipeMovement);Serial.print(F(", "));
    Serial.println(millis()-_timeLastHeightMovement);
  Serial.print(F("  SL Delta: ")); Serial.print(stat.slerror.pipe);Serial.print(F(", "));Serial.println(stat.slerror.height);
  Serial.print(F(" Toler: ")); Serial.print(_cfg.pipe_tol);Serial.print(F(", "));Serial.println(_cfg.height_tol);

  Serial.print(F("Desired Slit: ")); Serial.println(((int) stat.desired_slit)+1);
  Serial.print(F("Detected Slit: "));tellCurrentSlit();Serial.println();

  Serial.print(F("Errors: "));Serial.println(errors, BIN);
  Serial.print(F("Jrk: "));Serial.print(_pipe_motor->getErrorFlagsHalting(), BIN);Serial.print(F(", "));Serial.println(_height_motor->getErrorFlagsHalting(), BIN);
  Serial.print(F("MiP: "));Serial.print(_moveInProgress);
    Serial.print(F(" Safe: "));Serial.print(safeToMovePipes());
    Serial.print(F(" Relay: "));Serial.print(motorsPowered);
    Serial.print(F(" curPipeNdx: "));Serial.println(_currentPipeIndex());

  Serial.print(F("Slit Pos:\n Up:   "));
    for(uint8_t i=0;i<N_SLIT_POS;i++) {
      Serial.print(" ");
      Serial.print(_cfg.height_pos[i]);
    }
  Serial.print(F("\n Down: "));
    for(uint8_t i=0;i<N_SLIT_POS;i++) {
      Serial.print(" ");
      Serial.print(_cfg.down_pos[i]);
    }
  Serial.print(F("\n Pipe: "));
    for(uint8_t i=0;i<N_SLIT_POS;i++) {
      Serial.print(" ");
      Serial.print(_cfg.pipe_pos[i]);
    }
  Serial.print(F("\nFree Mem:"));Serial.print(freeMemory());
  Serial.println(F("\n==================="));


}
