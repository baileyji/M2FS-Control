#define  HS_PIN  2
#define  VS_PIN  3

void setup(){
  
  pinMode(HS_PIN,INPUT);
  pinMode(VS_PIN,INPUT);
  
  #ifdef USE_PULLUPS
  digitalWrite(HS_PIN,HIGH);
  digitalWrite(VS_PIN,HIGH);
  #endif

  attachInterrupt(0,hs_interrupt,RISING);
  attachInterrupt(1,vs_interrupt,RISING);

  Serial.begin(500000);
  
}

void hs_interrupt(){
  Serial.write('h'); 
}

void vs_interrupt(){
  Serial.write('v'); 
}


void loop() {
  
}
