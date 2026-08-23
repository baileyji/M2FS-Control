/*!

 *  @file Adafruit_TLA202x.h
 *
 * 	I2C Driver for the Adafruit library for the TLA202x ADCs from TI
 *
 * 	This is a library is written to work with the Adafruit TLA2024 breakout:
 * 	https://www.adafruit.com/products/47XX
 *
 * 	Adafruit invests time and resources providing this open source code,
 *  please support Adafruit and open-source hardware by purchasing products from
 * 	Adafruit!
 *
 *
 *	BSD license (see license.txt)
 */
// "requires_busio": "y",
//   "requires_sensor": "y",
#ifndef _ADAFRUIT_TLA202x_H
#define _ADAFRUIT_TLA202x_H

#include "Arduino.h"
#include <Adafruit_BusIO_Register.h>
#include <Adafruit_I2CDevice.h>
#include <Adafruit_Sensor.h>
#include <Wire.h>

#define TLA202x_I2CADDR_DEFAULT 0x48 ///< TLA202x default i2c address

#define TLA202x_DATA_REG 0x00   ///< Data Register
#define TLA202x_CONFIG_REG 0x01 ///< Configuration Register
///////////////////////////////////////////////////////////////

/**
 * @brief Options for `readVoltage` to choose the single channel to read
 *
 */
typedef enum {
  TLA202x_CHANNEL_0, ///< Channel 0
  TLA202x_CHANNEL_1, ///< Channel 1
  TLA202x_CHANNEL_2, ///< Channel 2
  TLA202x_CHANNEL_3, ///< Channel 3
} tla202x_channel_t;

/**
 * @brief
 *
 * Allowed values for `setDataRate`.
 */
typedef enum {
  TLA202x_RATE_128_SPS,  ///< 128 Samples per Second
  TLA202x_RATE_250_SPS,  ///< 250 Samples per Second
  TLA202x_RATE_490_SPS,  ///< 490 Samples per Second
  TLA202x_RATE_920_SPS,  ///< 920 Samples per Second
  TLA202x_RATE_1600_SPS, ///< 1600 Samples per Second
  TLA202x_RATE_2400_SPS, ///< 2400 Samples per Second
  TLA202x_RATE_3300_SPS, ///< 3300 Samples per Second
} tla202x_rate_t;

/**
 * @brief Options for `setRate`
 *
 */
typedef enum {
  TLA202x_MODE_CONTINUOUS, // Take a new measurement as soon as the previous
                           // measurement is finished
  TLA202x_MODE_ONE_SHOT    // Take a single measurement then go into a low-power
                           // mode
} tla202x_mode_t;

/**
 * @brief Options for `setMux`
 *
 * Selects which inputs will be used for the positive (AINp) and negative (AINn)
 * inputs
 *
 */
typedef enum {
  TLA202x_MUX_AIN0_AIN1, ///< AINp = AIN 0, AINn = AIN 1
  TLA202x_MUX_AIN0_AIN3, ///< AINp = AIN 0, AINn = AIN 3
  TLA202x_MUX_AIN1_AIN3, ///< AINp = AIN 1, AINn = AIN 3
  TLA202x_MUX_AIN2_AIN3, ///< AINp = AIN 2, AINn = AIN 3
  TLA202x_MUX_AIN0_GND,  ///< AINp = AIN 0, AINn = GND
  TLA202x_MUX_AIN1_GND,  ///< AINp = AIN 1, AINn = GND
  TLA202x_MUX_AIN2_GND,  ///< AINp = AIN 2, AINn = GND
  TLA202x_MUX_AIN3_GND,  ///< AINp = AIN 3, AINn = GND
} tla202x_mux_t;

/**
 * @brief Options for `setRange`
 *
 */
typedef enum {
  TLA202x_RANGE_6_144_V, ///< Measurements range from +6.144 V to -6.144 V
  TLA202x_RANGE_4_096_V, ///< Measurements range from +4.096 V to -4.096 V
  TLA202x_RANGE_2_048_V, ///< Measurements range from +2.048 V to -2.048 V
  TLA202x_RANGE_1_024_V, ///< Measurements range from +1.024 V to -1.024 V
  TLA202x_RANGE_0_512_V, ///< Measurements range from +0.512 V to -0.512 V
  TLA202x_RANGE_0_256_V  ///< Measurements range from +0.256 V to -0.256 V
} tla202x_range_t;

/**
 * @brief Possible states to be returned by `getOperationalState`
 *
 */
typedef enum {
  TLA202x_STATE_NO_READ, ///< Single-shot read in progress
  TLA202x_STATE_READ,    ///< Single-shot read available to read or start read
} tla202x_state_t;
/*!
 *    @brief  Class that stores state and functions for interacting with
 *            the TLA202x 12-bit ADCs
 */
class Adafruit_TLA202x {
public:
  Adafruit_TLA202x();
  ~Adafruit_TLA202x();

  bool begin(uint8_t i2c_addr = TLA202x_I2CADDR_DEFAULT, TwoWire *wire = &Wire);

  bool init(void);

  float readVoltage(void);
  float readOnce(void);
  float readOnce(tla202x_mux_t mux_setting);
  float readOnce(tla202x_channel_t channel);

  tla202x_rate_t getDataRate(void);
  bool setDataRate(tla202x_rate_t rate);

  bool setMode(tla202x_mode_t mode);
  tla202x_mode_t getMode(void);

  bool setChannel(tla202x_channel_t channel);
  bool setMux(tla202x_mux_t mux);
  tla202x_mux_t getMux(void);

  bool setRange(tla202x_range_t range);
  tla202x_range_t getRange(void);

  tla202x_state_t getOperationalState(void);
  bool startOneShot(void);

private:
  void _read(void);

  Adafruit_BusIO_Register *config_register = NULL;
  Adafruit_BusIO_Register *data_register = NULL;

  float voltage; ///< Last reading's pressure (hPa) before scaling
  tla202x_range_t current_range;
  tla202x_mode_t current_mode;
  Adafruit_I2CDevice *i2c_dev = NULL; ///< Pointer to I2C bus interface
};

#endif
