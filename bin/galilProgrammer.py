#!/usr/bin/env python2.7
import serial,io, time
from optparse import OptionParser


def main():
    default_bitrate=115200

    parser = OptionParser()

    parser.add_option("-f", "--file", help="file to send",
                      dest="file", metavar="FILE")
    parser.add_option("-d", "--device", help="The galil to program",
                      dest="device")
    parser.add_option("--auto", help="Run #AUTO after programming",
                      dest="auto", action="store_true", default=False)
    parser.add_option("--burn", help="Store program in flash, takes 10 sec. Do not interrupt.",
                      dest="burn", action="store_true", default=False)
                      
    (args, args_leftover)=parser.parse_args()
    if not args.device or not args.file:
        parser.print_help()
        exit(1)
    
    bitrate=115200

    try:
        f =open(args.file,'r')
    except IOError:
        print "No such file"
        exit(0)

    data=filter(lambda x:x[0:3]!='REM' and x!='\n',f)
    f.close()
    data=map(lambda x:x.replace('\n','\r'),data)
    data=map(lambda x:x.replace('\t',' '),data)
    
    fail=False
    for l in data:
        if '\\' in l:
            print 'Forbidden character (\\) in line:'
            print '     '+l
            fail=True
        if len(l)>80:
            print 'Line too long: (%i)'%len(l)
            print '     '+l
            fail=True
    if fail:
        print "File not suitable for upload"
        exit(0)
            
    #open serial connection
    try:
        ser = serial.Serial(args.device, bitrate, timeout=1, writeTimeout=4)
    except serial.SerialException,e:
        print "Serial error: "+str(e)
        exit(0)
    #ser.nonblocking()	# set nonblocking operation, UNIX only

    ser.flushInput()
    ser.write('\\;EO0;HX0;HX1;HX2;HX3;HX4;HX5;HX6;HX7;ST*;DA*;DA*[0];DL\r')
    resp=ser.read(25)
    print "Begin programming command response: %s " %resp
    for line in data:
        ser.write(line)
        time.sleep(.010)
	
    ser.write('\r\\;\\\r')
    ser.flush()
    #import pdb; pdb.set_trace()
    resp=ser.read(3)

    if resp == ':::':
        print "Complete: "+resp
        if args.burn:
            ser.write('BP\r')
            ser.flush()
            time.sleep(10)
            ser.write('RS\r')
        elif args.auto:
            ser.write('XQ#AUTO,0\r')
            ser.flush()
            if ser.read(1) ==':':
                print "#AUTO started"
            else:
                print "XQ#AUTO,0 failed"
    else:
        print "Upload failed:"+resp
    ser.close()
    exit(0)

if __name__ == "__main__":
    main()
