#include "Tetris.h"
Tetris::Tetris() {

}

Tetris::Tetris(int rst_pin, int stby_pin, int dir_pin, int ck_pin, int phase_pin) {

	_reset_pin=rst_pin;
	_standby_pin=stby_pin;  //Pin should be low to standby part
	_clock_pin=ck_pin;
	_dir_pin=dir_pin;
	_phase_pin=phase_pin;
  
	_calibrated=false;
  _calibration_in_progress=0;
  _lastDir=1;
  _backlash=DEFAULT_BACKLASH;
    _homed_move_in_progress=0;
	
	_slitPositions[0]=DEFAULT_POS_SLIT1;
	_slitPositions[1]=DEFAULT_POS_SLIT2;
	_slitPositions[2]=DEFAULT_POS_SLIT3;
	_slitPositions[3]=DEFAULT_POS_SLIT4;
	_slitPositions[4]=DEFAULT_POS_SLIT5;
	_slitPositions[5]=DEFAULT_POS_SLIT6;
	_slitPositions[6]=DEFAULT_POS_SLIT7;
  
  pinMode(_reset_pin, OUTPUT);
  pinMode(_standby_pin, OUTPUT);
  digitalWrite(_reset_pin, LOW);
  digitalWrite(_standby_pin, LOW);

  _motor=AccelStepper(1, _clock_pin, _dir_pin);
//  _motor.setEnablePin(_standby_pin);
  _motor.setMinPulseWidth(50);   // in us
  
  //256*20*16 pulses per revolution
  //<=683 pulses of backlash per 06/1 datasheet at 16x ustepping
  
  //If 16x ustepping
  //Max with 8 motors around 411 with v1.27 of accelstepper
  setSpeed(300);       // steps/second  
  setAcceleration(1000);
  
	
  //If full stepping
//  setSpeed(50);       // steps/second 
//  setAcceleration(700);

  digitalWrite(_phase_pin, HIGH); //enable pullup
  pinMode(_phase_pin, INPUT);

}

Tetris::~Tetris() {
	_motor.~AccelStepper();	
}

bool Tetris::isCalibrated() {
  return _calibrated;
}

void Tetris::defineSlitPosition(uint8_t slit, long position) {
  if (slit < N_SLIT_POS-1) {
    if (slit == 0) {
      for (uint8_t i=1; i<N_SLIT_POS-1; i++) {
        _slitPositions[i]-=_slitPositions[0]; //get relative offsets
      }
      _slitPositions[0]=position; // new 0
      for (uint8_t i=1; i<N_SLIT_POS-1; i++) {
        _slitPositions[i]+=_slitPositions[0]; //convert back to slit positions
      }
    }
    else {
      _slitPositions[slit]=_slitPositions[0]+position;
    }
  }
}

void Tetris::defineSlitPosition(uint8_t slit) {
  if (slit < N_SLIT_POS-1) {
    if (slit == 0) {
      for (uint8_t i=1; i<N_SLIT_POS-1; i++) {
        _slitPositions[i]-=_slitPositions[0]; //get relative offsets
      }
      _slitPositions[0]=_motor.currentPosition(); //new 0
      for (uint8_t i=1; i<N_SLIT_POS-1; i++) {
        _slitPositions[i]+=_slitPositions[0]; //convert back to slit positions
      }
    }
    else {
      _slitPositions[slit]=_motor.currentPosition();
    }
  }
}

void Tetris::dumbMoveToSlit(uint8_t slit) {
  if (slit>=0 && slit <8)
    positionAbsoluteMove(_slitPositions[slit]);
}

void Tetris::homedMoveToSlit(uint8_t slit) {
    if (slit>=0 && slit <8) {
        _targetAfterHome=_slitPositions[slit];
        _homed_move_in_progress=2;
        moveToHardStop();
    }
}

void Tetris::moveToHardStop() {
    //Move to the hardstop, based on the current position
    // will overshoot by _backlash to ensure we hit the stop
    if (_motor.currentPosition() > 0 ) {
        positionRelativeMove((-_motor.currentPosition()) - HOME_MOVE_OVERSHOOT);
    } else if (_motor.currentPosition() < 0 ) {
        positionRelativeMove((-_motor.currentPosition()) + HOME_MOVE_OVERSHOOT);
    }
}

