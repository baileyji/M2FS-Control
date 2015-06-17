#!/usr/bin/env python2.7
import time, os
from serial import Serial, SerialException
serial=Serial()
serial.baudrate=115200
serial.port='/dev/shutdownButton'
if __name__=='__main__':
    while True:
        try:
            if not serial.isOpen():
                print 'Opening...'
                serial.open()
                serial.flushInput()
                print 'open.'
            else:
                data=serial.readline()
#                print 'Got: "{}"'.format(data)
                if 'SHUTDOWN' in data:
                    print 'shutdown now'
                    os.system('shutdown now')
        except SerialException:
            print 'Serial exception'
            time.sleep(1)
        except IOError:
            print 'IOError'
            time.sleep(1)