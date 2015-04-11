//check button over and over if button stays down for 5 seconds
//send "shutdown" out over serial
//turn on light
//wait for 30s
//turn off light


//Python client
// listens for 'shutdown', on receipt executes "shutdown now"


const int LED_PIN=A3;
const int BUTTON_PIN=A2;
const int SINK_PIN=A5;
const int RELAY_PIN=A4;


const int LED_OFF=LOW;
const int LED_ON =HIGH;
const int PRESSED=LOW;



const int SHUTDOWN_TIME=150000; //ms

const int SHUTDOWN_PRESS_TIME=10000; //ms

const int UPS_RELAY_TIME=2500; //ms

unsigned long unpressed_time;

void setup() {
  pinMode(BUTTON_PIN, INPUT);
  digitalWrite(BUTTON_PIN, HIGH);

  digitalWrite(LED_PIN, LED_OFF);
  pinMode(LED_PIN, OUTPUT);

  digitalWrite(RELAY_PIN, LOW);
  pinMode(RELAY_PIN, OUTPUT);

  digitalWrite(SINK_PIN, LOW);
  pinMode(SINK_PIN, OUTPUT);

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
    digitalWrite(RELAY_PIN, HIGH);
    delay(UPS_RELAY_TIME);
    digitalWrite(LED_PIN, LED_OFF);
    digitalWrite(RELAY_PIN, LOW);
    unpressed_time=millis();
  } 
 
}
