// Basic demo for basic ADC readings from a single channel of the TLA2024
// Written to work with the Adafruit TLA2024 Breakout:
// https://adafruit.com/product/4780
#include <Wire.h>
#include <Adafruit_TLA202x.h>

Adafruit_TLA202x  tla;
void setup(void) {
  Serial.begin(115200);
  while (!Serial) delay(10);     // will pause Zero, Leonardo, etc until serial console opens

  Serial.println("Adafruit TLA202x test!");

  // Try to initialize!
  if (!tla.begin()) {
    Serial.println("Failed to find TLA202x chip");
    while (1) { delay(10); }
  }
  Serial.println("TLA202x Found!");

//  tla.setDataRate(TLA202x_RATE_12_5_HZ);
  Serial.print("Data rate set to: ");
  switch (tla.getDataRate()) {

    case TLA202x_RATE_128_SPS: Serial.println("128 SPS");break;
    case TLA202x_RATE_250_SPS: Serial.println("250 SPS");break;
    case TLA202x_RATE_490_SPS: Serial.println("490 SPS");break;
    case TLA202x_RATE_920_SPS: Serial.println("920 SPS");break;
    case TLA202x_RATE_1600_SPS: Serial.println("1600 SPS");break;
    case TLA202x_RATE_2400_SPS: Serial.println("2400 SPS");break;
    case TLA202x_RATE_3300_SPS: Serial.println("3300 SPS");break;

  }
}

void loop() {
  Serial.println("Read all channels in one-shot mode:");
  for (uint8_t channel_num= 0; channel_num < 4; channel_num++){
    Serial.print("Channel : ");
    Serial.print(channel_num);
    Serial.print(": ");
    Serial.print(
      tla.readOnce((tla202x_channel_t)channel_num)
      );

    Serial.println(" volts");
    Serial.println("");
  }

  Serial.println("Read each channel in continuous mode:");
  tla.setMode(TLA202x_MODE_CONTINUOUS);

  for (uint8_t channel_num= 0; channel_num < 4; channel_num++){
    tla.setChannel((tla202x_channel_t)channel_num);
    Serial.print("Channel : ");
    Serial.print(channel_num);
    Serial.print(": ");
    Serial.print(tla.readVoltage());
    Serial.println(" volts ");
    Serial.println("");
  }

  Serial.println("");
  Serial.println("");
  delay(1000);
}
