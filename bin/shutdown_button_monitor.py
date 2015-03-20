import time, os
from serial import Serial, SerialException
serial=Serial()
serial.baudrate=115200
serial.port='/dev/shutdownButton'
#serial.port='/dev/tty.usbserial-A9007Pp8'
if __name__=='__main__':
    while True:
        try:
            if not serial.isOpen():
                print 'Opening...'
                serial.open()
                print 'Open'
            else:
                data=serial.readline()
                print 'Got: "{}"'.format(data)
                if 'SHUTDOWN' in data:
                    print 'shutdown now'
                    os.system('shutdown now')
        except SerialException:
            print 'Serial exception'
            time.sleep(1)
        except IOError:
            print 'IOError'
            time.sleep(1)