#include "shoe.h"
#include "MemoryFree.h"

ShoeDrive::ShoeDrive(char shoe_name, uint8_t pipe_servo_pin, uint8_t pipe_pot_pin, uint8_t height_servo_pin,
                     uint8_t height_pot_pin, uint8_t height_sensor_pin,
                     uint8_t motorsoff_pin, uint8_t motorson_pin, Servo *p, Servo *h)
                     : _shoe_name(shoe_name)
                     , _pipe_pin(pipe_servo_pin)
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

#define MAX_RETRIES 2

#define SHOE_IDLE 0
#define USER_MOVE_pipe 2
#define USER_MOVE_height 1

#define RECOVERY_MOVE 99
#define RECOVERY_MOVE_pipe 98
#define RECOVERY_MOVE_raise 97
#define SLIT_MOVE 10
#define SLIT_MOVE_lower 9
#define SLIT_MOVE_pipe 8
#define SLIT_MOVE_raise 7

#define CHALLENGING_LOWPOS 170
#define DETACHED_LOWPOS false

#ifdef DEBUG_FEEDBACK
int feedback_update_msg=0;
#endif

void ShoeDrive::init() {
  pinMode(_motorson_pin, OUTPUT);
  pinMode(_motorsoff_pin, OUTPUT);
  digitalWrite(_motorson_pin, HIGH);
  digitalWrite(_motorsoff_pin, HIGH);
  pinMode(_sensor_pin, INPUT);
  digitalWrite(_sensor_pin, HIGH);
  motorsPowered=true;
  setMotorPower(false);

  _wait(SAMPLE_INTERVAL_MS*EWMA_SAMPLES);
  _pipe_motor->attach(_pipe_pin, (uint16_t) 1000, (uint16_t) 2000);
  _height_motor->attach(_height_pin, (uint16_t) 1000, (uint16_t) 2000);
  _pipe_motor->writeMicroseconds(_cfg.pos.pipe+1000);
  _height_motor->writeMicroseconds(_cfg.pos.height+1000);
  _wait(RC_PULSE_DELAY_SHORT);
  _pipe_motor->detach();
  _height_motor->detach();

  _height_moving=false;
  _pipe_moving=false;
  _timeLastPipeMovement=0;
  _timeLastHeightMovement=0;
  _moveInProgress=0;
  _samplet=0;
  _retries=1;
  _heading.pipe=1;
  _heading.height=1;

  _cfg.pipe_tol = DEFAULT_TOL;
  _cfg.height_tol = DEFAULT_TOL;
  _cfg.desired_slit = UNKNOWN_SLIT;
  const uint16_t default_heights[N_SLIT_POS] = {858, 839, 557, 530, 492, 220};
  for (uint8_t i=0;i<N_SLIT_POS;i++) {
    _cfg.pipe_pos[i]=119*i+224;
    _cfg.height_pos[i] = default_heights[i];
    _cfg.down_pos[i] = 135;
  }
  _cfg.idle_disconnected=DEFAULT_IDLE_DISCONNECTED;

}

ShoeDrive::~ShoeDrive() {
}

void ShoeDrive::defineTol(char axis, uint8_t tol) {
  if (axis=='H' && tol<=MAX_HEIGHT_TOL) _cfg.height_tol=tol;
  else if (axis=='P' && tol<=MAX_PIPE_TOL) _cfg.pipe_tol=tol;
}

void ShoeDrive::setMotorPower(bool enable) {
  if (enable == motorsPowered)
    return;
  if (!enable) {
    if (_pipe_motor->attached()) _pipe_motor->detach();
    if (_height_motor->attached()) _height_motor->detach();
  }
  uint8_t pin = enable ? _motorson_pin:_motorsoff_pin;
  digitalWrite(pin, LOW);
  _wait(MOTOR_RELAY_HOLD_MS);
  digitalWrite(pin, HIGH);
  motorsPowered=enable;
}

