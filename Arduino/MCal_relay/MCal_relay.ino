int sensorPin = A0;    // select the input pin for the potentiometer
int ledPin = 13;      // select the pin for the LED
int sensorValue = 0;  // variable to store the value coming from the sensor


#define RELAY_PINS 0xC0
#define ANALOG_PIN A5
#define MIN_ON_V 205 //1V/5V * 1024
#define MAX_ON_V 410 //2V/5V * 1024  

#define ADC_READ_WAIT_MS 1

bool relay_is_on;

void setup() {
  // declare the relay pins as output
  DDRD |= RELAY_PINS;
  //Serial.begin(115200);
  //relay off
  turn_off_relay();
}

uint8_t turnon=0;
void loop() {
  
  
  uint16_t inputV;
  
  // read the value from the sensor
  inputV = analogRead(ANALOG_PIN);
  
  //Bitshift to eliminate noise
  if (MIN_ON_V < inputV && inputV < MAX_ON_V) {
      turnon=turnon<<1 | 1;
  } else {
      turnon=turnon<<1;
  }
  
  //Act on the state
  if (turnon==255 && !relay_is_on) turn_on_relay();
  else if (turnon==0 && relay_is_on) turn_off_relay();

  //Wait for a bit until the next sample  
  delay(ADC_READ_WAIT_MS);
}

void turn_on_relay() {
  
  PORTD |= RELAY_PINS;
  relay_is_on=true;
  //Serial.println("Relay on");
}

void turn_off_relay() {
  
  PORTD &= ~RELAY_PINS;
  relay_is_on=false;
  //Serial.println("Relay off");
}
  
