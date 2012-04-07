#define TETRIS_MOTORS_POWER_ENABLE 12
#define POWERDOWN_DELAY_US  1000

#define R_SIDE_POLL_PIN 23
#define R_SIDE_POLL_DRIVER_PIN 24

#define TETRIS_1_RESET       A12
#define TETRIS_1_STANDBY     A13
#define TETRIS_1_DIR         A10
#define TETRIS_1_CK          A11
//#define TETRIS_1_ENABLE      
#define TETRIS_1_PHASE_HOME  A14  //input, requires pullup enabled

#define TETRIS_2_RESET       A7
#define TETRIS_2_STANDBY     A6
#define TETRIS_2_DIR         A8
#define TETRIS_2_CK          A9
//#define TETRIS_2_ENABLE      19
#define TETRIS_2_PHASE_HOME  A5  //input, requires pullup enabled

#define TETRIS_3_RESET       41
#define TETRIS_3_STANDBY     42
#define TETRIS_3_DIR         39
#define TETRIS_3_CK          40
//#define TETRIS_3_ENABLE      19
#define TETRIS_3_PHASE_HOME  43  //input, requires pullup enabled

#define TETRIS_4_RESET       A2
#define TETRIS_4_STANDBY     A3
#define TETRIS_4_DIR         A0
#define TETRIS_4_CK          A1
//#define TETRIS_4_ENABLE      19
#define TETRIS_4_PHASE_HOME  A4  //input, requires pullup enabled

#define TETRIS_5_RESET       31
#define TETRIS_5_STANDBY     32
#define TETRIS_5_DIR         29
#define TETRIS_5_CK          30
//#define TETRIS_5_ENABLE      19
#define TETRIS_5_PHASE_HOME  33  //input, requires pullup enabled

#define TETRIS_6_RESET       9
#define TETRIS_6_STANDBY     8
#define TETRIS_6_DIR         11
#define TETRIS_6_CK          10
//#define TETRIS_6_ENABLE      19
#define TETRIS_6_PHASE_HOME  7  //input, requires pullup enabled

#define TETRIS_7_RESET       19
#define TETRIS_7_STANDBY     20
#define TETRIS_7_DIR         17
#define TETRIS_7_CK          18
//#define TETRIS_7_ENABLE      19
#define TETRIS_7_PHASE_HOME  21  //input, requires pullup enabled

#define TETRIS_8_RESET       6
#define TETRIS_8_STANDBY     5
#define TETRIS_8_DIR         3
#define TETRIS_8_CK          2
//#define TETRIS_8_ENABLE      19
#define TETRIS_8_PHASE_HOME  4  //input, requires pullup enabled

#define DIRECTION_CW  LOW
#define DIRECTION_CCW HIGH

#include <SdFat.h>
#include <Tetris.h>
#include <AccelStepper.h>


Tetris tetris[8];
ArduinoOutStream cout(Serial);

void serialEvent() {
  //uint32_t t=micros();
  char line[81];
  int lineLen=Serial.readBytesUntil('\r',line,80);
  line[lineLen]=0;
  //uint32_t t2=micros();
  boolean commandGood=parseCommand(line, lineLen);
  //uint32_t t1=micros();
  //cout<<"#Event took "<<t1-t<<"us. Parsing took "<<t1-t2<<" us.\n";
  if(commandGood)
    cout<<":";
  else
    cout<<"?";
}

void setup() {


  //Set up R vs. B side detection
  pinMode(R_SIDE_POLL_PIN,INPUT);
  digitalWrite(R_SIDE_POLL_PIN, LOW);
  pinMode(R_SIDE_POLL_DRIVER_PIN,OUTPUT);
  digitalWrite(R_SIDE_POLL_DRIVER_PIN, HIGH);
  
  //Vm power control pin
  digitalWrite(TETRIS_MOTORS_POWER_ENABLE, LOW);
  pinMode(TETRIS_MOTORS_POWER_ENABLE, OUTPUT);
  
  //Tetris Drivers
  tetris[0]=Tetris(TETRIS_1_RESET, TETRIS_1_STANDBY, TETRIS_1_DIR, 
    TETRIS_1_CK, TETRIS_1_PHASE_HOME);
  tetris[1]=Tetris(TETRIS_2_RESET, TETRIS_2_STANDBY, TETRIS_2_DIR, 
    TETRIS_2_CK, TETRIS_2_PHASE_HOME);
  tetris[2]=Tetris(TETRIS_3_RESET, TETRIS_3_STANDBY, TETRIS_3_DIR, 
    TETRIS_3_CK, TETRIS_3_PHASE_HOME);
  tetris[3]=Tetris(TETRIS_4_RESET, TETRIS_4_STANDBY, TETRIS_4_DIR, 
    TETRIS_4_CK, TETRIS_4_PHASE_HOME);
  tetris[4]=Tetris(TETRIS_5_RESET, TETRIS_5_STANDBY, TETRIS_5_DIR, 
    TETRIS_5_CK, TETRIS_5_PHASE_HOME);
  tetris[5]=Tetris(TETRIS_6_RESET, TETRIS_6_STANDBY, TETRIS_6_DIR, 
    TETRIS_6_CK, TETRIS_6_PHASE_HOME);
  tetris[6]=Tetris(TETRIS_7_RESET, TETRIS_7_STANDBY, TETRIS_7_DIR, 
    TETRIS_7_CK, TETRIS_7_PHASE_HOME);
  tetris[7]=Tetris(TETRIS_8_RESET, TETRIS_8_STANDBY, TETRIS_8_DIR, 
    TETRIS_8_CK, TETRIS_8_PHASE_HOME);
  
  Serial.begin(115200);
  
  printCommands();
}


