String commands[3]={"PC","VO","VE"};//,"TS","MO","TD"}
bool (*cmdFuncArray[3])() = {
  printCommands,
  powereDownTetrisShield,
  powereUpTetrisShield
};

void setup() {
  Serial.begin(115200); 

  String c;
  char ndx;
  c="VE";
  ndx=getCallbackNdxForCommand(c);
  Serial.println(ndx);
  if (ndx !=-1 ) cmdFuncArray[ndx]();
  
  c="PC";
  ndx=getCallbackNdxForCommand(c);
  Serial.println(ndx);
  if (ndx !=-1 ) cmdFuncArray[ndx]();
  
  c="BL";
  ndx=getCallbackNdxForCommand(c);
  Serial.println(ndx);
  if (ndx !=-1 ) cmdFuncArray[ndx]();
  
  c="VO";
  ndx=getCallbackNdxForCommand(c);
  Serial.println(ndx);
  if (ndx !=-1 ) cmdFuncArray[ndx]();
}

void loop() {}

char getCallbackNdxForCommand(const String c) {
  for (char i=0;i<3;i++) {
    if (commands[i]==c) return i;    
  }
  return -1;
}

bool printCommands() {
  Serial.println("printCommands");
}
bool powereDownTetrisShield() {
  Serial.println("powereDownTetrisShield");
}
bool powereUpTetrisShield() {
  Serial.println("powereUpTetrisShield");
}
