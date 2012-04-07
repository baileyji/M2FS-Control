//#include <iostream.h>
#include <SdFat.h>

ArduinoOutStream cout(Serial);                          // create serial output stream


void serialEvent() {
  char line[81];
  int lineLen=Serial.readBytesUntil('\r',line,80);
  line[lineLen]=0;
  if (parseCommand(line, lineLen))
    cout<<":";
  else
    cout<<"?";
}


/*"Command List"
   
   Simple Commands
   VO Vreg off

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
*/
int parseCommand(const char *line, int lineLen)

 if(lineLen >= 2)
 {
   String command="";
   command+=line[0];
   command+=line[1];
   
   if (command=="VO")
   {
     
    //need to put all drivers in standby and powerdown
    return true;
    
   }
   else if ((command=="MO" || command=="TD" || command =="ST" ||
    command=="DP" || command=="PA" || command =="PR" ||
    command=="SP" || command=="AC") && lineLen > 2)
   {
     
     //Parse the axis
     int axis = line[2];
     if (axis =='*' || (axis>= 'A' && axis <='H')) 
     {
       
       axis= (axis =='*') ? 0:(axis-'A'+1);

       cout<<"Axis: "<<axis<<endl;

       if (axis >=0 && axis <= 8)
       {
  
         if (command=="MO" || command=="TD" || command =="ST")
         {
           //Take appropriate action
           if(command=="MO")
           {
             if(axis==0)
             {
               for(int i=0;i<8;i++)
                 tetris[i].motorOff(param);
             }
             else
             {
               tetris[axis-1].motorOff(param);
             }
           }
           
           if(command=="TD")
           {
             if(axis==0) for(int i=0;i<8;i++) tetris[i].tellPosition();
             else tetris[axis-1].tellPosition();
           }
           
           if(command=="ST")
           {
             if(axis==0)
             {
               for(int i=0;i<8;i++)
                 tetris[i].stop();
             }
             else
             {
               tetris[axis-1].stop();
             }
           }
           
           return true;
         }
         else if (lineLen > 3) 
         {
  
           //Parse the parameter
           if ((line[3] >='0' && line[3] <='9') ||
               (line[3]=='-' && (line[4] >='1' && line[4] <='9')))
           {
             long param=atol(line+3);
             cout<<"Param: "<<param<<endl;
           }
           
           //Take appropriate action
           if(command=="DP")
           {
             if(axis==0)
             {
               for(int i=0;i<8;i++)
                 tetris[i].definePosition(param);
             }
             else
             {
               tetris[axis-1].definePosition(param);
             }
           }
           
           if(command=="PA")
           {
             if(axis==0)
             {
               for(int i=0;i<8;i++)
                 tetris[i].positionAbsoluteMove(param);
             }
             else
             {
               tetris[axis-1].positionAbsoluteMove(param);
             }
           }
           
           if(command=="PR")
           {
             if(axis==0)
             {
               for(int i=0;i<8;i++)
                 tetris[i].positionRelativeMove(param);
             }
             else
             {
               tetris[axis-1].positionRelativeMove(param);
             }
           }
           
           if(command=="SP")
           {
             if(axis==0)
             {
               for(int i=0;i<8;i++)
                 tetris[i].setSpeed(param);
             }
             else
             {
               tetris[axis-1].setSpeed(param);
             }
           }
           
           if(command=="AC")
           {
             if(axis==0)
             {
               for(int i=0;i<8;i++)
                 tetris[i].setAcceleration(param);
             }
             else
             {
               tetris[axis-1].setAcceleration(param);
             }
           }
           
           return true;
           
         }
       }
     }
   }
 }
 return false; 
}

void setup() {
  Serial.begin(57600);
}


void loop() {}