void Tetris::run(){
  //Calibration is a three step process, move to limit, then
  // move to take out the backlash
  // then stop and call position 0
  if (_calibration_in_progress != 0 && 
      _motor.currentPosition() == _motor.targetPosition()) {
    if (_calibration_in_progress==2) { //enter second stage
      _motor.setCurrentPosition(_backlash);
      _motor.moveTo(0);
      _calibration_in_progress=1;
    }
    else { // final stage, we are calibrated
      _calibrated=true;
      _calibration_in_progress=0;
      _lastDir=-1;
    }
  }
  //Homed moves happen in two(three?) stages
  //
  if (_homed_move_in_progress != 0 &&
      _motor.currentPosition() == _motor.targetPosition() ) {
      if (_homed_move_in_progress==2) {
          _motor.setCurrentPosition(_backlash);
          _motor.moveTo(0);
          _homed_move_in_progress=1;
      }
      else {
          _lastDir=-1;
          positionAbsoluteMove(_targetAfterHome);
          _homed_move_in_progress=0;
          
      }
  }
  
  //Move the motor
  _motor.run();
}


void Tetris::motorOff() {
  //Per TB6608 datasheet: STBY must be low @ pwr on/off
  digitalWrite(_standby_pin, LOW);
}


//Caution, may block for a while 
void Tetris::motorPwrOffPos(){
	if (_motor.currentPosition()>=MOTOR_HOME_POSITION) {
		positionAbsoluteMove(MOTOR_HOME_POSITION-2*_backlash);
		while(_motor.run());
	}
	positionAbsoluteMove(MOTOR_HOME_POSITION);
}

void Tetris::motorOn() {
  digitalWrite(_reset_pin, HIGH);
  digitalWrite(_standby_pin, HIGH);
}

bool Tetris::motorIsOn() {
  return digitalRead(_standby_pin);
}

void Tetris::setBacklash(unsigned int b){
  _backlash=b;
}

uint16_t Tetris::getBacklash(){
    return _backlash;
}

void Tetris::tellBacklash() {
    Serial.print(_backlash);
}

void Tetris::tellPosition() {
  Serial.print(_motor.currentPosition());
}

int32_t Tetris::currentPosition() {
  return _motor.currentPosition();
}

int32_t Tetris::getSlitPosition(uint8_t slit) {
    if ( slit > N_SLIT_POS-2) return 0;
    if (slit == 0) return _slitPositions[0];
    else return _slitPositions[slit]-_slitPositions[0];
}

void Tetris::tellSlitPosition(uint8_t slit) {
  Serial.print(getSlitPosition(slit));
}
  
//No Deceleration
void Tetris::stop() {
  _motor.moveTo(_motor.currentPosition());
}

bool Tetris::moving(){
  return _motor.currentPosition() != _motor.targetPosition();
}

void Tetris::definePosition(long p) {
  _calibrated=true;
  _calibration_in_progress=0;
  _motor.setCurrentPosition(p);
}

void Tetris::setSpeed(int s) {
  _motor.setMaxSpeed(s);
}

void Tetris::setAcceleration(long	s){
  _motor.setAcceleration(abs(s));
}

void Tetris::positionRelativeMoveFS(long d){
  positionAbsoluteMove( d*USTEPPING + _motor.currentPosition());
}

void Tetris::positionAbsoluteMoveFS(long p){
  positionAbsoluteMove(USTEPPING*p);
}

char Tetris::getCurrentSlit() {
  for (unsigned char i=0; i<7; i++) {
    if (_motor.currentPosition()==_slitPositions[i]) {
      return i;
    }
  }
  return -1;
}

void Tetris::positionRelativeMove(long d){
  positionAbsoluteMove(d + _motor.currentPosition());
}

void Tetris::positionAbsoluteMove(long p){
  if (p == _motor.currentPosition()) return;
  //Handle backlash
  if (_lastDir<0 && (p>_motor.currentPosition()))
  {
      _motor.setCurrentPosition(_motor.currentPosition()-_backlash);
      _lastDir=1;
  }
  else if (_lastDir>0 && p<_motor.currentPosition())
  {
      _motor.setCurrentPosition(_motor.currentPosition()+_backlash);
      _lastDir=-1;
  }
  //Move
  motorOn();
  _motor.moveTo(p);
}



//Function WILL cause stall at negative physical limit.
void Tetris::calibrateToHardStop(){
  _calibrated=false;
  _motor.setCurrentPosition(0);
  motorOn();
  _motor.moveTo(MAX_HARDSTOP_DISTANCE);
  _calibration_in_progress=2; //First stage
}