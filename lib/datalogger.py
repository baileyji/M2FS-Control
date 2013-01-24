import time, re
from construct import *
import SelectedConnection

class DataloggerStartupException(Exception):
    pass

class Datalogger(SelectedConnection.SelectedSerial):
    """ Datalogger  Controller Class """
    def __init__(self, device):
        """open a threaded serial port connection with the controller
        assert the controller is running the correct version of the code
        """
        self.mode='default'
        self.n_temp_sensors=5
        self.messageHandler=None
        self._have_unfetched_temps=False
        self._have_unfetched_accels=False
        SelectedConnection.SelectedSerial.__init__(self, device, 115200)
    
    def handle_read(self):
        """Read from serial. Call callback"""
        try:
            self.in_buffer += self.connection.read(self.connection.inWaiting())
            if not self.in_buffer:
                raise IOError('Empty read')
        except Exception, err:
            self.handle_error(err)
        if self.mode=='default':
            byteIn=self.in_buffer[0]
            self.in_buffer=self.in_buffer[1:]
            if byteIn not in 't?BE#L':
                self.logger.debug("Out of sync, flushing buffer.")
                self.in_buffer=''
                byteIn=''
            self._setModeAndHandlerFromByte(byteIn)
        if self.mode=='listen4N' and len(self.in_buffer)>0:
            # listen for number of bytes to listen for mode
            self.length_of_incomming_message=ord(self.in_buffer[0])
            self.in_buffer=self.in_buffer[1:]
            #self.logger.debug("listen4N message of length %i" % 
            #    self.length_of_incomming_message)
            self.mode='listenN'
        if self.mode=='listenN' and len(self.in_buffer) >= self.length_of_incomming_message: 
            #listen for N bytes mode
            message_str=self.in_buffer[:self.length_of_incomming_message]
            self.in_buffer=self.in_buffer[self.length_of_incomming_message:]
            #self.logger.debug("Received message of length %i on %s" % 
            #    (self.length_of_incomming_message, self))
            if self.messageHandler:
                callback=self.messageHandler
                self.messageHandler=None
                callback(message_str)
            self.mode='default'
        if self.mode=='listen/n':
            count=self.in_buffer.find('\n')
            if count is not -1:
                self.connection.write('\x23')
                message_str=self.in_buffer[0:count+1]
                self.in_buffer=self.in_buffer[count+1:]
                #self.logger.debug("Received message '%s'" % message_str.encode('string_escape'))
                if self.messageHandler:
                    callback=self.messageHandler
                    self.messageHandler=None
                    callback(message_str[:-1])
                self.mode='default'

    def _setModeAndHandlerFromByte(self, byteIn):
        #self.logger.debug("ByteIn:%s"%byteIn)
        if  byteIn == 't':
            self.send_time_to_datalogger()
        elif byteIn == '?':
            self.connection.write('!')
        elif byteIn == 'B':
            self.length_of_incomming_message=X #TODO
            self.mode=='listenN'
            self.messageHandler=self.receiveBatteryStatus
        elif byteIn == 'E':
            self.mode='listen/n'
            self.messageHandler=self.receiveError
        elif byteIn == '#':
            self.mode='listen/n'
            self.messageHandler=self.receiveDebugMessage
        elif byteIn == 'L':
            self.mode='listen4N'
            #callback must put '#' into out_buffer once message is received
            self.messageHandler=self.receiveLogData
    
    
    def send_time_to_datalogger(self):
        """ send the current time to the datalogger"""
        utime=int(time.time())
        hexutime=hex(utime)[2:].upper()
        s='t'+UBInt32("f").build(utime)
        self.logger.debug('Sending time as %s' % s.encode('string_escape'))
        #this is what it took to send the time in testing, oh if only self.connection.write(s) would work
        self.connection.write(s[0])
        self.connection.write('\x00'+s[1])
        self.connection.write('\x00'+s[2])
        self.connection.write('\x00'+s[3])
        self.connection.write('\x00'+s[4])
        
    def receiveLogData(self, data):
        """ Convert logger data into a nice neat form and sit on it"""
        Acceleration_Record_Length=8+6*32
        Temp_Record_Length=8+4*self.n_temp_sensors
        Combined_Record_Length=Acceleration_Record_Length+4*self.n_temp_sensors
        tempConstruct=StrictRepeater(self.n_temp_sensors,LFloat32("temps"))
        accelConstruct=StrictRepeater(32*3,SLInt16("accel"))
        if len(data)==Combined_Record_Length:
            self._have_unfetched_accels=True
            self._have_unfetched_temps=True
            self.current_temps=tempConstruct.parse(data[0:4*self.n_temp_sensors+1])
            self.current_accels=accelConstruct.parse(data[4*self.n_temp_sensors+1:-8])
            self.most_recent_record_timestamp=(
                ULInt32("foo").parse(data[-8:-4]),
                ULInt32("foo").parse(data[-4:])
                )
            self.accels_timestamp=self.most_recent_record_timestamp
            self.temps_timestamp=self.most_recent_record_timestamp  
        elif len(data)==Acceleration_Record_Length:
            self._have_unfetched_accels=True
            self.current_accels=accelConstruct.parse(data[0:-8])
            self.most_recent_record_timestamp=(
                ULInt32("foo").parse(data[-8:-4]),
                ULInt32("foo").parse(data[-4:])
                )
            self.accels_timestamp=self.most_recent_record_timestamp
        elif len(data)==Temp_Record_Length:
            self._have_unfetched_temps=True
            self.current_temps=tempConstruct.parse(data[0:-8])
            self.most_recent_record_timestamp=(
                ULInt32("foo").parse(data[-8:-4]),
                ULInt32("foo").parse(data[-4:])
                )
            self.temps_timestamp=self.most_recent_record_timestamp
        #NB: to convert accels to Gs and numpy array do:
        # 0.00390625*numpy.array(accels).reshape([32,3])
        #time.strftime("%a, %d %b %Y %H:%M:%S +0000",time.localtime(data.unixtime))
        
    def receiveDebugMessage(self, message):
        """ Process a debugging message from the datalogger"""
        cleanmsg=message.encode('string_escape')
        self.logger.debug("%s: %s" % (self.addr_str(),cleanmsg) )
        
    def receiveError(self, message):
        """ Process an error message from the datalogger"""
        cleanmsg=message.encode('string_escape')
        self.logger.error("%s: %s" % (self.addr_str(),cleanmsg) )
	
    def receiveBatteryStatus(self, message):
        """ Process an error message from the datalogger"""
        cleanmsg=message.encode('string_escape')
        self.logger.info("%s battery at %s" % (self.addr_str(),cleanmsg) )
    
    def have_unfetched_temps(self):
        return self._have_unfetched_temps
    
    def have_unfetched_accels(self):
        return self._have_unfetched_accels

    def fetch_temps(self):
        self._have_unfetched_temps=False
        return (self.temps_timestamp, self.current_temps)

    def fetch_accels(self):
        self._have_unfetched_accels=False
        return (self.accels_timestamp, self.current_accels)
