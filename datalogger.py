import serial, termios, time
from construct import *

class DataloggerStartupException(Exception):
    pass

class Datalogger(SelectedSerial):
    """ Datalogger  Controller Class """
    def __init__(self, portName, logger):
        """open a threaded serial port connection with the controller
        assert the controller is running the correct version of the code
        """
        SelectedSerial.__init__(self, portName, 115200, logger,
            default_message_recieved_callback=
            default_message_sent_callback=
            )
    
    def handle_read(self):
        """Read from serial. Call callback"""
        try:
            self.in_buffer = self.in_buffer + self.serial.read(self.serial.inWaiting())
        except serial.SerialException, err:
            self.handle_error(str(err))
        if in_buffer:
            if self.mode=='default':
                byteIn=self.in_buffer[0]
                in_bufer=in_buffer[1:]
                if  byteIn == 't':
                    self.logger.debug("Telling time to %s"% self)
                    self.send_time_to_datalogger()
                elif byteIn == '?':
                    self.logger.debug("Ping...pong on %s"% self)
                    self.serial.write('!')
                elif byteIn == 'B':
                    self.logger.debug("Battery status incomming on %s"% self)
                    self.length_of_incomming_message=X #TODO
                    self.mode=='listenN'
                    self.responseCallback=receiveBatteryStatus
                elif byteIn == 'E':
                    self.logger.debug("Error message incomming from %s"% self)
                    self.mode='listen/n'
                    self.responseCallback=receiveError
                elif byteIn == '#':
                    self.logger.debug("Debug message incomming from %s"% self)
                    self.mode='listen/n'
                    self.responseCallback=recieveDebugMessage
                elif byteIn == 'L':
                    self.logger.debug("Logger data incomming from %s"% self)
                    mode='listen4N'
                    self.responseCallback=receiveLogData, which must but a '#' into out_buffer once the message is recieved
                else:
                    #likely we somehow got our of sync and should recover TODO
                    pass
            if mode=='listen4N' and len(in_bufer)>0: # listen for number of bytes to listen for mode
                self.length_of_incomming_message=in_buffer[0]
                in_bufer=in_buffer[1:]
                mode='listenN'
            if mode=='listenN' and len(in_buffer) >= self.length_of_incomming_message: #listen for N bytes mode
                message_str=self.in_buffer[:self.length_of_incomming_message]
                self.in_buffer=self.in_buffer[self.length_of_incomming_message:]
                self.logger.debug("Recieved message of length %i on %s" % 
                    (self.length_of_incomming_message, self))
                if self.responseCallback:
                    callback=self.responseCallback
                    self.responseCallback=self.defaultResponseCallback
                    callback(self, message_str)
                mode='default'
            if mode=='listen/n':
                count=self.in_buffer.find('\n')
                if count is not -1:
                    message_str=self.in_buffer[0:count+1]
                    self.in_buffer=self.in_buffer[count+1:]
                    self.logger.debug("Recieved message '%s' on %s" % 
                        (message_str.replace('\n','\\n'), self))
                    if self.responseCallback:
                        callback=self.responseCallback
                        self.responseCallback=self.defaultResponseCallback
                        callback(self, message_str[:-1])
                    mode='default'
        else:
            # empty read indicates disconnection
            self.logger.error("Empty read, should this happen on serial?.")
            self.handle_disconnect()
    
    
    def send_time_to_datalogger(self):
        """ send the current time to the datalogger"""
        utime=int(time.time())
        hexutime=hex(utime)[2:].upper()
        s='t'+UBInt32("f").build(utime)
        self.logger.debug('Sending time as %s' % s)
        #this is what it took to send the time in testing, oh if only self.serial.write(s) would work
        self.serial.write(s[0])
        self.serial.write('\x00'+s[1])
        self.serial.write('\x00'+s[2])
        self.serial.write('\x00'+s[3])
        self.serial.write('\x00'+s[4])
        
    def receiveLogData(self, data):
        """ Convert logger data into a nice neat form and sit on it"""
        record=DataloggerRecord(data)
        timestr=time.strftime("%a, %d %b %Y %H:%M:%S +0000",time.localtime(record.unixtime))
        self.out_buffer='#'

    def receiveDebugMessage(self, message):
        """ Process a debugging message from the datalogger"""
        self.logger.debug("Datalogger %s: %s " % (self,message) )
        
    def receiveError(self, message):
        """ Process an error message from the datalogger"""
        self.logger.error("Datalogger %s: %s " % (self,message) )
	
    def receiveBatteryStatus(self, message):
        """ Process an error message from the datalogger"""
        self.logger.info("Datalogger %s battery at %s " % (self,message) )
