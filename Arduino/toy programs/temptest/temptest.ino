#include <OneWire.h>
#include <DallasTemperature.h>

// Data wire is plugged into port 2 on the Arduino
#define ONE_WIRE_BUS 13

// Setup a oneWire instance to communicate with any OneWire devices (not just Maxim/Dallas temperature ICs)
OneWire oneWire(ONE_WIRE_BUS);

// Pass our oneWire reference to Dallas Temperature. 
DallasTemperature sensors(&oneWire);

void setup(void)
{
  pinMode(ONE_WIRE_BUS,INPUT);
  digitalWrite(ONE_WIRE_BUS,LOW);
  // start serial port
  Serial.begin(115200);
  Serial.println("Dallas Temperature Control Library - Async Demo");
  Serial.println("\nDemo shows the difference in length of the call\n\n");

  // Start up the library
  sensors.begin();
  sensors.setResolution(12);
}

void loop(void)
{ 
  // Request temperature conversion (traditional)
  Serial.println("Before blocking requestForConversion");
  unsigned long start = millis();    
  sensors.setWaitForConversion(true);
  delay(10);
  sensors.requestTemperatures();

  unsigned long stop = millis();
  Serial.println("After blocking requestForConversion");
  Serial.print("Time used: ");
  Serial.println(stop - start);
  
  // get temperature
  Serial.print("Temperature: ");
  Serial.println(sensors.getTempCByIndex(0));  
  Serial.println("\n");
  
  // Request temperature conversion - non-blocking / async
  Serial.println("Before NON-blocking/async requestForConversion");
  sensors.setWaitForConversion(false);  // makes it async
  delay(10);
  start = millis();       
  sensors.requestTemperatures();
  stop = millis();
  Serial.println("After NON-blocking/async requestForConversion");
  Serial.print("Time used: ");
  Serial.println(stop - start); 
  
  
  // 9 bit resolution by default 
  // Note the programmer is responsible for the right delay
  // we could do something usefull here instead of the delay
  int resolution = 12;
  delay(750);
  
  // get temperature
  Serial.print("Temperature: ");
  Serial.println(sensors.getTempCByIndex(0));  
  Serial.println("\n\n\n\n");  
  
  delay(5000);
}
