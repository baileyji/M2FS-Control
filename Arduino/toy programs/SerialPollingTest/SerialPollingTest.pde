#include <Streaming.h>
void setup() {
  Serial.begin(115200);
}
/*
void loop() {
  while(!Serial.available());
  Serial<<"Get ready..."<<endl;
  delay(100);
  Serial.flush();
  uint32_t t2,t1,t0=micros();
  Serial.print("112131999240032");
  t1=micros();
  while(!Serial.available());
  t2=micros();
  Serial<<"Time to poll: "<<t1-t0<<endl<<"Time until response: "<<t2-t1<<endl;
  Serial<<"69.4 us for transmission"<<endl;
  Serial.flush();
}
*/

void loop() {
  int count=0;
  while(!Serial.available());
  if (count==0) count=Serial.available();
  Serial<<Serial.available()-count<<endl;
}

