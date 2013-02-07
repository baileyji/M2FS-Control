import time, re, select
from construct import UBInt32, StrictRepeater, LFloat32, SLInt16, ULInt32
from serial import Serial, SerialException
import threading
import Queue
import logging
import logging.handlers
import numpy


LOGGING_LEVEL=logging.ERROR
#Lengths of the message parts in bytes

N_TEMP_SENSORS=5
ECHELLE_INDEX=0
PRISIM_INDEX=1
LORES_INDEX=2


TEMPERATURE_BYTES=4
ACCELERATION_BYTES=2
TIMESTAMP_LENGTH=8
ADXL_FIFO_LENGTH=32
NUM_AXES=3
ACCELS_TO_GEES=0.00390625
ACCEL_RECORD_LENGTH=TIMESTAMP_LENGTH+NUM_AXES*ACCELERATION_BYTES*ADXL_FIFO_LENGTH
TEMP_RECORD_LENGTH=TIMESTAMP_LENGTH + TEMPERATURE_BYTES*N_TEMP_SENSORS
COMPOSITE_RECORD_LENGTH=ACCEL_RECORD_LENGTH+TEMP_RECORD_LENGTH-TIMESTAMP_LENGTH



#These are constructs which take the raw binary data for the accelerations or
# temps and parse them into lists of numbers
tempsParser=StrictRepeater(N_TEMP_SENSORS, LFloat32("temps")).parse
accelsParser=StrictRepeater(ADXL_FIFO_LENGTH*NUM_AXES, SLInt16("accel")).parse
unsigned32BitParser=ULInt32("foo").parse


class DataloggerRecord(object):
    """
    A timestamped record containing temperatures and/or accelerations
    
    Initialize with the raw data string (following the L and num bytes sent)
    sent from the datalogger. Throws ValueError if the data does not parse into
    a valid record.
    
    Has the attributes:
    temps - None or a list of floats in the order sent by the datalogger
    accels - None or a numpy 32x3 array of accelerations in Gs with the 
        FIRST?LAST? TODO 
        taken at approximately the timestamp and the remainder preceeding at
        intervals of 40 ms. 3 element dimension consists of x, y, & z axes.
    unixtime - The unixtime the of the record
    millis - The number of miliseconds into the day
    
    Implements the magic function __str__ 
    """
    def __init__(self, data):
        if len(data)==COMPOSITE_RECORD_LENGTH:
            self.temps=tempsParser(data[0:4*N_TEMP_SENSORS+1])
            self.accels=accelsParser(data[0:-8])
        elif len(data)==ACCEL_RECORD_LENGTH:
            self.temps=None
            self.accels=accelsParser(data[0:-8])
        elif len(data)==TEMP_RECORD_LENGTH:
            self.temps=tempsParser(data[0:-8])
            self.accels=None
        else:
            raise ValueError("Malformed Record: '%s'" %
                             data.encode('string_escape'))
        if self.accels:
            self.accels=ACCELS_TO_GEES*numpy.array(self.accels).reshape([32,3])
        self.unixtime=float(unsigned32BitParser(data[-8:-4]))
        self.millis=unsigned32BitParser(data[-4:])
        self.unixtime+=float(self.millis)/1000 % 86400

    def __str__(self):
        if not self.temps:
            string="Accel Record"
        elif not self.accels:
            string="Temps Record"
        else:
            string="Combo Record"
        timestr=time.strftime("%a, %d %b %Y %H:%M:%S",
                              time.localtime(self.unixtime))
        return ' '.join([string,timestr,str(self.millis/1000.0)])

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
        #self.logger.debug('Sending time as %s' % s.encode('string_escape'))
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
    def __init__(self, device, queue):
        """
        Start a new thread to capture temperature and accelerometer data from
        an M2FS datalogger on device. Place data into the Queue passed in Queue.
        """
        threading.Thread.__init__(self)
        self.daemon=True
        self.queue=queue
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
                                    [self.datalogger], [self.datalogger], .5)
                    if reader:
                        byte=self.datalogger.read(1)
                        if byte == 't':
                            self.datalogger.telltime()
                            self.logger.debug('Handled time query')
                        elif byte == 'L':
                            logdata=self.datalogger.readLogData()
                            self.datalogger.write('#')
                            record=DataloggerRecord(logdata)
                            self.logger.debug(str(record))
                            self.queue.put(record)
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