void loop() {

  uint32_t t=micros();
  for(int i=0;i<8;i++) tetris[i].run();
  uint32_t t1=micros();
  
  //if(t%5 ==0) cout<<"Run took "<<t1-t<<" us.\n";
}



//Toggle the value of a pin
inline void togglePin(unsigned char pin) {
  digitalWrite(pin, !digitalRead(pin));
}

/*"Command List"
   
   Simple Commands
   VO Vreg off
   VE Vreg on
   TS Tel Status "side vreg state" "powered motors" "moving motors"

   Commands with mask
   TDx tell position
   MOx motor off
   STx stop motion

   Commands with mask & parameters
   DPx define position
   PAx position absolute move
   PRx position relative move
   SPx set speed
   ACx set acceleration
   SLx move to slit
   SDx define current position as slit
   BLx define backlash amount 
*/
int parseCommand(const char *line, int lineLen) {

 if(lineLen >= 2)
 {
   String command="";
   command+=line[0];
   command+=line[1];
   
   if (command=="PC")
   {
     printCommands();
     return true;
   }
   else if (command=="VO")
   {
     
    //Power down the tetris shield
    powereDownTetrisShield();
    return true;
    
   }
   else if (command =="VE")
   {
     powereUpTetrisShield();
     return true;
   }
   else if (command=="TS")
   {
     uint16_t statusBytes[3]={0,0,0};
     for (int i=0;i<8;i++) statusBytes[0]|=(tetris[i].moving()<<i);
     for (int i=0;i<8;i++) statusBytes[1]|=(tetris[i].motorIsOn()<<i);
     statusBytes[3]=(tetrisShieldIsR()<<1)|tetrisShieldIsPowered();
     cout<<statusBytes[3]<<" "<<statusBytes[2]<<" "<<statusBytes[0]<<endl;     
   }
   else if ((command=="MO" || command=="TD" || command =="ST" ||
    command=="DP" || command=="PA" || command =="PR" ||
    command=="SP" || command=="AC" || command=="SD" || 
    command=="SL" || command=="BL" || command=="SH") && lineLen > 2)
   {
     
     //Parse the axis
     int axis = line[2];
     
     if (axis =='*' || (axis>= 'A' && axis <='H')) 
     {
       
       axis= (axis =='*') ? 0:(axis-'A'+1);

       //cout<<"Axis: "<<axis<<endl;

       if (axis >=0 && axis <= 8)
       {
  
         if (command=="MO" || command=="TD" || command =="ST" ||
             command=="SH" )
         {

           if(command=="MO")
           {
             if(axis==0) for(int i=0;i<8;i++) tetris[i].motorOff();
             else tetris[axis-1].motorOff();
           }
           
           if(command=="TD")
           {
             if(axis==0)
               for(int i=0;i<8;i++) 
               {
                 tetris[i].tellPosition(); 
                 if(i<7)cout<<", ";
               }
             else tetris[axis-1].tellPosition();
             cout<<endl;
           }
           
           if(command=="ST")
           {
             if(axis==0) for(int i=0;i<8;i++) tetris[i].stop();
             else tetris[axis-1].stop();
           }
           
           if(command=="SH")
           {
             if(axis==0) for(int i=0;i<8;i++) tetris[i].motorOn();
             else tetris[axis-1].motorOn();
           }
           
           return true;
           
         }
         else if ( (lineLen > 3) && ((line[3] >='0' && line[3] <='9') ||
                  (line[3]=='-' && (line[4] >='1' && line[4] <='9')))) 
         {
  
           //Parse the parameter
           long param=atol(line+3);
           
           //cout<<"Param: "<<param<<endl;

           if(command=="BL")
           {
             if (param<0) return false;
             if(axis==0) for(int i=0;i<8;i++) tetris[i].setBacklash(param);
             else tetris[axis-1].setBacklash(param);
           }
           
           if(command=="SL")
           {
             if (param<0 || param>6) return false;
             if(axis==0) for(int i=0;i<8;i++) tetris[i].dumbMoveToSlit(param);
             else tetris[axis-1].dumbMoveToSlit(param);
           }

           if(command=="SD")
           {
             if (param<0 || param>6) return false;
             if(axis==0) for(int i=0;i<8;i++) tetris[i].defineSlitPosition(param);
             else tetris[axis-1].defineSlitPosition(param);
           }

           if(command=="DP")
           {
             if(axis==0) for(int i=0;i<8;i++) tetris[i].definePosition(param);
             else tetris[axis-1].definePosition(param);
           }
           
           if(command=="PA")
           {
             if(axis==0) for(int i=0;i<8;i++) tetris[i].positionAbsoluteMove(param);
             else tetris[axis-1].positionAbsoluteMove(param);
           }
           
           if(command=="PR")
           {
             if(axis==0) for(int i=0;i<8;i++) tetris[i].positionRelativeMove(param);
             else tetris[axis-1].positionRelativeMove(param);
           }
           
           if(command=="SP")
           {
             if(axis==0) for(int i=0;i<8;i++) tetris[i].setSpeed(param);
             else tetris[axis-1].setSpeed(param);
           }
           
           if(command=="AC")
           {
             if(axis==0) for(int i=0;i<8;i++) tetris[i].setAcceleration(param);
             else tetris[axis-1].setAcceleration(param);
           }
           
           return true;
           
         }
       }
     }
   }
 }
 return false; 
}


