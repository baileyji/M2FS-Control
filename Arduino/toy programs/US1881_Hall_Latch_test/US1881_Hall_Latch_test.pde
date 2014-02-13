/*
Melexis US1881
Hall Latch Test program
*/

#include <SdFat.h>

ArduinoOutStream cout(Serial);  // Serial print stream
boolean sensorValue, oldValue;


void setup() {
  Serial.begin(115200);
  pinMode(A0, INPUT);
  digitalWrite(A0, HIGH);
  pinMode(13, OUTPUT);
  oldValue=sensorValue=digitalRead(A0);
  cout<<pstr("Sensor value: ")<<(sensorValue?"High":"Low")<<endl;
  if (sensorValue) 
    digitalWrite(13, HIGH);
  else
    digitalWrite(13, LOW);
}

void loop() {
  sensorValue=digitalRead(A0);
  if (sensorValue!=oldValue) {
    cout<<pstr("Sensor value: ")<<(sensorValue?"High":"Low")<<endl;
    if (sensorValue) 
      digitalWrite(13, HIGH);
    else
      digitalWrite(13, LOW);
    oldValue=sensorValue;
  }
}



