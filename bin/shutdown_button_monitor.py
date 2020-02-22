#!/usr/bin/env python2.7
import time, os
from serial import Serial, SerialException
import logging
from m2fscontrol.m2fsConfig import M2FSConfig

serial = Serial()
serial.baudrate = 115200
serial.port = '/dev/m2fs_shutdownButton'
if __name__ == '__main__':
    logging.basicConfig()
    log = logging.getLogger('M2FSShutdownButton')
    log.setLevel(M2FSConfig.getAgentLogLevel('M2FSShutdownButton'))
    while True:
        try:
            if not serial.isOpen():
                log.debug('Attempting to connect to shutdown button')
                serial.open()
                serial.flushInput()
                log.info("Connected to shutdown button.")
            else:
                data=serial.readline()
#                print 'Got: "{}"'.format(data)
                if 'SHUTDOWN' in data:
                    log.info("Recieved SHUTDOWN from shutdown button, shutting down now")
                    os.system('shutdown now')
        except SerialException:
            log.debug("Caught SerialException", exc_info=True)
            time.sleep(1)
        except IOError:
            log.debug("Caught IOError", exc_info=True)
            time.sleep(1)