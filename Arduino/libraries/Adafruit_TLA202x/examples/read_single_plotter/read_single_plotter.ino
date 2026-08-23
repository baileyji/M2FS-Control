// This demo uses the Serial plotter to show the effect of changing the sample rate
// and measurement range
// Written to work with the Adafruit TLA2024 Breakout:
// https://adafruit.com/product/4780
#include <Wire.h>
#include <Adafruit_TLA202x.h>

#define ANALOG_OUT 5
Adafruit_TLA202x  tla;
void setup(void) {
  Serial.begin(115200);
  while (!Serial) delay(10);     // will pause Zero, Leonardo, etc until serial console opens


  // Try to initialize!
  if (!tla.begin()) {
    Serial.println("Failed to find TLA202x chip");
    while (1) { delay(10); }
  }
  // TLA202x_RATE_128_SPS
  // TLA202x_RATE_250_SPS
  // TLA202x_RATE_490_SPS
  // TLA202x_RATE_920_SPS
  // TLA202x_RATE_1600_SPS
  // TLA202x_RATE_2400_SPS
  // TLA202x_RATE_3300_SPS
  tla.setDataRate(TLA202x_RATE_128_SPS);
  Serial.println("Voltage:");

    // TLA202x_RANGE_6_144_V
    // TLA202x_RANGE_4_096_V
    // TLA202x_RANGE_2_048_V
    // TLA202x_RANGE_1_024_V
    // TLA202x_RANGE_0_512_V
    // TLA202x_RANGE_0_256_V


    // tla.setRange(TLA202x_RANGE_6_144_V);

}

void loop() {
  tla.setRange(TLA202x_RANGE_2_048_V);

  tla.setDataRate(TLA202x_RATE_128_SPS);
  for(uint16_t i=0; i<255; i++){
    analogWrite(ANALOG_OUT, i);
    Serial.println(tla.readVoltage(), 5);
  }
  tla.setDataRate(TLA202x_RATE_3300_SPS);
  for(uint16_t i=0; i<255; i++){
    analogWrite(ANALOG_OUT, i);
    Serial.println(tla.readVoltage(), 5);
  }

  delay(1000);
  tla.setRange(TLA202x_RANGE_6_144_V);

  tla.setDataRate(TLA202x_RATE_128_SPS);
  for(uint16_t i=0; i<255; i++){
    analogWrite(ANALOG_OUT, i);
    Serial.println(tla.readVoltage(), 5);
  }
  tla.setDataRate(TLA202x_RATE_3300_SPS);
  for(uint16_t i=0; i<255; i++){
    analogWrite(ANALOG_OUT, i);
    Serial.println(tla.readVoltage(), 5);
  }

  delay(1000);

}