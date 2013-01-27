import time, re
from construct import UBInt32, StrictRepeater, LFloat32, SLInt16, ULInt32
from serial import Serial, SerialException
import threading
import Queue
import logging
import logging.handlers

HEADER_LENGTH=8
ADXL_FIFO_LENGTH=32
NUM_AXES=3
N_TEMP_SENSORS=5
ACCEL_RECORD_LENGTH=HEADER_LENGTH + 6*ADXL_FIFO_LENGTH
TEMP_RECORD_LENGTH=HEADER_LENGTH + 4*N_TEMP_SENSORS
COMPOSITE_RECORD_LENGTH=ACCEL_RECORD_LENGTH+TEMP_RECORD_LENGTH-HEADER_LENGTH

tempsParser=StrictRepeater(N_TEMP_SENSORS, LFloat32("temps")).parse
accelsParser=StrictRepeater(ADXL_FIFO_LENGTH*NUM_AXES, SLInt16("accel")).parse
unsigned32BitParser=ULInt32("foo").parse


class DataloggerRecord(object):
    def __init__(self, data):
        if len(data)==COMPOSITE_RECORD_LENGTH:
            self.temps=tempsParser(data[0:4*N_TEMP_SENSORS+1])
            self.accels=accelsParser(data[4*N_TEMP_SENSORS+1:-8])
            self.timestamp=(unsigned32BitParser(data[-8:-4]),
                            unsigned32BitParser(data[-4:]))
        elif len(data)==ACCEL_RECORD_LENGTH:
            self.temps=None
            self.accels=accelsParser(data[0:-8])
        elif len(data)==TEMP_RECORD_LENGTH:
            self.temps=tempsParser(data[0:-8])
            self.accels=None
        else:
            raise ValueError("Malformed Record: '%s'" %
                             data.encode('string_escape'))
        self.timestamp=(unsigned32BitParser(data[-8:-4]),
                        unsigned32BitParser(data[-4:]))

    def __str__(self):
        if not self.temps:
            string="Accel Record"
        elif not self.accels:
            string="Temps Record"
        else:
            string="Combo Record"
        timestr=time.strftime("%a, %d %b %Y %H:%M:%S +0000",
                              time.localtime(self.timestamp[0]))
        return ' '.join([string,timestr,str(self.timestamp[1])])

class DataloggerConnection(Serial):
    """ Datalogger Connection Class """
    def __init__(self, device):
        Serial.__init__(self, baudrate=115200)
        self.port=device
        try:
            self.open()
        except SerialException:
            pass
    
    def readLogData(self):
        return self.read(ord(self.read(1)))
    
    def telltime(self):
        """ send the current time to the datalogger"""
        s='t'+UBInt32("f").build(int(time.time()))
        #self.logger.debug('Sending time as %s' % s.encode('string_escape'))
        #this is what it took to send the time in testing,
        # oh if only self.connection.write(s) would work
        self.write(s[0])
        self.write('\x00'+s[1])
        self.write('\x00'+s[2])
        self.write('\x00'+s[3])
        self.write('\x00'+s[4])

class DataloggerListener(threading.Thread):
    def __init__(self, device, queue, testData=None):
        threading.Thread.__init__(self)
        if testData:
            self.testData=list(testData)
        else:
            self.testData=None
        self.daemon=True
        self.queue=queue
        self.datalogger=DataloggerConnection(device)
        self.logger=logging.getLogger('DataloggerListener')
        self.logger.setLevel(logging.DEBUG)
        self.logger.info("Listener started")
    
    def run(self):
        while True:
            if not self.datalogger.isOpen():
                try:
                    #self.logger.debug('Attempting connect %s' % self.datalogger.port)
                    self.datalogger.open()
                except SerialException:
                    time.sleep(1)
                    pass
            if self.testData and len(self.testData)>0:
                i=self.testData[0]
                self.testData=self.testData[1:]
                self.queue.put(('debug',i))
            if self.datalogger.isOpen():
                try:
                    byte=self.datalogger.read(1)
                    if byte == 't':
                        self.datalogger.telltime()
                        self.logger.debug('Handled time query')
                    elif byte == 'L':
                        logdata=self.datalogger.readLogData()
                        self.datalogger.write('#')
                        self.queue.put(('record',logdata))
                    elif byte == 'E':
                        msg=self.datalogger.readline()
                        self.queue.put(('error',msg))
                    elif byte == '#':
                        msg=self.datalogger.readline()
                        self.queue.put(('debug',msg))
                    else:
                        pass
                except SerialException:
                    pass
                except OSError:
                    pass

class Datalogger(object):
    """ Datalogger  Controller Class """
    def __init__(self, device):
        self.logger=logging.getLogger('Datalogger')
        self.logger.setLevel(logging.DEBUG)
        self.queue=Queue.Queue()
        self.dataloggerthread=DataloggerListener(device, self.queue)
             #testData=['test1','test2','test3','test4','test5','test6'])
        self.dataloggerthread.start()
    
    def fetch(self):
        try:
            kind,data = self.queue.get()
            self.queue.task_done()
            if kind =='record':
                self.logger.debug("Returning log data")
                try:
                    record=DataloggerRecord(data)
                except ValueError, e:
                    record=str(e)
                self.logger.debug(record)
                return record
            elif kind =='debug':
                self.logger.debug(data)
            elif kind =='error':
                self.logger.error(data)
        except Queue.Empty:
            pass
        return None