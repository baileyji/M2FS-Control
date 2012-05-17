class SelectedConnection():
    def __init__(self, logger=None,
                default_message_recieved_callback=None,
                default_message_sent_callback=None,
                default_message_error_callabck=None):

        self.logger=logger
        self.defaultResponseCallback=default_message_recieved_callback
        self.defaultSentCallback=default_message_sent_callback
        self.defaultErrorCallback=default_message_error_callabck
        self.responseCallback=self.defaultResponseCallback
        self.sentCallback=self.defaultSentCallback
        self.errorCallback=self.defaultErrorCallback
        self.out_buffer=''
        self.in_buffer=''


    def __str__(self):
        if self.isOpen():
            return 'Open SelectedConnection '+self.addr_str()
        else:
            return 'Closed SelectedConnection '+self.addr_str()

    def addr_str(self):
        """ Implemented by subclass """
        pass

    def trimNewlineFromString(self, string):
        """ remove \r\n \r\r \n\n \n\r \n \r from end of string. """
        chop=0
        if len(string) >0 and string[-1] in '\r\n':
            chop=1
        if len(string) > 1 and string[-2] in '\r\n':
            chop=2
        if chop!=0:
            return string[:-chop]
        else:
            return string
    
    def sendMessage(self, message, sentCallback=None, responseCallback=None, errorCallback=None):
        if self.socket==None:
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
        if errorCallback is not None:
            self.errorCallback=errorCallback
    
    def handle_error(self, error=None):
        """ Connection fails"""
        self.logger.error("Error %s on %s." %(error, self.addr_str()))
        self.handle_disconnect()
                
    def close(self):
        if self.isOpen():
            self.handle_disconnect()
            
    def do_select_read(self):
        """ Do select for read whenever the connection is open """
        return self.isOpen()
    
    def do_select_write(self):
        """ Do select for write whenever the connection is open & have data """
        return self.isOpen() and self.out_buffer !=''
    
    def do_select_error(self):
        """ Do select for errors when the connection is open"""
        return self.isOpen()
        
        
import serial, termios
class SelectedSerial(SelectedConnection):
    def __init__(self, port, baudrate, logger,
                default_message_recieved_callback=None,
                default_message_sent_callback=None,
                default_message_error_callabck=None):
                
        SelectedConnection.__init__(self, logger=logger,
                default_message_recieved_callback=default_message_recieved_callback,
                default_message_sent_callback=default_message_sent_callback,
                default_message_error_callabck=default_message_error_callabck)
        self.port=port
        self.baudrate=baudrate
        self.timeout=None
        creation_message='Creating SelectedSerial: '+self.addr_str()
        self.logger.debug(creation_message)
        self.serial=None
        try:
            self.connect()
        except serial.SerialException, err:
            self.serial=None
            self.logger.info('Could not connect to %s. %s' % 
                (self.addr_str(),str(err)))

    def __getattr__(self, attr):
        return getattr(self.serial, attr)

    def addr_str(self):
        return "%s@%s"%(self.port,self.baudrate)

    def sendMessageBlocking(self, message):
        """ Send a string immediately, appends string terminator if needed"""
        if not self.isOpen():
            self.logger.error('Attempting to send %s on %s' % str(self) )
            raise IOError
        if not message:
            return
        if message[-1]=='\n':
            message+='\n'
        self.serial.flushInput()
        self.serial.write(message)
        self.serial.flush()
        except serial.SerialException, e:
            self.handle_error(e)
            raise IOError
            
    def recieveMessageBlocking(self, nBytes=0, delim=None, timeout=.125):
        """Wait for a response, chops \r & \n off response if present"""
        if not self.isOpen():
            self.logger.error('Attempting to receive on %s' % str(self) )
            raise IOError
        saved_timeout=self.serial.timeout
        self.serial.timeout=timeout
        try:
            if type(delim)==str:
                response=self.serial.readline(eol=delim)
            else:
                response=self.serial.read(nBytes)
            response=trimNewlineFromString(response)
        except serial.SerialException, e:
            self.handle_error(e)
            raise IOError
        finally:
            if self.serial !=None:
                self.serial.timeout=saved_timeout
        return response
    
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
        
