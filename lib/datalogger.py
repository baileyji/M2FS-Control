import time, select
from serial import Serial, SerialException
import threading
import Queue
import logging
import logging.handlers
import LoggerRecord

LOGGING_LEVEL=logging.ERROR


class DataloggerConnection(Serial):
    """
    Datalogger Connection Class
    
    Wrapper for Serial which knows how to tell the datalogger the unixtime
    and grab a log message.
    """
    def __init__(self, device):
        """
        Wrap Serial initialization so we can instantite unpoened w/o problems
        This is fine, because it might be unplugged.
        """
        Serial.__init__(self, baudrate=115200, timeout=1)
        self.timeout=1
        self.port=device
        try:
            self.open()
        except SerialException:
            pass
    
    def readLogData(self):
        """
        Read one byte, then read the number of bytes specified in the first byte
        
        Return the read data
        """
        return self.read(ord(self.read(1)))
    
    def telltime(self):
        """ 
        Send the current unix time to the datalogger as a 32bit big endian
        
        For some reason I can't identify the null bytes are necessary for the 
        message to be received properly.
        """
        s='t'+UBInt32("f").build(int(time.time()))
        self.logger.debug('Sending time as %s' % s.encode('string_escape'))
        self.write(s[0])
        self.write('\x00'+s[1])
        self.write('\x00'+s[2])
        self.write('\x00'+s[3])
        self.write('\x00'+s[4])

class DataloggerListener(threading.Thread):
    """
    This is a thread class that handles communication with a datalogger and
    yields the reported data via a queue.
    """
    def __init__(self, side, device, queue):
        """
        Start a new thread to capture temperature and accelerometer data from
        an M2FS datalogger on device. Place data into the Queue passed in Queue.
        """
        if side != 'R' and side != 'B':
            raise Exception('Side must be R or B')
        threading.Thread.__init__(self)
        self.daemon=True
        self.queue=queue
        self.side=side
        self.datalogger=DataloggerConnection(device)
        self.logger=logging.getLogger('DataloggerListener')
        self.logger.setLevel(LOGGING_LEVEL)
        self.logger.info("Listener started")
    
    def run(self):
        """
        
        It runs, listening for #, E, L, or t from the datalogger and acting
        accordingly.
        E) An \n delimited error message follows, recieve it
        L) A log record follows, recieve it, acknowledge it, and create a
            DataloggerRecord from it
        #) A \n delimited dubug message follows, receive it
        t) The datalogger is requesting the current time, send it

        As error, log, or debug messages are received, they are placed into the
        queue as the second element in a tuple, the first identifing the 
        contents: 'record', 'error', 'debug'

        If the datalogger is disconnected, keep trying to connect
        """
        while True:
            if not self.datalogger.isOpen():
                try:
                    self.datalogger.open()
                except SerialException:
                    time.sleep(1)
                    pass
            if self.datalogger.isOpen():
                try:
                    reader, junk, errors=select.select([self.datalogger],
                                    [self.datalogger], [self.datalogger], 5)
                    if reader:
                        byte=self.datalogger.read(1)
                        if byte == 't':
                            self.datalogger.telltime()
                            self.logger.debug('Handled time query')
                        elif byte == 'L':
                            logdata=self.datalogger.readLogData()
                            self.datalogger.write('#')
                            try:
                                record=LoggerRecord(self.side, logdata)
                                self.logger.debug(record.prettyStr())
                                self.queue.put(record)
                            except ValueError:
                                self.logger.error('Got malformed record')
                        elif byte == 'E':
                            msg=self.datalogger.readline()
                            self.logger.error(msg)
                        elif byte == '#':
                            msg=self.datalogger.readline()
                            self.logger.debug(msg)
                        else:
                            pass
                except SerialException:
                    pass
                except OSError:
                    pass
                except IOError:
                    pass
