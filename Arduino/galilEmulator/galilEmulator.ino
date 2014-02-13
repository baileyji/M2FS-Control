void setup() {
  Serial.begin(115200);
}

void loop() {
  char byteIn;
  byteIn=Serial.read();
  if (byteIn==';' || byteIn=='\r')
    Serial.write(':');
  
}
