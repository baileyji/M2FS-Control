#!/usr/bin/python2.6
import serial
import io
import time
from construct import *
from optparse import OptionParser
import numpy
import warnings


def fxn():
    warnings.warn("deprecated", DeprecationWarning)

with warnings.catch_warnings():
	warnings.simplefilter("ignore")
	warnings.warn("deprecated", DeprecationWarning)


class DataloggerRecord:
    
	def __init__(self, record):
		
		Num_Temp_Sensors=5
		FIFO_Length=32
		Acceleration_Record_Length=8+6*FIFO_Length
		Temp_Record_Length=8+4*Num_Temp_Sensors
		Combined_Record_Length=Acceleration_Record_Length+4*Num_Temp_Sensors
		
		tempConstruct=StrictRepeater(Num_Temp_Sensors,LFloat32("temps"))
		accelConstruct=StrictRepeater(FIFO_Length*3,SLInt16("accel"))
		
		self.temps=None
		self.accels=None
		self.unixtime=None
		self.millis=None
				
		if len(record)==Combined_Record_Length:
			self.temps=tempConstruct.parse(record[0:4*Num_Temp_Sensors+1])
			self.accels=accelConstruct.parse(record[4*Num_Temp_Sensors+1:-8])
		
		
		if len(record)==Acceleration_Record_Length:
			self.temps=None
			self.accels=accelConstruct.parse(record[0:-8])
		
		if len(record)==Temp_Record_Length:
			self.accels=None
			self.temps=tempConstruct.parse(record[0:-8])
		
		if len(record)>=Temp_Record_Length:
			self.unixtime=ULInt32("foo").parse(record[-8:-4])
			self.millis=ULInt32("foo").parse(record[-4:])
		
		if self.accels!=None:
			self.accels=numpy.array(self.accels).reshape([FIFO_Length,3])
			self.accels*=0.00390625
		
		
		
		
def receiveError(ser):
	raise Exception(ser.readline())
	

def receiveBatteryStatus(ser):
	pass
	
	
def receiveLogData(ser):
	
	#read the line
	#print "In waiting:", ser.inWaiting()

	recordsize=ord(ser.read(1))
	print "Record Size:", recordsize
	data=ser.read(recordsize)
	print "Got Record of length ",len(data)

	record=DataloggerRecord(data)
	
	print " ",record.unixtime
	print " ",record.millis
	print " ",record.temps
	if record.accels != None:
		print " ",record.accels.shape

	else:
		print " ",record.accels
	



def debugMessage(ser):
	l=[]
		
	line=ser.readline()
	#l=[c for c in line]
	print line[0:-1]




def tellTime(ser):
	utime=int(time.time())
	#utime=2172748161
	hexutime=hex(utime)[2:].upper()
	#hexutime='000102030405000000000'
	#str='t'+time.strftime("%b %d %Y %H:%M:%S")
	str='t'+3*UBInt32("f").build(utime)
	#str='t'+hexutime
	sentbytes=''.join([hex(ord(b))[2:] for b in str[1:]])
	#sentbytes=sentbytes.upper()

	print "Time: ", utime
	print " Sent Bytes:    ", sentbytes
	ser.write(str)
	#for b in str:
	#	ser.write(b)
		
	
	#ser.write(str[1:])
  #	for b in str:
  #		ser.write(b)




def main():
	default_bitrate=115200
	
	parser = OptionParser()
	
	parser.add_option("-f", "--file", help="logfile to store data",
					  dest="logfilename", metavar="FILE")
	parser.add_option("-d", "--device", help="The serial device",
					  dest="device") 
	parser.add_option("-r", "--bitrate", help="The serial bitrate (default 115200)",
					  dest="bitrate", default=default_bitrate, type="int")
	parser.add_option("-t", "--timeout", help="The timeout before assuming receipt of message is complete",
					  dest="timeout", default=3, type="int")
					  
	(args, args_leftover)=parser.parse_args()

	
	#open serial connection
	ser = serial.Serial(args.device, args.bitrate, timeout=args.timeout)
	ser.flushInput()
	#ser.nonblocking()	# set nonblocking operation, UNIX only
	sio = io.BufferedRWPair(ser, ser)

	
	#loop 1
	byteOut=0
	while True:
		byteIn=ser.read(1)
		
		if byteIn == 't':
			s='t'+UBInt32("f").build(byteOut<<8 | byteOut)
			ser.write(s[0])
			ser.write('\x00'+s[1])
			ser.write('\x00'+s[2])
			ser.write('\x00'+s[3])
			ser.write('\x00'+s[4])
			byteOut+=1

			 
		if byteIn == '#':
			debugMessage(ser)
	
		
		#other potential (ignored) errors: logging database full
		
	ser.close()


if __name__ == "__main__":
    main()
