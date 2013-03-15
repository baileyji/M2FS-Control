/*
  EEPROMEx.cpp - Extended EEPROM library
  Copyright (c) 2012 Thijs Elenbaas.  All right reserved.

  This library is free software; you can redistribute it and/or
  modify it under the terms of the GNU Lesser General Public
  License as published by the Free Software Foundation; either
  version 2.1 of the License, or (at your option) any later version.

  This library is distributed in the hope that it will be useful,
  but WITHOUT ANY WARRANTY; without even the implied warranty of
  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
  Lesser General Public License for more details.

  You should have received a copy of the GNU Lesser General Public
  License along with this library; if not, write to the Free Software
  Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
*/

/******************************************************************************
 * Includes
 ******************************************************************************/
#include "EEPROMEx.h"

/******************************************************************************
 * Definitions
 ******************************************************************************/

 #define _EEPROMEX_VERSION 0.8.2 // software version of this library
// #define _EEPROMEX_DEBUG         // Enables logging of maximum of writes and out-of-memory
/******************************************************************************
 * Constructors
 ******************************************************************************/

// Boards with ATmega328, Duemilanove, Uno, Uno SMD, Lilypad - 1024 bytes (1 kilobyte)
// Boards with ATmega1280 or 2560, Arduino Mega series – 4096 bytes (4 kilobytes)
// Boards with ATmega168, Lilypad, old Nano, Diecimila  – 512 bytes
// By default we choose conservative settings
EEPROMClassEx::EEPROMClassEx()
  :  _allowedWrites(10000)
{
}
 
/******************************************************************************
 * User API
 ******************************************************************************/

void EEPROMClassEx::setMemPool(uint16_t base, uint16_t memSize) {
	//Base can only be adjusted if no addresses have already been issued
	if (_nextAvailableaddress == _base) 
		_base = base;
		_nextAvailableaddress=_base;
	
	//Ceiling can only be adjusted if not below issued addresses
	if (memSize >= _nextAvailableaddress ) 
		_memSize = memSize;

	#ifdef _EEPROMEX_DEBUG    
	if (_nextAvailableaddress != _base) 
		Serial.println(F("Cannot change base, addresses have been issued"));

	if (memSize < _nextAvailableaddress )  
		Serial.println(F("Cannot change ceiling, below issued addresses"));
	#endif	
	
}

void EEPROMClassEx::setMaxAllowedWrites(unsigned long allowedWrites) {
#ifdef _EEPROMEX_DEBUG
	_allowedWrites = allowedWrites;
#endif			
}

int EEPROMClassEx::getAddress(uint16_t noOfBytes){
	int availableaddress   = _nextAvailableaddress;
	_nextAvailableaddress += noOfBytes;

#ifdef _EEPROMEX_DEBUG    
	if (_nextAvailableaddress > _memSize) {
		Serial.println(F("Attempt to access address outside of EEPROM memory"));
		return -availableaddress;
	} else {
		return availableaddress;
	}
#endif
	return availableaddress;		
}
 

bool EEPROMClassEx::isReady() {
	return eeprom_is_ready();
}

uint8_t EEPROMClassEx::read(uint16_t address)
{
	return readByte(address);
}

bool EEPROMClassEx::readBit(uint16_t address, byte bit) {
	  if (bit> 7) return false; 
	  if (!isReadOk(address+sizeof(uint8_t))) return false;
	  byte byteVal =  eeprom_read_byte((unsigned char *) address);      
	  byte bytePos = (1 << bit);
      return (byteVal & bytePos);
}

uint8_t EEPROMClassEx::readByte(uint16_t address)
{	
	if (!isReadOk(address+sizeof(uint8_t))) return 0;
	return eeprom_read_byte((unsigned char *) address);
}

uint16_t EEPROMClassEx::readInt(uint16_t address)
{
	if (!isReadOk(address+sizeof(uint16_t))) return 0;
	return eeprom_read_word((unsigned int *) address);
}

uint32_t EEPROMClassEx::readLong(uint16_t address)
{
	if (!isReadOk(address+sizeof(uint32_t))) return 0;
	return eeprom_read_dword((unsigned long *) address);
}

