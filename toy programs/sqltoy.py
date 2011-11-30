#!/usr/bin/python2.6
import time
import sqlite3
import
from optparse import OptionParser
from __future__ import print_function

def recieverMain(device=None):
	try:
		starttime=time.time()
		identity=device
		while 1:
			t=time.time()
			if int(time-starttime)%60==0:
				#log this info
				log(device, t)
		
	except KeyError:
		raise
	
	
def sqlMain(dbfile=None):
	try:
		conn=sqlite3.connect(dbfile)
		
		#get database ready for access
		???
		
		while 1:
			#Listen for events from recievers
			#Listen for queries from master control



def main():
	
	parser = OptionParser()
	
	parser.add_option("-f", "--file", help="database file",
					  dest="logfilename", metavar="FILE",default=None)
	parser.add_option("-d", "--device", help="The serial device",
					  dest="device",defaul=None) 

	(args, args_leftover)=parser.parse_args()
	
	#device and file =>error
	
	#try:
	if args.logfilename!='':
		sqlMain(args.logfilename)
		
	#except IOError:
	#
	
	#try:
	recieverMain(args.device):
	

if __name__ == "__main__":
    main()
