#!/usr/bin/env python2.7
import time, os
from serial import Serial, SerialException
import logging.config
import logging
from m2fscontrol.m2fsConfig import M2FSConfig

serial = Serial()
serial.baudrate = 115200
serial.port = '/dev/m2fs_shutdownButton'
if __name__ == '__main__':
    logging.config.dictConfig(M2FSConfig.getAgentLogConfig('M2FSShutdownButton'))
    log = logging.getLogger('M2FSShutdownButton')
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
                    log.info("Received SHUTDOWN from shutdown button, shutting down now")
                    os.system('shutdown now')
        except SerialException as e:
            log.debug("Caught {}".format(e))
            time.sleep(1)
        except IOError:
            log.debug("Caught IOError", exc_info=True)
            time.sleep(1)