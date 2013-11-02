
enum State{
    LOG_TIMED,       
    POWER_SAVE,
    IDLE,        
    ONLINE,
    DEBUG_MODE
};

void reportIdentity(){
  Serial.print("M2FS_DATALOGGER_PROTO");
}


typedef struct MEASUREMENT{
    DateTime time;
    unsigned long mils;
    int value;
} Measurement;



