#!/usr/bin/python2.6
import serial
import io
import time
from optparse import OptionParser
import warnings


def main():
	default_bitrate=460800
	
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
	ser.flushInput()
	#ser.nonblocking()	# set nonblocking operation, UNIX only
	
	#loop 1
	while True:
		bytesIn=ser.read(10)
		if len(bytesIn) > 0:
			print [ord(c) for c in bytesIn]
		
	ser.close()


if __name__ == "__main__":
    main()
