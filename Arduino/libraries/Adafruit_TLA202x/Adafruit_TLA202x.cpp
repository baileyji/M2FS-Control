/*!
 *  @file Adafruit_TLA202x.cpp
 *
 *  @mainpage Adafruit library for the TLA202x ADCs from TI
 *
 *  @section intro_sec Introduction
 *
 * 	I2C Driver for the Library for the TLA202x 12-bit ADCs
 *
 * 	This is a library is written to work with the Adafruit TLA2024 breakout:
 * 	https://www.adafruit.com/product/47XX
 *
 * 	Adafruit invests time and resources providing this open source code,
 *  please support Adafruit and open-source hardware by purchasing products from
 * 	Adafruit!
 *
 *  @section dependencies Dependencies
 *  This library depends on the Adafruit BusIO library
 *
 *  This library depends on the Adafruit Unified Sensor library
 *
 *  @section author Author
 *
 *  Bryan Siepert for Adafruit Industries
 *
 * 	@section license License
 *
 * 	BSD (see license.txt)
 *
 * 	@section  HISTORY
 *
 *     v1.0 - First release
 */

#include "Arduino.h"
#include <Wire.h>

#include "Adafruit_TLA202x.h"

/**
 * @brief Construct a new Adafruit_TLA202x::Adafruit_TLA202x object
 *
 */
Adafruit_TLA202x::Adafruit_TLA202x(void) {}

/**
 * @brief Destroy the Adafruit_TLA202x::Adafruit_TLA202x object
 *
 */
Adafruit_TLA202x::~Adafruit_TLA202x(void) {
  if (config_register)
    delete config_register;
  if (data_register)
    delete data_register;
}

/*!
 *    @brief  Sets up the hardware and initializes I2C
 *    @param  i2c_address
 *            The I2C address to be used.
 *    @param  wire
 *            The Wire object to be used for I2C connections.
 *    @return True if initialization was successful, otherwise false.
 */
bool Adafruit_TLA202x::begin(uint8_t i2c_address, TwoWire *wire) {
  if (i2c_dev) {
    delete i2c_dev; // remove old interface
  }

  i2c_dev = new Adafruit_I2CDevice(i2c_address, wire);
  if (config_register)
    delete config_register;
  config_register =
      new Adafruit_BusIO_Register(i2c_dev, TLA202x_CONFIG_REG, 2, MSBFIRST);
  if (data_register)
    delete data_register;
  data_register =
      new Adafruit_BusIO_Register(i2c_dev, TLA202x_DATA_REG, 2, MSBFIRST);

  if (!i2c_dev->begin()) {
    return false;
  }
  return init();
}

/*!  @brief Initializer for post i2c init
 *   @returns True if chip identified and initialized
 */
bool Adafruit_TLA202x::init(void) {

  setDataRate(TLA202x_RATE_3300_SPS);
  setMode(TLA202x_MODE_CONTINUOUS);
  setMux(TLA202x_MUX_AIN0_GND);
  setRange(TLA202x_RANGE_6_144_V);

  return true;
}

/**
 * @brief Read the voltage of the currently set channel
 *
 * @return float the voltage in volts
 */
float Adafruit_TLA202x::readVoltage(void) {
  int16_t raw_voltage = data_register->read();
  // this will read the sign bit correctly, but shifting will move the bit out
  // of the msbit
  if (raw_voltage & 0x8000) {
    raw_voltage >>= 4;
    raw_voltage |= 0x8000;
  } else {
    raw_voltage >>= 4;
  }
  switch (current_range) {
  case TLA202x_RANGE_6_144_V:
    voltage = raw_voltage *= 3;
    break;
  case TLA202x_RANGE_4_096_V:
    voltage = raw_voltage *= 2;
    break;
  case TLA202x_RANGE_2_048_V:
    voltage = raw_voltage *= 1;
    break;
  case TLA202x_RANGE_1_024_V:
    voltage = raw_voltage *= 0.5;
    break;
  case TLA202x_RANGE_0_512_V:
    voltage = raw_voltage *= 0.25;
    break;
  case TLA202x_RANGE_0_256_V:
    voltage = raw_voltage *= 0.125;
    break;
  }
  voltage /= 1000.0; // mV =>V
  return voltage;
}

/**
 * @brief Set the active input to the given channel and take a single
 * reading
 *
 * @param channel The channel to read from
 * @return float The voltage in Volts
 */
float Adafruit_TLA202x::readOnce(tla202x_channel_t channel) {
  setChannel(channel);
  return readOnce();
}

/**
 * @brief Set the active input to the given channel and take a single
 * reading
 *
 * @param mux_setting Multiplexer setting to set the inputs to read between
 * @return float The voltage in Volts
 */
float Adafruit_TLA202x::readOnce(tla202x_mux_t mux_setting) {
  // single channel to gnd  are the last 4 mux enums
  setMux(mux_setting);
  return readOnce();
}

/**
 * @brief Take a single voltage reading using the current mux settings
 * @return float The voltage in Volts
 */
float Adafruit_TLA202x::readOnce(void) {
  // single channel to gnd  are the last 4 mux enums
  startOneShot();
  while (getOperationalState() == TLA202x_STATE_NO_READ) {
    delay(1);
  }
  return readVoltage();
}

