#!/usr/bin/python2.6
import serial
import io
import time
from optparse import OptionParser


def receiveError(ser):
	raise Exception(ser.readline())
	

def receiveBattryStatus(ser):
	#read the line
	line=ser.readline()
	
	#extract the months of battery life remaining
	
	#act appropriately
	print line
	

def receiveTempData(ser):
	
	#read the line
	line=ser.readline()
	
	#store the temp data
	print line
	

def receiveAccelData(ser):
	
	#confirm receipt
	confirmReceipt(ser)
	
	#read the line
	line=ser.readline()
	
	#store the acceleration data
	print line


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
					  dest="timeout", default=1, type="int")
					  
	(args, args_leftover)=parser.parse_args()

	
	#open serial connection
	ser = serial.Serial(args.device, args.bitrate, timeout=args.timeout)
	#ser.nonblocking()	# set nonblocking operation, UNIX only
	sio = io.TextIOWrapper(io.BufferedRWPair(ser, ser))


	#Serial responses
	responses = { 't':lambda x: ser.write('t'+time.strftime("%b %d %Y %H:%M:%S")),
			  '?':lambda x: ser.write('!') ,
			  'T':ser.write('#'),
			  'A':ser.write('#')}
	cases = { 't':lambda x: ser.write('t'+time.strftime("%b %d %Y %H:%M:%S")),
			  '?':lambda x: ser.write('!'),
			  'T':receiveTempData,
			  'A':receiveAccelData,
			  'B':receiveBattryStatus,
			  'E':receiveError }
	
	#loop 1
	while True:
		'''byteIn=ser.read(1)
		try:
			cases[byteIn](ser)
		
		except KeyError:
			if ser.inWaiting()>0:
				line=ser.readline()
				print byteIn, line
		'''
		for line in ser:
			print line
			if line[0]=='?':
				ser.write('!')
				print '!'
			if line[0] in 'AT':
				ser.write('#')
				print '#'
			if line[0]=='t':
				str=bytearray(b'tNov 08 2011 21:44:34')
				ser.write(str)
				print str

				
		#other potential (ignored) errors: logging database full
		
	ser.close()


if __name__ == "__main__":
    main()
