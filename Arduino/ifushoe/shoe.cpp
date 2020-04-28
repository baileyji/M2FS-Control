#import "shoe.h"

#define DEFAULT_IDLE_DISCONNECTED false
#define MOTOR_RELAY_HOLD_MS 50  //blind guess
#define SAMPLE_INTERVAL_MS 3
#define EWMA_SAMPLES 7

#define MOVING 0xFE
#define UNKNOWN_SLIT 0xFF
#define DEFAULT_TOL 3   // about 0.33mm, 20mm/180 per unit

#define MAX_ADC 1023
#define ADU_PER_STEP 5.03333333// 1.0929  0=11 180=964
#define CALIB_STEP_TIME_MS 6000
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
                     , _pipe_filter(1,EWMA_SAMPLES)     //about 10 samples
                     , _height_filter(1,EWMA_SAMPLES)
                     , _pipe_motor(p)
                     , _height_motor(h) {
}


void ShoeDrive::init() {
  pinMode(_motorson_pin, OUTPUT);
  pinMode(_motorsoff_pin, OUTPUT);
  digitalWrite(_motorson_pin, HIGH);
  digitalWrite(_motorsoff_pin, HIGH);
  pinMode(_sensor_pin, INPUT);
  digitalWrite(_sensor_pin, HIGH);
  motorsConnected=true;
  disconnectMotors();

  _timeLastPipeMovement=0;
  _timeLastHeightMovement=0;
  _moveInProgress=0;
  _samplet=0;

  _pipe_motor->attach(_pipe_pin, (uint16_t) 1000, (uint16_t) 2000);
  _height_motor->attach(_height_pin, (uint16_t) 1000, (uint16_t) 2000);

  _cfg.pos.pipe=_pipe_filter.filter(512);
  _cfg.pos.height=_height_filter.filter(512);
  _cfg.pipe_tol = DEFAULT_TOL;
  _cfg.height_tol = DEFAULT_TOL;
  _cfg.desired_slit=UNKNOWN_SLIT;
  _cfg.height_lim[0]=0;
  _cfg.height_lim[1]=MAX_ADC;
  _cfg.pipe_lim[0]=0;
  _cfg.pipe_lim[1]=MAX_ADC;
  for (uint8_t i=1;i<N_SLIT_POS+1;i++)
    _cfg.pipe_pos[i]=25*i;
  _cfg.height_pos[0]=25;
  _cfg.height_pos[1]=150;
  _cfg.idle_disconnected=DEFAULT_IDLE_DISCONNECTED;

}

ShoeDrive::~ShoeDrive() {
//  _pipe_motor.~Servo();
//  _height_motor.~Servo(); 
}

void ShoeDrive::disconnectMotors() {
  if (motorsConnected) {
    digitalWrite(_motorsoff_pin, LOW);
    delay(MOTOR_RELAY_HOLD_MS);
    digitalWrite(_motorsoff_pin, HIGH);
    motorsConnected=false;
  }
}

void ShoeDrive::connectMotors() {
  if (!motorsConnected) {
    digitalWrite(_motorson_pin, LOW);
    delay(MOTOR_RELAY_HOLD_MS);
    digitalWrite(_motorson_pin, HIGH);
    motorsConnected=true;
  }
}

void ShoeDrive::stop() {
  _pipe_motor->write(_cfg.pos.pipe);
  _height_motor->write(_cfg.pos.height);
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
  //Filtered, Not instant, requires run() to be called regularly
  shoepos_t pos;

  int adu;
  uint64_t tmp;
  adu=analogRead(_pipe_pot_pin);
  tmp=_pipe_filter.filter(MAX_ADC-adu)-_cfg.pipe_lim[0];
  pos.pipe=round(tmp*180.0/(float)_cfg.pipe_lim[1]);

  adu=analogRead(_height_pot_pin);
  tmp=_height_filter.filter(MAX_ADC-adu)-_cfg.height_lim[0];
  pos.height=round(tmp*180.0/(float)_cfg.height_lim[1]);
  return pos;
}

