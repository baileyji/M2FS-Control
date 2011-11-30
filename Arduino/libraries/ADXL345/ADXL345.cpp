#include "ADXL345.h"


ADXL345Class::ADXL345Class(void) {
  _bits2gees=0.00390625; //gees per LSB
  _dataFormat= ADXL_INT_ACTIVELOW | ADXL_16G_RANGE | ADXL_FULL_RES;
}

boolean ADXL345Class::init(uint8_t csPin) {
  
  _cs_pin=csPin;
  
  _setupSPI();
  
  // Place the part in standby
  writeRegister(ADXL_POWER_CTL, 0);  

  // Set measurement range (±16g),
  //  and interrupts to active low.
  writeRegister(ADXL_DATA_FORMAT, _dataFormat);  //0x23
  
  // Use the FIFO in stream mode
  writeRegister(ADXL_FIFO_CTL,ADXL_FIFO_STREAM | 0x1F); 
  
  
  // Set the measurement rate
  writeRegister(ADXL_BW_RATE, ADXL_LP_RATE_25);
  
  // Configure interrupts
  writeRegister(ADXL_INT_ENABLE, 0); //Disable interrupts
  
  uint8_t interrupts= ADXL_INT_FREEFALL | ADXL_INT_WATERMARK |
					  ADXL_INT_ACTIVITY  | ADXL_INT_INACTIVITY;
  
  //Send the Activity and Freefall Interrupts to INT1 pin, rest to INT2 pin
  writeRegister(ADXL_INT_MAP, ~interrupts );
  
  // Configure freefall interrupt
  writeRegister(ADXL_THRESH_FF, 0x08);	// Threshold to around 500 mg.
  writeRegister(ADXL_TIME_FF, 0x46);    //Duration to 350ms
  
  //Set activity and inactivity detection mode to AC, all axes included
  writeRegister(ADXL_ACT_INACT_CTL, 0b11111111);
  writeRegister(ADXL_THRESH_ACT, 0x06); //activity threshold, .25g~0x04, About 1.5g as 255*1.5/16~0x18
  writeRegister(ADXL_THRESH_INACT, 0x05); //*62.5mg inactivity threshold
  writeRegister(ADXL_TIME_INACT, 5);	  // inactivity duration (seconds)
  //Set the activity threshold that must be reached


  // Enable interrupts
  writeRegister(ADXL_INT_ENABLE, interrupts);

  // Clear the interrupts by reading
  getInterruptSource(); 

  // Link, Measurement mode, autosleep, 8Hz rate
  writeRegister(ADXL_POWER_CTL, 0b00101000);

  return true;
}


void ADXL345Class::selfTest(int16_t * accel) {
  writeRegister(ADXL_DATA_FORMAT,0b10000000 | _dataFormat);
  delay(500);
  getRawAccelerations(accel);
  writeRegister(ADXL_DATA_FORMAT,_dataFormat);
}

char ADXL345Class::getInterruptSource() {
  char interrupt;
  ADXL345.readRegister(ADXL_INT_SOURCE, 1, &interrupt);
  return interrupt;
}


void ADXL345Class::_setupSPI() {

  //Set up the Chip Select pin to be an output from the Arduino.
  //N.B. Caller's responsibility to make sure that the default chip
  //   select pin (10) is set to output, even if it is unused.
  pinMode(_cs_pin, OUTPUT);
  
  //Make sure the ADXL isn't selected while configuring.
  digitalWrite(_cs_pin, HIGH);

  //Initiate an SPI communication instance and 
  // configure the SPI connection for the ADXL345.
  SPI.begin();
  SPI.setDataMode(SPI_MODE3);
  SPI.setClockDivider(SPI_CLOCK_DIV2);

}

