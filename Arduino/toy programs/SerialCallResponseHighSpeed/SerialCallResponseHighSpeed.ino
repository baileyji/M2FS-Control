int inByte = 0;         // incoming serial byte
char i=0;
void setup()
{
  Serial.begin(460800);
//  Serial.println("Hello World!");
}

void loop()
{
  // if we get a valid byte, read analog ins:
  if (Serial.available() > 0) {
    // get incoming byte:
    inByte = Serial.read();
  } 
  delay(1500);
//  if (inByte!=0)
//    Serial.println(inByte);
  Serial.print("1234567890");
  i=(i+1)%43;
}

