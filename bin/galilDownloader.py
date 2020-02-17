#!/usr/bin/env python2.7
import serial, os
from optparse import OptionParser


def main():
    default_bitrate=115200

    parser = OptionParser()

    parser.add_option("-f", "--file", help="output filename, must not exist",
                      dest="file", metavar="FILE")
    parser.add_option("-d", "--device",
                      help="The galil from which to fetch the code",
                      dest="device")
                      
    (args, args_leftover)=parser.parse_args()
    if not args.device or not args.file:
        parser.print_help()
        exit(1)

    if os.path.exists(args.file):
        print 'Output file already exists'
        parser.print_help()
        exit(1)

    #open serial connection
    try:
        ser = serial.Serial(args.device, 115200, timeout=1, writeTimeout=4)
    except serial.SerialException,e:
        print "Serial error: "+str(e)
        exit(0)

    try:
        f=open(args.file,'w')
    except IOError:
        print "Could not open file for writing"
        exit(1)

    ser.flushInput()
    ser.flushOutput()
    ser.write('LS\r')
    resp=ser.read(80*2001)
    lines=resp.split('\r\n')
    for l in lines:
        f.write(l+'\n')
#    resp=ser.readline()
#    if resp:
#        f.write(resp)
#    while resp !=':':
#        resp=ser.readline()
#        if resp:
#            f.write(resp)

    f.close()
    ser.close()
    exit(0)

if __name__ == "__main__":
    main()