//This function will write a value to a register on the ADXL345.
//Parameters:
//  char registerAddress - The register to write a value to
//  char value - The value to be written to the specified register.
void ADXL345Class::writeRegister(char registerAddress, char value){
  _setupSPI();
  //Set Chip Select pin low to signal the beginning of an SPI packet.
  digitalWrite(_cs_pin, LOW);
  //Transfer the register address over SPI.
  SPI.transfer(registerAddress);
  //Transfer the desired register value over SPI.
  SPI.transfer(value);
  //Set the Chip Select pin high to signal the end of an SPI packet.
  digitalWrite(_cs_pin, HIGH);
}

//This function will read a certain number of registers starting from a specified address and store their values in a buffer.
//Parameters:
//  char registerAddress - The register addresse to start the read sequence from.
//  int numBytes - The number of registers that should be read.
//  char * values - A pointer to a buffer where the results of the operation should be stored.
void ADXL345Class::readRegister(char registerAddress, int numBytes, char * values){
  //Since we're performing a read operation, the most significant bit of the register address should be set.
  _setupSPI();
  char address = 0x80 | registerAddress;
  //If we're doing a multi-byte read, bit 6 needs to be set as well.
  if(numBytes > 1)address = address | 0x40;
  
  //Set the Chip select pin low to start an SPI packet.
  digitalWrite(_cs_pin, LOW);
  //Transfer the starting register address that needs to be read.
  SPI.transfer(address);
  //Continue to read registers until we've read the number specified, storing the results to the input buffer.
  for(int i=0; i<numBytes; i++){
    values[i] = SPI.transfer(0x00);
  }
  //Set the Chips Select pin high to end the SPI packet.
  digitalWrite(_cs_pin, HIGH);
}

void ADXL345Class::getRawAccelerations(int16_t * accel) {
  
	
	/*
	 uint32_t t1,t2;
	 t1=micros();
	 //*/
	
  char values[6];
  ADXL345.readRegister(ADXL_DATA, 6, values);
  //The X value is stored in values[0] and values[1].
  accel[0] = ((int16_t) ( ( ((uint16_t)values[1]) <<8) | ((uint16_t)values[0])) );
  //The Y value is stored in values[2] and values[3].
  accel[1] =  ((int16_t) ( ( ((uint16_t)values[3]) <<8) | ((uint16_t)values[2])) );
  //The Z value is stored in values[4] and values[5].
  accel[2] =  ((int16_t) ( ( ((uint16_t)values[5]) <<8) | ((uint16_t)values[4])) );
	
	/*
	 t2=micros();
	 if (t2 > t1) {
	 Serial.print("#Accel poll/process: ");
	 Serial.println(t2-t1);
	 }
	 //*/
}

//testing indicates ~170us per call @ 2MHz SPI
// 96us for float math
//ADXL Mandates a minimum of 3.4 us between reads at 
//	5MHz SPI or about 27 clocks at 8MHz, clearly we don't need any delay here.
//  @ Max data rate (3200Hz) values come every 312us so we are still good even there,
//	Though we wouldn't have much time left elsewhere!!
void ADXL345Class::getAccelerations(float * accel) {
  
  char values[6];

  ADXL345.readRegister(ADXL_DATA, 6, values);

  /*
  uint32_t t1,t2;
  t1=micros();
  //*/
  
  //The X value is stored in values[0] and values[1].
  accel[0] = _bits2gees * (float) ((int16_t) ( ( ((uint16_t)values[1]) <<8) | ((uint16_t)values[0])) );
  //The Y value is stored in values[2] and values[3].
  accel[1] = _bits2gees * (float) ((int16_t) ( ( ((uint16_t)values[3]) <<8) | ((uint16_t)values[2])) );
  //The Z value is stored in values[4] and values[5].
  accel[2] = _bits2gees * (float) ((int16_t) ( ( ((uint16_t)values[5]) <<8) | ((uint16_t)values[4])) );

  /*
  t2=micros();
  if (t2 > t1) {
	Serial.print("Accel poll/process: ");
	Serial.println(t2-t1);
  }
  //*/

}

ADXL345Class ADXL345;