void ShoeDrive::stop() {
  //if not powered, don't power up!
  if (motorsPowered) {
    // to try and command where we are
    shoepos_t pos = getLivePosition();
    _move(_height_motor, pos.height, 0, false);
    _move(_pipe_motor, pos.pipe, 0, false);
    _wait(RC_PULSE_DELAY_SHORT);
    setMotorPower(false);
  }
  _cfg.desired_slit=UNKNOWN_SLIT;
  _moveInProgress=0;
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
  // NB this is correct even when detached
  shoepos_t pos;
  pos.pipe=_pipe_motor->readMicroseconds()-1000;
  pos.height=_height_motor->readMicroseconds()-1000;
  return pos;
}


bool ShoeDrive::getOffWhenIdle() {
  return _cfg.idle_disconnected;
}

void ShoeDrive::toggleOffWhenIdle() {
  _cfg.idle_disconnected=!_cfg.idle_disconnected;
}


uint16_t ShoeDrive::getSlitPosition(uint8_t slit) {
  return _cfg.pipe_pos[max(min(slit, N_SLIT_POS-1),0)];
}


uint16_t ShoeDrive::getHeightPosition(uint8_t height) {
  return _cfg.height_pos[max(min(height, N_SLIT_POS-1),0)];
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

void ShoeDrive::movePipe(uint16_t pos){
  // Danger. This does not do any checks.
  Serial.print(F("#Move pipe to "));Serial.println(pos);
  _moveInProgress=USER_MOVE_pipe;
  _cfg.desired_slit=UNKNOWN_SLIT;
  _movePipe(pos, RC_PULSE_DELAY, true);
}


inline void ShoeDrive::_movePipe(uint16_t pos, uint16_t wait, bool detach){
  _move(_pipe_motor, pos, wait, detach);
}


void ShoeDrive::moveHeight(uint16_t pos){
  // Danger. This does not do any checks.
  Serial.print(F("#Move H to "));Serial.println(pos);
  _moveInProgress=USER_MOVE_height;
  _cfg.desired_slit=UNKNOWN_SLIT;
  _moveHeight(pos+15, RC_PULSE_DELAY_SHORT, false); //twitch up first
  _moveHeight(pos, RC_PULSE_DELAY, _detachHeight(pos));
}


inline void ShoeDrive::_moveHeight(uint16_t pos, uint16_t wait, bool detach){
  _move(_height_motor, pos, wait, detach);
}

void ShoeDrive::_move(Servo *axis, uint16_t pos, uint16_t wait, bool detach){

  // Danger. This does not do any checks.

  int8_t heading=0;
  uint8_t pin;
  uint16_t last;

  last=axis->readMicroseconds()-1000;
  if (pos < last) heading = -1;
  else if (pos > last) heading = 1;

  if (axis==_height_motor) {
    _heading.height=heading==0 ? _heading.height:heading;
    pin=_height_pin;
    _timeLastHeightMovement=millis();
  } else {
    _heading.pipe=heading==0 ? _heading.pipe:heading;
    pin=_pipe_pin;
    _timeLastPipeMovement=millis();
  }

  setMotorPower(true);
  if (!axis->attached()) axis->attach(pin, (uint16_t) 1000, (uint16_t) 2000);
  axis->writeMicroseconds(min(max(pos+1000,1000),2000));
  _wait(wait);
  if (detach && ENABLE_DETACH) axis->detach();
}


bool ShoeDrive::safeToMovePipes() {
  shoepos_t cur = getFilteredPosition();
  shoepos_t cmd = getCommandedPosition();

  return (cmd.height<=safe_pipe_height &&                  // commanded to a low enough point
          cur.height<=safe_pipe_height + _cfg.height_tol); // Clear of the pipes

}

bool ShoeDrive::fibersAreUp() {
  //The logic here is as follows:
  // -verify within tolerance of slits height setting
  // -the height moving check checks to see if we've stabilized
  shoepos_t cur = getFilteredPosition();
  shoepos_t cmd = getCommandedPosition();
  uint16_t err=abs((int)cur.height-(int)_cfg.height_pos[_cfg.desired_slit]);
  return (cmd.height==_cfg.height_pos[_cfg.desired_slit] &&
          err < _cfg.height_tol &&
          !heightMoving());
}

void ShoeDrive::getState(shoecfg_t &data) {
  data=_cfg;
}

void ShoeDrive::restoreState(shoecfg_t data) {
  _cfg = data;
  _cfg.idle_disconnected=DEFAULT_IDLE_DISCONNECTED;
}

bool ShoeDrive::idle() {
  return _moveInProgress==SHOE_IDLE;
}


int16_t ShoeDrive::getPipeError() {
  //not meaningful if commanded position isn't via a slit
  return (int)_cfg.pos.pipe - (int)_cfg.pipe_pos[min(_cfg.desired_slit, N_SLIT_POS-1)];
}

int16_t ShoeDrive::getHeightError() {
   //not meaningful if commanded position isn't via a slit
  return (int)_cfg.pos.height - (int)_cfg.height_pos[min(_cfg.desired_slit, N_SLIT_POS-1)];
}

uint8_t ShoeDrive::_currentPipeIndex() {
  //Returns index into pipe pos if within tolerance else 0xff
  uint16_t m=2000; //min
  uint8_t ndx=0xff;
  for (uint8_t i=0;i<N_SLIT_POS;i++) {
    uint16_t delta = abs((int)_cfg.pos.pipe - (int)_cfg.pipe_pos[i]);
    if (delta <= _cfg.pipe_tol && delta<m) {
      m=delta;
      ndx=i;
    }
  }
  return ndx;
}


void ShoeDrive::_wait(uint32_t time_ms) {
  uint32_t tic=millis();
  while (millis()-tic<time_ms) _updateFeedbackPos();
}


shoestatus_t ShoeDrive::_status() {
  shoestatus_t x;
  x.pos=getFilteredPosition();
  x.target=getCommandedPosition();
  x.error.pipe = (int) _cfg.pos.pipe - (int)x.target.pipe;
  x.error.height = (int) _cfg.pos.height - (int) x.target.height;
  x.moving.height=heightMoving();
  x.moving.pipe=pipeMoving();
  x.heading=_heading;
  return x;
}

uint16_t ShoeDrive::_clearance_height(uint8_t slit) {
  //given the current position and a destination slit
  //return the height below which we need to be for pipe safety

  // This function uses _cfg.pos for figuring out the current pipe position so
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


  int pipe = (int) _cfg.pos.pipe;
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
  Serial.print(F("#Clearance "));Serial.print(clearance);
  Serial.print(F(" move from "));Serial.print((int)current+1);
  Serial.print(" (");Serial.print(pipe);
  Serial.print(F(") to "));Serial.println((int)slit+1);
  return clearance;

}


bool ShoeDrive::_detachHeight(uint16_t height) {
  return (ENABLE_DETACH && (DETACHED_LOWPOS || height>CHALLENGING_LOWPOS));
}


void ShoeDrive::run(){

  // Monitor position
  _updateFeedbackPos();
  shoestatus_t stat = _status();


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
          Serial.println(F("#No retry left. IDLE."));
          tellStatus();
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
            Serial.print(F("#Pipe to SL 1"));
            if (abs((int)stat.target.pipe-(int)_cfg.pipe_pos[0])< 50) {
              Serial.print(F(", twitch 1st"));
              _movePipe(_cfg.pipe_pos[0]-50, RC_PULSE_DELAY_SHORT, false);
            }
            Serial.println("");
            _movePipe(_cfg.pipe_pos[0], RC_PULSE_DELAY, true);
            _moveInProgress=RECOVERY_MOVE_pipe;

          } else if (errors & E_PIPESTALL) {

            uint16_t dest = stat.target.pipe - 200;//0*stat.heading.pipe;
            Serial.print(F("#Pipe retry "));Serial.print(stat.target.pipe);Serial.print(F(" via "));Serial.println(dest);
            // E_PIPESTALL: pipe didn't get to where it was sent. if height is down we can send it safely whereever,
            // if height isn't safe then simplest to handle it like a height stall (see above)
            _movePipe(dest, RC_PULSE_DELAY_SHORT, false);
            _movePipe(stat.target.pipe, RC_PULSE_DELAY, true);
            errors=0;
            _moveInProgress=SLIT_MOVE_pipe;

          } else if (errors & E_HEIGHTSTUCK) {

            Serial.println(F("#Raise fail, lower"));
            // E_HEIGHTSTUCK: height didn't up get to where it was sent. if pipes aren't where they need to be then
            // that would cause this (though that isn't possible by sw. design), just lower back down and let the cycle go again
            _moveHeight(_clearance_height(_cfg.desired_slit)+20, RC_PULSE_DELAY_SHORT, false);
            _moveHeight(_clearance_height(_cfg.desired_slit), RC_PULSE_DELAY, DETACHED_LOWPOS);
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
          _moveHeight(_cfg.height_pos[0], RC_PULSE_DELAY, true);
          _moveInProgress=RECOVERY_MOVE_raise;
      } else  { //transition to RECOVERY_MOVE
        _moveInProgress=RECOVERY_MOVE;
        errors|=E_RECOVER;
        Serial.print(F("#ERROR: RECOVERY_MOVE_pipe"));Serial.println(stat.error.pipe);
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
    _cfg.pos filtered analog position
    stat.target position being written via PWM
    stat.pos filtered analog position
    stat.error difference between commanded and filtered analog (NOT based on _cfg.desired_slit)
    */
    case SLIT_MOVE: //new move, lower cassette
      errors=0;
      safe_pipe_height = _clearance_height(_cfg.desired_slit);
      Serial.print(F("#Starting move to ")); Serial.print((uint16_t)_cfg.desired_slit+1);
      Serial.print(F(". Lowering, safe height "));Serial.println(safe_pipe_height);
      Serial.print(F("#Free Mem:"));Serial.println(freeMemory());
      //This first move is a tweak for dealing with LAC pulse width oddities. 20 is tied to the LAC settings (i.e. it needs to be set so that the LAC sees the two as distinct positions)
      _moveHeight(safe_pipe_height+20, RC_PULSE_DELAY_SHORT, false);
      _moveHeight(safe_pipe_height, RC_PULSE_DELAY, false);
      _moveInProgress=SLIT_MOVE_lower;
      break;
    case SLIT_MOVE_lower:  //lowering in process
      //Alow pipes to move while the height is twitching at the bottom!
      if (safeToMovePipes()) { //transition to SLIT_MOVE_pipes
        //We detach if enabled, but DETACHED_LOWPOS controls this seperately for positions < CHALLENGING_LOWPOS
        if (_detachHeight(stat.target.height)) _height_motor->detach();
        errors=0;
        Serial.print(F("#Down ("));Serial.print(stat.error.height);Serial.println(F("), moving pipe."));
        _movePipe(_cfg.pipe_pos[min(_cfg.desired_slit, N_SLIT_POS-1)], RC_PULSE_DELAY, true);
        _moveInProgress=SLIT_MOVE_pipe;

      } else if (!stat.moving.height){ //transition to RECOVERY_MOVE we are stalled breaks if stall timeout is too short to detect real movement
        if (_detachHeight(stat.pos.height)) _height_motor->detach();
        Serial.print(F("#ERROR: Height not down ")); Serial.println(stat.error.height);
        errors|=E_HEIGHTSTALL;
        _moveInProgress=RECOVERY_MOVE;
      }
      break;
    case SLIT_MOVE_pipe: // moving pipes into position
      if (stat.moving.pipe) {
        safe_pipe_height = _clearance_height(_cfg.desired_slit);
        if (!safeToMovePipes()) { // transition to RECOVERY_MOVE
          Serial.print(F("#Height moved too high: "));Serial.print(stat.error.height);Serial.println(F(". Stoping pipe."));
          _movePipe(stat.pos.pipe, RC_PULSE_DELAY_SHORT, true);
          _moveInProgress=RECOVERY_MOVE;
          errors|=E_HEIGHTMOVEDUP;
        } // else nothing to do but wait
      } else if (_currentPipeIndex() == _cfg.desired_slit) { // transition to SLIT_MOVE_raise
          errors=0;
          Serial.print(F("#Pipe done ("));Serial.print(stat.error.pipe);Serial.println(F("), raising."));
          _moveHeight(_cfg.down_pos[min(_cfg.desired_slit, N_SLIT_POS-1)]+30, RC_PULSE_DELAY_SHORT, false);
          _moveHeight(_cfg.height_pos[min(_cfg.desired_slit, N_SLIT_POS-1)], RC_PULSE_DELAY, false);
          _moveInProgress=SLIT_MOVE_raise;
      } else  { //transition to RECOVERY_MOVE
        Serial.print(F("#ERROR: Pipe error too large: "));Serial.println(stat.error.pipe);
        errors|=E_PIPESTALL;
        _moveInProgress=RECOVERY_MOVE;
      }
      break;
    case SLIT_MOVE_raise: // raising cassette
      if (stat.moving.height) {
        if (_currentPipeIndex() != _cfg.desired_slit) {
          Serial.print(F("#Pipe shifted "));Serial.print(stat.error.pipe);Serial.println(F(". Lowering."));
          _moveHeight(_clearance_height(_cfg.desired_slit), RC_PULSE_DELAY_SHORT, true); //NB detach here is a it of a guess
          errors|=E_PIPESHIFT;
          _moveInProgress=RECOVERY_MOVE;
        } // else nothing to do but wait
      } else if (fibersAreUp()) { //transition to SHOE_IDLE
          if (_detachHeight(stat.target.height)) _height_motor->detach();
          Serial.print(F("#Raised ("));Serial.print(stat.error.height);Serial.print(F("). Slit"));Serial.println((int) _cfg.desired_slit+1);
          _moveInProgress=SHOE_IDLE;
          errors=0;
      } else { //transition to RECOVERY_MOVE
          if (_detachHeight(stat.target.height)) _height_motor->detach();
          Serial.print(F("#ERROR: Height stopped too low:"));Serial.println(stat.error.height);
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
      if (_cfg.idle_disconnected) setMotorPower(false);
      break;
    default:
      break;
  }

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
    uint32_t toc = micros();
    if (feedback_update_msg>0) {
      Serial.print(F("Height ADC: "));Serial.print(MAX_ADC-adu);Serial.println(".");
      Serial.print(F("Filtered: "));Serial.print(tmp);Serial.print("*");Serial.print(ADU_TO_STEP);
      Serial.print("=");Serial.println(pos.height);
      Serial.print(F("Update feedback took "));Serial.print(toc-t);Serial.println(" us.");
      feedback_update_msg--;
    }
#endif DEBUG_FEEDBACK
  }

  _cfg.pos.pipe=pos.pipe;
  if (abs((int)pos.pipe-(int)_movepos.pipe)>MOVING_PIPE_TOL){
    if (!_pipe_moving) {
      Serial.print(F("## "));
      Serial.print(_shoe_name);
      Serial.println(F(" Pipe  move ##"));
    }
    _pipe_moving=true;
    _timeLastPipeMovement=t_ms;
    _movepos.pipe=pos.pipe;
  } else if (millis()-_timeLastPipeMovement > MOVING_TIMEOUT_MS) {
    if (_pipe_moving) {
      Serial.print(F("## "));
      Serial.print(_shoe_name);
      Serial.println(F(" Pipe  stop ##"));
    }
    _pipe_moving=false;
  }

  _cfg.pos.height=pos.height;
  if (abs((int)pos.height-(int)_movepos.height)>MOVING_HEIGHT_TOL){
    if (!_height_moving) {
      Serial.print(F("## "));
      Serial.print(_shoe_name);
      Serial.println(F(" Height move ##"));
    }
    _height_moving=true;
    _timeLastHeightMovement=t_ms;
    _movepos.height=pos.height;
  } else if (millis()-_timeLastHeightMovement > MOVING_TIMEOUT_MS) {
    if (_height_moving) {
      Serial.print(F("## "));
      Serial.print(_shoe_name);
      Serial.println(F(" Height stop ##"));
    }
    _height_moving=false;
  }

}