void powereDownTetrisShield() {
  for(int i=0;i<8;i++) tetris[i].motorOff();
  delayMicroseconds(POWERDOWN_DELAY_US);
  digitalWrite(TETRIS_MOTORS_POWER_ENABLE,LOW);
}

void powereUpTetrisShield() {
  for(int i=0;i<8;i++) tetris[i].motorOff();
  delayMicroseconds(POWERDOWN_DELAY_US);
  digitalWrite(TETRIS_MOTORS_POWER_ENABLE,HIGH);
}

bool tetrisShieldIsPowered() {
  return digitalRead(TETRIS_MOTORS_POWER_ENABLE);
}

bool tetrisShieldIsR(){
  return digitalRead(R_SIDE_POLL_PIN);
}

//Print the commands and wait for a response
void establishContact() {
  printCommands(); 
  while (Serial.available() <= 0);
}

/*"Command List"
   
   Simple Commands
   PC Print Commands
   VO Vreg off
   VE Vreg on
   TS Tel Status "side vreg state" "powered motors" "moving motors"

   Commands with mask
   TDx tell position
   MOx motor off
   STx stop motion

   Commands with mask & parameters
   DPx define position
   PAx position absolute move
   PRx position relative move
   SPx set speed
   ACx set acceleration
   SLx move to slit
   SDx define current position as slit
   BLx define backlash amount 
*/

void printCommands() {
  cout<<"#PC   Print Commands - Print the list of commands"<<endl;
  cout<<"#VO   Voltage Off - Power down the tetris motors"<<endl;
  cout<<"#VE   Voltage Enable - Power up the motor supply"<<endl;
  cout<<"#TS   Tell Status - Tell the status bytes"<<endl;
  
  cout<<"#TDx  Tell Position - Tell position of tetris x in microsteps"<<endl;
  cout<<"#SHx  Servo Here - Turn on tetris x"<<endl;
  cout<<"#MOx  Motor Off - Turn off motor in tetris x"<<endl;
  cout<<"#STx  Stop - Stop motion of tetris x"<<endl;
  
  cout<<"#DPx# Define Position - Define the current position of tetris x to be #"<<endl;
  cout<<"#PAx# Position Absolute - Command tetris x to move to position #"<<endl;
  cout<<"#PRx# Position Relative - Command tetris x to move #"<<endl;
  cout<<"#SPx# Speed - Set the movement speed of tetris x to # (usteps/s)"<<endl;
  cout<<"#ACx# Acceleration - Set the acceleration rate of tetris x to # (usteps/s^2)"<<endl;
  cout<<"#SLx# Slit - Command tetris x to go to the position of slit #"<<endl;
  cout<<"#SDx# Slit Define - Set slit # for tetris x to be at the current position"<<endl;
  cout<<"#BLx# Backlash - Set the amount of backlash of tetris x to # (usteps)"<<endl;

}