/**
 * @brief Read the conversion status of the ADC for single-shot readings
 *
 * @return tla202x_state_t the current state
 */
tla202x_state_t Adafruit_TLA202x::getOperationalState(void) {
  Adafruit_BusIO_RegisterBits os_bit =
      Adafruit_BusIO_RegisterBits(config_register, 1, 15);
  return (tla202x_state_t)os_bit.read();
}

/**
 * @brief Switch to One-shot mode and start a single measurement
 * @return true: success false: failure
 */
bool Adafruit_TLA202x::startOneShot(void) {
  if (current_mode != TLA202x_MODE_ONE_SHOT) {
    setMode(TLA202x_MODE_ONE_SHOT);
  }
  Adafruit_BusIO_RegisterBits os_bit =
      Adafruit_BusIO_RegisterBits(config_register, 1, 15);
  return (tla202x_state_t)(os_bit.write(TLA202x_STATE_READ));
}

/**
 * @brief Gets the current rate at which pressure and temperature measurements
 * are taken
 *
 * @return tla202x_rate_t The current data rate
 */
tla202x_rate_t Adafruit_TLA202x::getDataRate(void) {
  Adafruit_BusIO_RegisterBits rate_bits =
      Adafruit_BusIO_RegisterBits(config_register, 3, 5);
  return (tla202x_rate_t)rate_bits.read();
} /**
   * @brief Sets the rate at which pressure and temperature measurements
   *
   * @param data_rate The data rate to set. Must be a `tla202x_rate_t`
   * @return true: success false: failure
   */
bool Adafruit_TLA202x::setDataRate(tla202x_rate_t data_rate) {
  Adafruit_BusIO_RegisterBits rate_bits =
      Adafruit_BusIO_RegisterBits(config_register, 3, 5);
  return rate_bits.write(data_rate);
}

/**
 * @brief Set the operational mode for the ADC, either
 * `TLA202x_MODE_CONTINUOUS` or `TLA202x_MODE_ONE_SHOT`
 * @param mode
 * @return true: success false: failure
 */
bool Adafruit_TLA202x::setMode(tla202x_mode_t mode) {
  Adafruit_BusIO_RegisterBits mode_bit =
      Adafruit_BusIO_RegisterBits(config_register, 1, 8);
  current_mode = mode;
  return mode_bit.write(mode);
}
/**
 * @brief Get the ADC's operational mode
 *
 * @return tla202x_mode_t the currently set mode
 */
tla202x_mode_t Adafruit_TLA202x::getMode(void) {
  Adafruit_BusIO_RegisterBits mode_bit =
      Adafruit_BusIO_RegisterBits(config_register, 1, 8);
  current_mode = (tla202x_mode_t)mode_bit.read();
  return current_mode;
}

/**
 * @brief Read the input multiplexer  configuration
 *
 * @return tla202x_mux_t the current mux configuration
 */
tla202x_mux_t Adafruit_TLA202x::getMux(void) {
  Adafruit_BusIO_RegisterBits mux_bits =
      Adafruit_BusIO_RegisterBits(config_register, 3, 12);
  return (tla202x_mux_t)mux_bits.read();
}

/**
 * @brief Set the input multiplexer to a new configuration
 *
 * @param mux The new multiplexer setting
 * @return true: success false: failure
 */
bool Adafruit_TLA202x::setMux(tla202x_mux_t mux) {
  Adafruit_BusIO_RegisterBits mux_bits =
      Adafruit_BusIO_RegisterBits(config_register, 3, 12);
  bool success = mux_bits.write(mux);
  // if mode is continuous, wait for a new reading to finish so the user doesn't
  // get the previous read from the old mux config
  if (current_mode == TLA202x_MODE_CONTINUOUS) {
    // fastest is 1/3300 => 0.0003 seconds, 0.3ms
    // slowest is 1/128 => 0.0078125 seconds, 8ms
    delay(10); // sleep 10ms for good measure
  }
  return success;
}

/**
 * @brief Set an input channel to be measured to GND
 *
 * @param channel The channel to be measured
 * @return true: success false: failure
 */
bool Adafruit_TLA202x::setChannel(tla202x_channel_t channel) {
  return setMux((tla202x_mux_t)(channel + 4));
}

/**
 * @brief Read the current measurement range based on the gain of the amplifier
 *
 * @return tla202x_range_t
 */
tla202x_range_t Adafruit_TLA202x::getRange(void) {
  Adafruit_BusIO_RegisterBits rate_bits =
      Adafruit_BusIO_RegisterBits(config_register, 3, 9);
  return (tla202x_range_t)rate_bits.read();
}
/**
 * @brief Set the gain of the PGA based on a new measurement range
 *
 * @param range The new measurement range
 * @return true: success false: failure
 *
 * ```
 * Adafruit_TLA202X tla = Adafruit_TLA202X();
 * tla.begin();
 *
 * // change the range to measure +/- 0.256 V (lowest noise)
 * tla.setRange(TLA202x_RANGE_0_256_V);
 * ```
 */
bool Adafruit_TLA202x::setRange(tla202x_range_t range) {
  Adafruit_BusIO_RegisterBits rate_bits =
      Adafruit_BusIO_RegisterBits(config_register, 3, 9);
  current_range = range;
  return rate_bits.write(range);
}
