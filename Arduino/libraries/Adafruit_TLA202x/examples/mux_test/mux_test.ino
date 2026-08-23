// Demo of the multiplexer and differential reads with expected negative voltages
// https://adafruit.com/product/4780
#include <Wire.h>
#include <Adafruit_TLA202x.h>

void printMux(Adafruit_TLA202x *tla){
  Serial.print("Multiplexer set to: ");
  switch (tla->getMux()) {
    case TLA202x_MUX_AIN0_AIN1:
      Serial.println("AINp = AIN 0, AINn = AIN 1"); break;
    case TLA202x_MUX_AIN0_AIN3:
      Serial.println("AINp = AIN 0, AINn = AIN 3"); break;
    case TLA202x_MUX_AIN1_AIN3:
      Serial.println("AINp = AIN 1, AINn = AIN 3"); break;
    case TLA202x_MUX_AIN2_AIN3:
      Serial.println("AINp = AIN 2, AINn = AIN 3"); break;
    case TLA202x_MUX_AIN0_GND:
      Serial.println("AINp = AIN 0, AINn = GND"); break;
    case TLA202x_MUX_AIN1_GND:
      Serial.println("AINp = AIN 1, AINn = GND"); break;
    case TLA202x_MUX_AIN2_GND:
      Serial.println("AINp = AIN 2, AINn = GND"); break;
    case TLA202x_MUX_AIN3_GND:
      Serial.println("AINp = AIN 3, AINn = GND"); break;
  }
}


Adafruit_TLA202x  tla;
float expected_reads[4];
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

  printMux(&tla);

  // update this to match the voltages to GND for each input
  expected_reads[0] = 3.7;
  expected_reads[1] = 4.85;
  expected_reads[2] = 0;
  expected_reads[3] = 5.0;


}

void loop() {
  tla.setMux(TLA202x_MUX_AIN0_AIN1);
  Serial.print("Reading with "); printMux(&tla);
  Serial.print(tla.readVoltage()); Serial.println(" V");
  Serial.print("Expected: "); Serial.print(expected_reads[0]-expected_reads[1]); // 3.7-4.85=-1.15
  Serial.println(" V");

  tla.setMux(TLA202x_MUX_AIN0_AIN3);
  Serial.print("Reading with "); printMux(&tla); // 3.7 - 5 = -1.3
  Serial.print(tla.readVoltage()); Serial.println(" V");
  Serial.print("Expected: "); Serial.print(expected_reads[0]-expected_reads[3]);
  Serial.println(" V");

  tla.setMux(TLA202x_MUX_AIN1_AIN3);
  Serial.print("Reading with "); printMux(&tla); // 4.85 - 5 = 0.15
  Serial.print(tla.readVoltage()); Serial.println(" V");
  Serial.print("Expected: "); Serial.print(expected_reads[1]-expected_reads[3]);
  Serial.println(" V");

  tla.setMux(TLA202x_MUX_AIN2_AIN3);
  Serial.print("Reading with "); printMux(&tla); // 0-5 = -5.0
  Serial.print(tla.readVoltage()); Serial.println(" V");
  Serial.print("Expected: "); Serial.print(expected_reads[2]-expected_reads[3]);
  Serial.println(" V");

  tla.setMux(TLA202x_MUX_AIN0_AIN1);
  Serial.print(""); Serial.println();
  Serial.println("");
  delay(1000);
}
