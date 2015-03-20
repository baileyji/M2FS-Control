//check button over and over if button stays down for 5 seconds
//send "shutdown" out over serial
//turn on light
//wait for 30s
//turn off light


//Python client
// listens for 'shutdown', on receipt executes "shutdown now"


const int LED_PIN=13; 
const int LED_OFF=LOW;
const int LED_ON =HIGH;
const int PRESSED=LOW;

const int BUTTON_PIN=2;

const int SHUTDOWN_TIME=150000; //ms

const int SHUTDOWN_PRESS_TIME=10000; //ms

unsigned long unpressed_time;

void setup() {
  pinMode(BUTTON_PIN, INPUT);
  digitalWrite(BUTTON_PIN, HIGH);
  
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LED_OFF);
  
  Serial.begin(115200);
  unpressed_time=millis();
}

void loop() {
  
  unsigned long time=millis();
  
  if (digitalRead(BUTTON_PIN) != PRESSED) unpressed_time=time;
  
  //Deal with rollover
  if (time < unpressed_time)  unpressed_time=0;
  
  //If it has been pressed for long enough send shutdown
  if (time-unpressed_time > SHUTDOWN_PRESS_TIME) {
    Serial.println("SHUTDOWN");
    digitalWrite(LED_PIN, LED_ON);
    delay(SHUTDOWN_TIME);
    digitalWrite(LED_PIN, LED_OFF);
    unpressed_time=millis();
  } 
 
}