float EEPROMClassEx::readFloat(uint16_t address)
{
	if (!isReadOk(address+sizeof(float))) return 0;
	float _value;
	readBlock<float>(address, _value);
	return _value;
}

double EEPROMClassEx::readDouble(uint16_t address)
{
	if (!isReadOk(address+sizeof(double))) return 0;	
	double _value;
	readBlock<double>(address, _value);
	return _value;
}

bool EEPROMClassEx::write(uint16_t address, uint8_t value)
{
	return writeByte(address, value);
}

bool EEPROMClassEx::writeBit(uint16_t address, uint8_t bit, bool value) {
	updateBit(address, bit, value);
}


bool EEPROMClassEx::writeByte(uint16_t address, uint8_t value)
{
	if (!isWriteOk(address+sizeof(uint8_t)-1)) return false;
	eeprom_write_byte((unsigned char *) address, value);
	return true;
}

bool EEPROMClassEx::writeInt(uint16_t address, uint16_t value)
{
	if (!isWriteOk(address+sizeof(uint16_t)-1)) return false;
	eeprom_write_word((unsigned int *) address, value);
	return true;
}

bool EEPROMClassEx::writeLong(uint16_t address, uint32_t value)
{
	if (!isWriteOk(address+sizeof(uint32_t)-1)) return false;
	eeprom_write_dword((unsigned long *) address, value);
	return true;
}

bool EEPROMClassEx::writeFloat(uint16_t address, float value)
{
	return (writeBlock<float>(address, value)!=0);	
}

bool EEPROMClassEx::writeDouble(uint16_t address, double value)
{
	return (writeBlock<float>(address, value)!=0);	
}

bool EEPROMClassEx::update(uint16_t address, uint8_t value)
{
	return (updateByte(address, value));
}

bool EEPROMClassEx::updateBit(uint16_t address, uint8_t bit, bool value) 
{
	  if (bit> 7) return false; 
	  
	  byte byteValInput  = readByte(address);
	  byte byteValOutput = byteValInput;	  
	  // Set bit
	  if (value) {	    
		byteValOutput |= (1 << bit);  //Set bit to 1
	  } else {		
	    byteValOutput &= !(1 << bit); //Set bit to 0
	  }
	  // Store if different from input
	  if (byteValOutput!=byteValInput) {
		writeByte(address, byteValOutput);	  
	  }
}

bool EEPROMClassEx::updateByte(uint16_t address, uint8_t value)
{
	return (updateBlock<uint8_t>(address, value)!=0);
}

bool EEPROMClassEx::updateInt(uint16_t address, uint16_t value)
{
	return (updateBlock<uint16_t>(address, value)!=0);
}

bool EEPROMClassEx::updateLong(uint16_t address, uint32_t value)
{
	return (updateBlock<uint32_t>(address, value)!=0);
}

bool EEPROMClassEx::updateFloat(uint16_t address, float value)
{
	return (updateBlock<float>(address, value)!=0);
}

bool EEPROMClassEx::updateDouble(uint16_t address, double value)
{
	return (updateBlock<double>(address, value)!=0);
}

bool EEPROMClassEx::isWriteOk(uint16_t address)
{
    
	_writeCounts++;
    //Serial.print("WriteCount=");Serial.print(_writeCounts);
    //Serial.print(" Address=");Serial.println(address);
	if (_allowedWrites == 0 || _writeCounts > _allowedWrites ) {
        #ifdef _EEPROMEX_DEBUG
		Serial.println(F("Exceeded maximum number of writes"));
        #endif
		return false;
	}
	
	if (address > _memSize) {
        #ifdef _EEPROMEX_DEBUG
		Serial.println(F("Attempt to write outside of EEPROM memory"));
        #endif
		return false;
	} else {
		return true;
	}
}

bool EEPROMClassEx::isReadOk(uint16_t address)
{
	if (address > _memSize) {
        #ifdef _EEPROMEX_DEBUG  
		Serial.println(F("Attempt to read outside of EEPROM memory"));
        #endif
		return false;
	} else {
		return true;
	}	
}

int EEPROMClassEx::_base= 0;
int EEPROMClassEx::_memSize= EEPROMSizeMega;
int EEPROMClassEx::_nextAvailableaddress= 0;
unsigned long EEPROMClassEx::_writeCounts =0;

EEPROMClassEx EEPROM;
