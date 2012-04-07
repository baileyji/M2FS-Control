#include <SdFat.h>

ArduinoOutStream cout(Serial);
void setup() {
  
  Serial.begin(115200);
  
  cout<<"1";
  cout<<"2"<<endl;
  Serial.print("3");
  Serial.println("4");
  Serial.print(0.5);
  cout<<6;
  cout<<7<<endl;
  
}

void loop(){}
