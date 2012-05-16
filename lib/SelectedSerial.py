import serial, termios
class SelectedSerial():
    def __init__(self, port, baudrate, logger,
                default_message_recieved_callback=None,
                default_message_sent_callback=None):
        self.port=port
        self.baudrate=baudrate
        self.logger=logger
        creation_message='Creating SelectedSerial: '+self.addr_str()
        self.logger.debug(creation_message)
        self.serial=None
        try:
            self.connect()
        except Exception, err:
            self.serial=None
            self.logger.info('Could not connect to %s. %s' % 
                (self.addr_str(),str(err)))
        self.out_buffer=''
        self.in_buffer=''
        self.defaultResponseCallback=default_message_recieved_callback
        self.defaultSentCallback=default_message_sent_callback
        self.responseCallback=self.defaultResponseCallback
        self.sentCallback=self.defaultSentCallback

    def __str__(self):
        if self.isOpen():
            return 'Open SelectedSerial '+self.addr_str()
        else:
            return 'Closed SelectedSerial '+self.addr_str()

    def __getattr__(self, attr):
        return getattr(self.serial, attr)

    def addr_str(self):
        return "%s@%s"%(self.port,self.baudrate)

    def sendMessageBlocking(self, message):
        """ Send a string immediately, appends string terminator if needed"""
        if self.serial==None:
            self.logger.error('Attempting to send %s on %s' % str(self) )
            raise IOError
        if message[-1]==';':
            message=[:-1]+'\n'
        else:
            message+='\n'
        self.serial.flushInput()
        self.serial.write(message)
        self.serial.flush()
        except serial.SerialException, e:
            self.handle_error(e)
            raise IOError
            
    def recieveMessageBlocking(self, nBytes=0, delim=None, timeout=.125):
        """Wait for a response, chops \r & \n off response if present"""
        saved_timeout=self.serial.timeout
        self.serial.timeout=timeout
        try:
            if type(delim)==str:
                response=self.serial.readline(eol=delim)
            else:
                response=self.serial.read(nBytes)
            chop=0
            if len(response) >0 and response[-1] in '\r\n':
                chop=1
            if len(response) > 1 and response[-2] in '\r\n':
                chop=2
            if chop!=0:
                response=response[:-chop]
        except serial.SerialException, e:
            self.handle_error(e)
            raise IOError
        finally:
            self.serial.timeout=saved_timeout
        return response

    def sendMessage(self, message, sentCallback=None, responseCallback=None):
        if self.serial==None:
            self.logger.error('Attempting to send %s on %s' % str(self) )
            raise IOError
        if message=='' or self.out_buffer!='':
            return
        if message[-1] !='\n':
            self.out_buffer=message+'\n'
        else:
            self.out_buffer=message
        if responseCallback is not None:
            self.responseCallback=responseCallback
        if sentCallback is not None:
            self.sentCallback=sentCallback
    
    def connect(self):
        if self.serial is None:
            self.serial=serial.Serial(self.port, baudrate=self.baudrate,
                timeout=self.timeout)
   
    def handle_read(self):
        """Read from serial. Call callback"""
        try:
            # read a chunk from the serial port
            data = self.serial.read(self.serial.inWaiting())
            if data:
                self.in_buffer += data
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
            else:
                # empty read indicates disconnection
                self.logger.error("Empty read, should this happen on serial?.")
                self.handle_disconnect()
        except serial.SerialException, err:
            self.handle_error(str(err))

    def handle_write(self):
        """Write to serial"""
        try:
            if self.out_buffer:
                # write a chunk
                count = self.serial.write(self.out_buffer)
                self.logger.debug('Attempted write "%s", wrote "%s" on %s' %
                    (self.out_buffer.replace('\n','\\n'),
                     self.out_buffer[:count].replace('\n','\\n'),
                     self.addr_str()))
                # and remove the sent data from the buffer
                self.out_buffer = self.out_buffer[count:]
                if self.sentCallback and self.out_buffer=='':
                    callback=self.sentCallback
                    self.sentCallback=self.defaultSentCallback
                    callback(self)
        except serial.SerialException,err:
            self.handle_error(str(err))
            
    def handle_error(self, error=None):
        """Serial connection fails"""
        self.logger.error("Serial error %s on %s." %(error, self.addr_str())
        self.handle_disconnect()
        
    def handle_disconnect(self):
        """Serial gets disconnected"""
        if self.serial is None:
            self.logger.error('Handle_Disconnect called on already disconnected serial port %s'%
            self.addr_str())
            return
        self.logger.info("Port %s disconnecting." % self.addr_str())
        self.out_buffer=''
        self.serial.flushOutput()
        self.serial.flushInput()
        self.serial.close()
        self.serial = None
        if self.responseCallback != None:
            callback=self.responseCallback
            self.responseCallback=self.defaultResponseCallback
            callback(self,'Lost Serial Connection.')
        self.sentCallback=self.defaultSentCallback
    
    def isOpen(self):
        return self.serial is not None and self.serial.isOpen()
        
    def close(self):
        if self.serial is not None:
            self.handle_disconnect()
            
    def do_select_read(self):
        """ Do select for read whenever serial is connected """
        return self.isOpen()
    
    def do_select_write(self):
        """ Do select for write whenever connected & have data """
        return self.isOpen() and self.out_buffer !=''
    
    def do_select_error(self):
        """ Do select for errors when open """
        return self.isOpen()