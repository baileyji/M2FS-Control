#ifndef __ADXL345_H__
#define __ADXL345_H__
//Add the SPI library so we can communicate with the ADXL345 sensor
#include <SPI.h>
#include <WProgram.h>
#include <Wiring.h>


//Default Chip select pin
#define ADXL_CHIP_SELECT_PIN 10


//ADXL345 Register Addresses
#define	ADXL_DEVID		0x00	//Device ID Register
#define ADXL_THRESH_TAP	0x1D	//Tap Threshold
#define	ADXL_OFSX		0x1E	//X-axis offset
#define	ADXL_OFSY		0x1F	//Y-axis offset
#define	ADXL_OFSZ		0x20	//Z-axis offset
#define	ADXL_DURATION	0x21	//Tap Duration
#define	ADXL_LATENT		0x22	//Tap latency
#define	ADXL_WINDOW		0x23	//Tap window
#define	ADXL_THRESH_ACT	0x24	//Activity Threshold
#define	ADXL_THRESH_INACT	0x25	//Inactivity Threshold
#define	ADXL_TIME_INACT	0x26	//Inactivity Time
#define	ADXL_ACT_INACT_CTL	0x27	//Axis enable control for activity and 
									//inactivity detection
#define	ADXL_THRESH_FF	0x28	//free-fall threshold
#define	ADXL_TIME_FF		0x29	//Free-Fall Time
#define	ADXL_TAP_AXES	0x2A	//Axis control for tap/double tap
#define ADXL_ACT_TAP_STATUS	0x2B	//Source of tap/double tap
#define	ADXL_BW_RATE		0x2C	//Data rate and power mode control
#define ADXL_POWER_CTL	0x2D	//Power Control Register
#define	ADXL_INT_ENABLE	0x2E	//Interrupt Enable Control
#define	ADXL_INT_MAP		0x2F	//Interrupt Mapping Control
#define	ADXL_INT_SOURCE	0x30	//Source of interrupts
#define	ADXL_DATA_FORMAT	0x31	//Data format control
#define ADXL_DATA		0x32
#define ADXL_DATAX0		0x32	//X-Axis Data 0
#define ADXL_DATAX1		0x33	//X-Axis Data 1
#define ADXL_DATAY0		0x34	//Y-Axis Data 0
#define ADXL_DATAY1		0x35	//Y-Axis Data 1
#define ADXL_DATAZ0		0x36	//Z-Axis Data 0
#define ADXL_DATAZ1		0x37	//Z-Axis Data 1
#define	ADXL_FIFO_CTL	0x38	//FIFO control
#define	ADXL_FIFO_STATUS	0x39	//FIFO status


#define	ADXL_TRIGGER_INT1 0x00
#define	ADXL_TRIGGER_INT2 0x20

#define	ADXL_FIFO_BYPASS  0x00
#define	ADXL_FIFO_FIFO	  0x40
#define	ADXL_FIFO_STREAM  0x80
#define	ADXL_FIFO_TRIGGER 0xC0

#define ADXL_INT_ACTIVELOW 0x20 
#define ADXL_16G_RANGE 0x03
#define ADXL_FULL_RES 0x08


#define	ADXL_INT_FREEFALL     0x04
#define	ADXL_INT_DATAREADY    0x80
#define	ADXL_INT_SINGLETAP    0x40
#define ADXL_INT_DOUBLETAP    0x20
#define ADXL_INT_ACTIVITY     0x10
#define ADXL_INT_INACTIVITY   0x08
#define ADXL_INT_WATERMARK    0x02
#define	ADXL_INT_OVERRUN      0x01


#define	ADXL_LINK		5
#define	ADXL_AUTOSLEEP  4
#define	ADXL_MEASURE    3
#define ADXL_SLEEP		2
#define ADXL_WAKEUP_8   0x0
#define ADXL_WAKEUP_4   0x1
#define ADXL_WAKEUP_2   0x2
#define ADXL_WAKEUP_1   0x3

#define	ADXL_RATE_3200  0xF
#define	ADXL_RATE_1600	0xE
#define	ADXL_RATE_800	0xD
#define	ADXL_RATE_400   0xC
#define	ADXL_RATE_200   0xB
#define ADXL_RATE_100   0xA
#define ADXL_RATE_50	0x9
#define ADXL_RATE_25	0x8
#define ADXL_RATE_12	0x7
#define	ADXL_RATE_6		0x6

#define	ADXL_LP_RATE_400	0x10|ADXL_RATE_400
#define	ADXL_LP_RATE_200	0x10|ADXL_RATE_200
#define ADXL_LP_RATE_100	0x10|ADXL_RATE_100
#define ADXL_LP_RATE_50		0x10|ADXL_RATE_50
#define ADXL_LP_RATE_25		0x10|ADXL_RATE_25
#define ADXL_LP_RATE_12		0x10|ADXL_RATE_12



class ADXL345Class {

private:
  uint8_t _cs_pin;
  uint8_t _dataFormat;
  float _bits2gees;

public:
  ADXL345Class(void);
    
  // Set up the ADXL chip
  boolean init(uint8_t csPin = ADXL_CHIP_SELECT_PIN);
  
  void writeRegister(char registerAddress, char value);
  void readRegister(char registerAddress, int numBytes, char * values);
  
  //accel must be size [3] or larger
  void getAccelerations(float * accel);
  void selfTest(int16_t * accel);
  void getRawAccelerations(int16_t * accel);
  char getInterruptSource();
  
  
  
private:
  void _setupSPI();

};

extern ADXL345Class ADXL345;

#endif