shoepos_t ShoeDrive::getCommandedPosition() {
  shoepos_t pos;
  pos.pipe = _pipe_motor->read();
  pos.height = _height_motor->read();
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

  Serial.println(F("Shoe Status: (pipe, height)"));
  Serial.print(F(" Pos: ")); Serial.print(_cfg.pos.pipe);
  pos=getLivePosition();
  Serial.print(" ("); Serial.print(pos.pipe);
  Serial.print("), "); Serial.print(_cfg.pos.height);
  Serial.print(" (");Serial.print(pos.height);
  Serial.print(")\n");
  
  pos=getCommandedPosition();
  Serial.print(F("Servo: "));Serial.print(pos.pipe);Serial.print(", ");Serial.println(pos.height);
  Serial.print(F("Time: "));Serial.print(millis()-_timeLastPipeMovement);
  Serial.print(", ");Serial.println(millis()-_timeLastHeightMovement);
  Serial.print(F("Moving: "));Serial.print(pipeMoving());Serial.print(", ");
  Serial.println(heightMoving());

  tellCurrentSlit();
  Serial.println();
  
  Serial.print(F("Errors: "));Serial.println(errors, BIN);
  Serial.print(F("MIP: "));Serial.println(_moveInProgress);
  Serial.print(F("Button: "));Serial.println(downButtonPressed());
  Serial.print(F("Safe: "));Serial.println(safeToMovePipes());
  Serial.print(F("Relay: "));Serial.println(motorsConnected);
  Serial.print(F("Idleoff: "));Serial.println(_cfg.idle_disconnected);
  Serial.print(F("CPI: "));Serial.println(_currentPipeIndex());
  Serial.print(F("Desired Slit: ")); Serial.println((uint16_t) _cfg.desired_slit);
  Serial.print(F("Pipe Delta: ")); Serial.print(_cfg.pos.pipe - _cfg.pipe_pos[_cfg.desired_slit]); Serial.print(F(" Tol: ")); Serial.println(_cfg.pipe_tol);

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
  slit=max(min(slit, N_SLIT_POS-1),0);
  return _cfg.pipe_pos[slit];
}


uint16_t ShoeDrive::getHeightPosition(uint8_t height) {
  height=max(min(height, N_HEIGHT_POS-1),0);
  return _cfg.height_pos[height];
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
  defineSlitPosition(slit, _pipe_motor->read());    
}

    
void ShoeDrive::defineHeightPosition(uint8_t height, uint16_t pos){
  if (height>N_HEIGHT_POS-1) return;
  _cfg.height_pos[height] = pos;
}


void ShoeDrive::defineHeightPosition(uint8_t height){
  defineHeightPosition(height, _height_motor->read());  
}


void ShoeDrive::moveToSlit(uint8_t slit) { //kick off a move
  if (slit>N_SLIT_POS-1) return;
  if (_cfg.desired_slit!=slit) {
    _moveInProgress=10;
    _cfg.desired_slit=slit;
  }
}


void ShoeDrive::movePipe(uint16_t pos){
  // Danger. This does not do any checks.
  Serial.print(F("#Moving pipe to "));Serial.println(pos);
  connectMotors();
  _moveInProgress=1;
  _cfg.desired_slit=UNKNOWN_SLIT;
  _pipe_motor->write(pos);
  delay(50);
}

void ShoeDrive::moveHeight(uint16_t pos){
  // Danger. This does not do any checks.
  Serial.print(F("#Moving H to "));Serial.println(pos);
  connectMotors();
  _moveInProgress=2;
  _cfg.desired_slit=UNKNOWN_SLIT;
  _height_motor->write(pos);
  delay(50);
}

bool ShoeDrive::downButtonPressed(){
  return !digitalRead(_sensor_pin);
}

bool ShoeDrive::safeToMovePipes() {
  //The logic here is as follows:
  // -The read command verifies that the setpoint is down
  // -The down button is pressed
  // -The _cfg.pos.height is below the clearance point
  return (_cfg.pos.height<PIPE_CLEARANCE_HEIGHT &&
          _height_motor->read()==_cfg.height_pos[DOWN_NDX]); //&&
          //downButtonPressed());  //TODO UNCOMMENT WHEN BUTTONS WORK
}

bool ShoeDrive::fibersAreUp() {
  //The logic here is as follows:
  // -the read command verifies that the setpoint is UP
  // -the height moving check checks to see if we've stabilized
  // -The down button isn't pressed
  // - we could check _cfg.pos.height>PIPE_CLEARANCE_HEIGHT but that is only reflective of the
  //   drive as the linkage could be slack
  return _height_motor->read()==_cfg.height_pos[UP_NDX] && !heightMoving() && !downButtonPressed();
}

void ShoeDrive::getEEPROMInfo(shoecfg_t &data) {
  data=_cfg;
}

void ShoeDrive::restoreEEPROMInfo(shoecfg_t data) {
  shoepos_t tmp;
  _cfg = data;
}

bool ShoeDrive::idle() {
  return _moveInProgress==0;
}

void ShoeDrive::calibrate(){
  //Assumes extremal movements are safe
  if (!idle()) return;
  Serial.println(F("Calibrating lowered pos. Move down"));
  moveHeight(0);
  _wait(CALIB_STEP_TIME_MS);
  _cfg.height_lim[0]=_height_filter.output();
  Serial.print(F("HRetracted="));Serial.println(_cfg.height_lim[0]);

  Serial.println(F("Calibrating Pipes. Retracting"));
  movePipe(0);
  _wait(CALIB_STEP_TIME_MS);
  _cfg.pipe_lim[0]=_pipe_filter.output();
  Serial.print(F("PRetracted="));Serial.println(_cfg.pipe_lim[0]);

  Serial.println(F("Calibrating Pipes. Extending"));
  movePipe(180);
  _wait(CALIB_STEP_TIME_MS);
  _cfg.pipe_lim[1]=_pipe_filter.output()-_cfg.pipe_lim[0];
  Serial.print(F("PExtended="));Serial.println(_cfg.pipe_lim[1]+_cfg.pipe_lim[0]);

  Serial.println(F("Pipes done, moving to slit 0"));
  _pipe_motor->write(_cfg.pipe_pos[0]);
  _cfg.desired_slit=0;
  _wait(CALIB_STEP_TIME_MS);

  Serial.println(F("Calibrating full height. Move up"));
  moveHeight(180);
  _wait(CALIB_STEP_TIME_MS);
  _cfg.height_lim[1]=_height_filter.output()-_cfg.height_lim[0];
  Serial.print(F("HExtended="));Serial.println(_cfg.height_lim[1]+_cfg.height_lim[0]);
}


