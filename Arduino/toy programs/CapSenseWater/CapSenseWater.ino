#include <CapSense.h>

/*
 * CapitiveSense Library Demo Sketch
 * Paul Badger 2008
 * Uses a high value resistor e.g. 10M between send pin and receive pin
 * Resistor effects sensitivity, experiment with values, 50K - 50M. Larger resistor values yield larger sensor values.
 * Receive pin is the sensor pin - try different amounts of foil/metal on this pin
 */


CapSense   cs_4_6 = CapSense(4,6);        // 10M resistor between pins 4 & 6, pin 6 is sensor pin, add a wire and or foil

void setup()                    
{
    pinMode(13,OUTPUT);
   Serial.begin(9600);
}

void loop()                    
{
    long start = millis();
    long total2 =  cs_4_6.capSense(30);
    if (total2 > 10000) digitalWrite(13,HIGH);
    else digitalWrite(13,LOW);
    Serial.print(millis() - start);        // check on performance in milliseconds
    Serial.print('\t');
    Serial.println(total2);                  // print sensor output 2

    delay(10);                             // arbitrary delay to limit data to serial port 
}