void ShoeDrive::tellStatus() {

  shoepos_t pos, cpos;
  _wait(SAMPLE_INTERVAL_MS);

  #ifdef DEBUG_FEEDBACK
  feedback_update_msg=1;
  #endif

  _updateFeedbackPos();

  Serial.print(F("==="));Serial.print(_shoe_name);
  Serial.println(F(" Shoe Status===\n (pipe, height)"));
  uint64_t tmp;
  tmp=_pipe_filter.output();
  Serial.print(" ADC: ");
    if (tmp>=0xffffffff) Serial.print("***");
    else Serial.print((uint32_t)tmp);
    Serial.print(", ");
    tmp=_height_filter.output();
    if (tmp>=0xffffffff) Serial.print("***");
    else Serial.println((uint32_t)tmp);


  cpos=getCommandedPosition();
  Serial.print(F(" Servo: "));Serial.print(cpos.pipe);Serial.print(F(", "));Serial.println(cpos.height);
  pos=getLivePosition();
  Serial.print(F(" Pos (live): "));
    Serial.print(_cfg.pos.pipe);Serial.print(" ("); Serial.print(pos.pipe);Serial.print(F("), "));
    Serial.print(_cfg.pos.height);Serial.print(" (");Serial.print(pos.height);Serial.print(")\n");
  Serial.print(F(" Err: ")); Serial.print((int) _cfg.pos.pipe - (int)cpos.pipe);Serial.print(F(", "));Serial.println((int) _cfg.pos.height - (int) cpos.height);

  Serial.print(F(" Attached: "));Serial.print(_pipe_motor->attached());Serial.print(F(", "));Serial.println(_height_motor->attached());
  Serial.print(F(" Moving: "));Serial.print(pipeMoving());Serial.print(F(", "));Serial.println(heightMoving());
  Serial.print(F("  ms since move: "));
    Serial.print(millis()-_timeLastPipeMovement);Serial.print(F(", "));
    Serial.println(millis()-_timeLastHeightMovement);
  Serial.print(F(" SL: "));Serial.println((int)_cfg.desired_slit+1);
  Serial.print(F("  SL Delta: ")); Serial.print(getPipeError());Serial.print(F(", "));Serial.println(getHeightError());
  Serial.print(F(" Toler: ")); Serial.print(_cfg.pipe_tol);Serial.print(F(", "));Serial.println(_cfg.height_tol);


  Serial.print(F("Desired Slit: ")); Serial.println((uint16_t) _cfg.desired_slit+1);
  Serial.print(F("Detected Slit: "));tellCurrentSlit();Serial.println();

  Serial.print(F("Errors: "));Serial.print(errors, BIN);
    Serial.print(F(" MiP: "));Serial.print(_moveInProgress);
    Serial.print(F(" Safe: "));Serial.print(safeToMovePipes());
    Serial.print(F(" Relay: "));Serial.print(motorsPowered);
    Serial.print(F(" Idleoff: "));Serial.print(_cfg.idle_disconnected);
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
