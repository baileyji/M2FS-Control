/*
  EEPROMEx.h - Extended EEPROM library
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

#ifndef EEPROMEX_h
#define EEPROMEX_h

#include <EEPROM.h>

#if ARDUINO >= 100
#include <Arduino.h> 
#else
#include <WProgram.h> 
#endif
#include <inttypes.h>
#include <avr/eeprom.h>

// Boards with ATmega328, Duemilanove, Uno, UnoSMD, Lilypad - 1024 bytes (1 kilobyte)
// Boards with ATmega1280 or 2560, Arduino Mega series – 4096 bytes (4 kilobytes)
// Boards with ATmega168, Lilypad, old Nano, Diecimila  – 512 bytes (1/2 kilobyte)

#define EEPROMSizeATmega168   512     
#define EEPROMSizeATmega328   1024     
#define EEPROMSizeATmega1280  4096     

#define EEPROMSizeUno         EEPROMSizeATmega328     
#define EEPROMSizeUnoSMD      EEPROMSizeATmega328
#define EEPROMSizeLilypad     EEPROMSizeATmega328
#define EEPROMSizeDuemilanove EEPROMSizeATmega328
#define EEPROMSizeMega        EEPROMSizeATmega1280
#define EEPROMSizeDiecimila   EEPROMSizeATmega168
#define EEPROMSizeNano        EEPROMSizeATmega168

class EEPROMClassEx
{
	  
  public:
	EEPROMClassEx();
	bool 	 isReady();
	int 	 writtenBytes();
    void 	 setMemPool(uint16_t base, uint16_t memSize);
	void  	 setMaxAllowedWrites(unsigned long allowedWrites);
	int 	 getAddress(uint16_t noOfBytes);
    
	uint8_t  read(uint16_t);	
	bool 	 readBit(uint16_t, byte);
	uint8_t  readByte(uint16_t);
    uint16_t readInt(uint16_t);
    uint32_t readLong(uint16_t);
	float    readFloat(uint16_t);
	double   readDouble(uint16_t);
			
    bool     write(uint16_t, uint8_t);
	bool 	 writeBit(uint16_t , uint8_t, bool);
	bool     writeByte(uint16_t, uint8_t);
	bool 	 writeInt(uint16_t, uint16_t);
	bool 	 writeLong(uint16_t, uint32_t);
	bool 	 writeFloat(uint16_t, float);
	bool 	 writeDouble(uint16_t, double);

	bool     update(uint16_t, uint8_t);
	bool 	 updateBit(uint16_t , uint8_t, bool);
	bool     updateByte(uint16_t, uint8_t);
	bool 	 updateInt(uint16_t, uint16_t);
	bool 	 updateLong(uint16_t, uint32_t);
	bool 	 updateFloat(uint16_t, float);
	bool 	 updateDouble(uint16_t, double);

	
    // Use template for other data formats


	template <class T> int readBlock(uint16_t address, const T value[], int items)
	{
		if (!isReadOk(address+items*sizeof(T))) return 0;
		unsigned int i;
		for (i = 0; i < items; i++) 
			readBlock<T>(address+(i*sizeof(T)),value[i]);
		return i;
	}
	
	template <class T> int readBlock(uint16_t address, const T& value)
	{		
		eeprom_read_block((void*)&value, (const void*)address, sizeof(value));
		return sizeof(value);
	}
	
	template <class T> int writeBlock(uint16_t address, const T value[], int items)
	{	
		if (!isWriteOk(address+items*sizeof(T))) return 0;
		unsigned int i;
		for (i = 0; i < items; i++) 
			  writeBlock<T>(address+(i*sizeof(T)),value[i]);
		return i;
	}
	
	template <class T> int writeBlock(uint16_t address, const T& value)
	{
		if (!isWriteOk(address+sizeof(value))) return 0;
		eeprom_write_block((void*)&value, (void*)address, sizeof(value));			  			  
		return sizeof(value);
	}

	template <class T> int updateBlock(uint16_t address, const T value[], int items)
	{
		int writeCount=0;
		if (!isReadOk(address+items*sizeof(T)-1)) return 0;
		unsigned int i;
		for (i = 0; i < items; i++) 
			  writeCount+= updateBlock<T>(address+(i*sizeof(T)),value[i]);
		return writeCount;
	}
	
	template <class T> int updateBlock(uint16_t address, const T& value)
	{
		int writeCount=0;
		if (!isReadOk(address+sizeof(value)-1)) return 0;
		const byte* bytePointer = (const byte*)(const void*)&value;
		for (unsigned int i = 0; i < sizeof(value); i++) {
            /*
            Serial.print("addr=");Serial.print(address);
            Serial.print(" *bP=");Serial.print(*bytePointer);
            Serial.print(" bP=");Serial.print(reinterpret_cast<uint32_t>(bytePointer));
            Serial.print(" value=");Serial.print(value);
            Serial.print(" &value=");Serial.println(reinterpret_cast<uint32_t>(&value));
            */
			if (read(address)!=*bytePointer) {
                write(address, *bytePointer);
				writeCount++;		
			}
			address++;
			*bytePointer++;
		}
		return writeCount;
	}
	
	
	
private:
	//Private variables
	static int _base;
	static int _memSize;
	static int _nextAvailableaddress;	
	static unsigned long _writeCounts;
	int _allowedWrites;	
	bool checkWrite(int base,int noOfBytes);	
	bool isWriteOk(uint16_t address);
	bool isReadOk(uint16_t address);
};

extern EEPROMClassEx EEPROM;

#endif

