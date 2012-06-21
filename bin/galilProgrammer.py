#!/usr/bin/python
import serial,io,
from optparse import OptionParser


def main():
    default_bitrate=115200

    parser = OptionParser()

    parser.add_option("-f", "--file", help="file to send",
                      dest="file", metavar="FILE")
    parser.add_option("-d", "--device", help="The galil to program",
                      dest="device") 
                      
    (args, args_leftover)=parser.parse_args()
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
    
    for l in data:
        if '\\' in l:
            print 'Forbidden character (\\) in line:'
            print '     '+l
            
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
    print "Begin programming command response: "+resp
    for line in data:
        ser.write(line)
    
    ser.write('\r\\;\\\r')
    ser.flush()
    #import pdb; pdb.set_trace()
    resp=ser.read(3)

    if resp == ':::':
        print "Complete: "+resp
    else:
        print "Upload failed:"+resp
    ser.close()
    exit(0)

if __name__ == "__main__":
    main()