import socket
class SelectedSocket(SelectedConnection):
    def __init__(self, host, port, logger, Live_Socket_To_Use=None,
                default_message_recieved_callback=None,
                default_message_sent_callback=None,
                default_message_error_callabck=None):
        SelectedConnection.__init__(self, logger=logger,
                default_message_recieved_callback=default_message_recieved_callback,
                default_message_sent_callback=default_message_sent_callback,
                default_message_error_callabck=default_message_error_callabck)
        self.host=host
        self.port=port
        creation_message='Creating SelectedSocket: '+self.addr_str()
        if Live_Socket_To_Use:
            creation_message+=' with live socket.'
        self.logger.debug(creation_message)
        if Live_Socket_To_Use:
            self.socket=Live_Socket_To_Use
        else:
            self.socket=None
            try:
                self.connect()
            except socket.error, err:
                self.socket=None
                self.logger.info('Could not connect to %s. %s' % 
                    (self.addr_str(),str(err)))
    
    def __getattr__(self, attr):
        return getattr(self.socket, attr)
    
    def addr_str(self):
        return "%s:%s"%(self.host,self.port)
    
    def sendMessageBlocking(self, message):
        """ Send a string immediately, appends string terminator if needed"""
        if not self.isOpen():
            self.logger.error('Attempting to send %s on %s' % str(self) )
            raise IOError
        if not message:
            return
        if message[-1]!='\n':
            message+='\n'
        try:
            count = self.socket.send(self.out_buffer)
            self.logger.debug('Attempted write "%s", wrote "%s" on %s' %
                    (message.replace('\n','\\n'),
                     message[:count].replace('\n','\\n'),
                     self.addr_str()))
            # and remove the sent data from the buffer
            if count !=len(message):
                raise socket.error('Could not send full message on blocking request.')
        except socket.error,err:
            self.handle_error(str(err))
            raise IOError
            
    def recieveMessageBlocking(self, nBytes=1024, timeout=.125):
        """Wait for a response, chops \r & \n off response if present"""
        if not self.isOpen():
            self.logger.error('Attempting to receive on %s' % str(self) )
            raise IOError
        if nBytes==0:
            return ''
        saved_timeout=self.socket.gettimeout()
        self.socket.settimeout(timeout)
        try:
            response=self.socket.recv(nBytes)
            response=self.trimNewlineFromString(response)
        except socket.timeout:
            return ''
        except socket.error, e:
            self.handle_error(e)
            raise IOError
        finally:
            if self.socket !=None:
                self.socket.settimeout(saved_timeout)
        return response

      
    def connect(self):
        if self.socket is None:
            thesocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            thesocket.connect((self.host, self.port))
            thesocket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            thesocket.setblocking(0)
            self.socket=thesocket
   
    def handle_read(self):
        """Read from socket. Call callback"""
        try:
            # read a chunk from the serial port
            data = self.socket.recv(1024)
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
                self.logger.error("Empty read, socket %s:%i dead."%(self.host,self.port))
                self.handle_disconnect()
        except socket.error, err:
            self.handle_error(str(err))

    def handle_write(self):
        """Write to socket"""
        try:
            if self.out_buffer:
                # write a chunk
                count = self.socket.send(self.out_buffer)
                self.logger.debug('Attempted write "%s", wrote "%s" on %s:%s' %
                    (self.out_buffer.replace('\n','\\n'),
                     self.out_buffer[:count].replace('\n','\\n'),
                     self.host,self.port))
                # and remove the sent data from the buffer
                self.out_buffer = self.out_buffer[count:]
                if self.sentCallback and self.out_buffer=='':
                    callback=self.sentCallback
                    self.sentCallback=self.defaultSentCallback
                    callback(self)
        except socket.error,err:
            self.handle_error(str(err))
    
    def handle_disconnect(self):
        """Socket gets disconnected"""
        if self.socket is None:
            self.logger.error('Handle_Disconnect called on already disconnected socket %s:%s'%
            (self.host,self.port))
            return
        self.logger.info("Socket %s:%s disconnecting." %(self.host,self.port))
        self.out_buffer=''
        self.socket.close()
        self.socket = None
        self.sentCallback=self.defaultSentCallback
        if self.errorCallback !=None:
            callback=self.errorCallback
            self.errorCallback=self.defaultErrorCallback
            callback(self,'Lost Socket Connection.')
        elif self.responseCallback != None:
            callback=self.responseCallback
            self.responseCallback=self.defaultResponseCallback
            callback(self,'Lost Socket Connection.')
    
    def isOpen(self):
        return self.socket is not None