void ShoeDrive::run(){

  // Monitor position
  _updateFeedbackPos();

  //Execute move: lower, wait, move pipes, wait, raise, wait, done
  bool _heightMoving = heightMoving();
  bool _pipeMoving = pipeMoving();
  
  switch (_moveInProgress) {
    case 10: //new move, lower cassette
      Serial.print(F("Starting move to "));
      Serial.print((uint16_t)_cfg.desired_slit);
      Serial.println(F("...lowering down"));
      connectMotors();
      _height_motor->write(_cfg.height_pos[DOWN_NDX]);
      _moveInProgress--;
      errors=0;
      break;
    case 9: // move pipes
      if (safeToMovePipes()) {
        Serial.println(F("Safely down, starting pipe move"));
        _pipe_motor->write(_cfg.pipe_pos[max(_cfg.desired_slit, N_SLIT_POS-1)]);
        _moveInProgress--;
        errors=0;
      } else if (!_heightMoving) {
        Serial.println(F("Height not moving, yet not safe"));
        errors|=E_HEIGHTSTALL;
      }
      break;
    case 8: // raise cassette
      if (!_pipeMoving) {
        if(_currentPipeIndex()==_cfg.desired_slit) {
          Serial.println(F("Pipe done, raising"));
          _height_motor->write(_cfg.height_pos[UP_NDX]);
          _moveInProgress--;
          errors=0;
        } else  {
          if(errors==0) Serial.println(F("Pipe not moving, not in position"));
          errors|=E_PIPESTALL;
        }
      }
      break;
    case 7: //All done
      if (!_heightMoving) {
        if (fibersAreUp()) {
          Serial.println(F("All done"));
          _moveInProgress=0;
          errors=0;
        } else {
          if(errors==0) Serial.println(F("Fibers not up"));
//          if (_cfg.idle_disconnected) {
//            Serial.println(F("Disconnecting motors"));
//            disconnectMotors();
//          }
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
      if (_cfg.idle_disconnected) disconnectMotors();
      break;
    default:
      break;
  }

}


uint8_t ShoeDrive::_currentPipeIndex() {
  //Returns index into pipe pos if within tolerance else 0xff
  for (uint8_t i=0;i<N_SLIT_POS;i++)
    if (abs(_cfg.pos.pipe - _cfg.pipe_pos[i]) <= _cfg.pipe_tol)
      return i;
  return 0xff;
}

uint8_t feedback_update_msg=10;
void ShoeDrive::_wait(uint32_t time_ms) {
  uint32_t tic=millis();
  while (millis()-tic<time_ms) {
//    if (((millis()-tic)/500) %2) {
//      feedback_update_msg=1;
//    }
    _updateFeedbackPos();
  }
}

void ShoeDrive::_updateFeedbackPos() {
  shoepos_t pos;
  int adu;
  uint64_t tmp;
  uint32_t t = millis();
  if (t-_samplet>SAMPLE_INTERVAL_MS) {

    /*
     * pipe_lim[0] is the filtered ADC output at postion 0
     *
     * ADC_PER_STEP
     */
    adu=analogRead(_pipe_pot_pin);
    tmp=_pipe_filter.filter(MAX_ADC-adu)-_cfg.pipe_lim[0];
    pos.pipe=round(tmp*180.0/(float)_cfg.pipe_lim[1]);

    adu=analogRead(_height_pot_pin);
    tmp=_height_filter.filter(MAX_ADC-adu)-_cfg.height_lim[0];
    pos.height=round(tmp*180.0/(float)_cfg.height_lim[1]);
    _samplet=t;
  }

  if (pos.pipe!=_cfg.pos.pipe) {
    _cfg.pos.pipe = pos.pipe;
    _timeLastPipeMovement=t;
  }

  if (pos.height!=_cfg.pos.height) {
    _cfg.pos.height = pos.height;
    _timeLastHeightMovement=t;
  }
  if (feedback_update_msg>0) {
    Serial.print(F("Update feedback took "));Serial.println(millis()-t);
    Serial.print((uint16_t) MAX_ADC-adu);Serial.print(" ");Serial.print((uint32_t) (tmp>>32));Serial.print("-");Serial.println((uint32_t) (tmp&0xffffffff));
    Serial.print(_cfg.height_lim[0]);Serial.print(",");Serial.println(_cfg.height_lim[1]);
    feedback_update_msg--;
  }

}
