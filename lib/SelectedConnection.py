class ReadError(IOError):
    pass

class WriteError(IOError):
    pass

class ConnectError(IOError):
    pass

class SelectedConnection():
    def __init__(self, logger=None,
                default_message_recieved_callback=None,
                default_message_received_callback=None,
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
        
    def __getattr__(self, attr):
        return getattr(self.connection, attr)

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
        if self.connection==None:
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
        
    def handle_disconnect(self):
        """Disconnect"""
        if self.connection is None:
            self.logger.error('Handle_Disconnect called on already disconnected %s' % self)
            return
        self.logger.info("%s disconnecting." % self)
        self.out_buffer=''
        self.implementationSpecificDisconnect()
        self.connection = None
        self.sentCallback=self.defaultSentCallback
        if self.errorCallback !=None:
            callback=self.errorCallback
            self.errorCallback=self.defaultErrorCallback
            callback(self,'Lost Connection.')
        elif self.responseCallback != None:
            callback=self.responseCallback
            self.responseCallback=self.defaultResponseCallback
            callback(self,'Lost Connection.')
    
    def close(self):
        if self.isOpen():
            self.handle_disconnect()
            
    def do_select_read(self):
        """ Do select for read whenever the connection is open """
        return self.isOpen()
    
    def handle_read(self):
        """Read callback for select"""
        try:
            data = self.implementationSpecificRead()
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
        except ReadError, err:
            self.handle_error(err)
    
    def do_select_write(self):
        """ Do select for write whenever the connection is open & have data """
        return self.isOpen() and self.out_buffer !=''
        
    
    def handle_write(self):
        """Write callback for select"""
        try:
            if self.out_buffer:
                # write a chunk
                count = self.implementationSpecificWrite(self.out_buffer)
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
        except WriteError,err:
            self.handle_error(str(err))
    
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
        self.connection=None
        try:
            self.connect()
        except serial.SerialException, err:
            self.connection=None
            self.logger.info('Could not connect to %s. %s' % 
                (self.addr_str(),str(err)))

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
        self.connection.flushInput()
        self.connection.write(message)
        self.connection.flush()
        except serial.SerialException, e:
            self.handle_error(e)
            raise IOError
            
    def recieveMessageBlocking(self, nBytes=0, delim=None, timeout=.125):
        """Wait for a response, chops \r & \n off response if present"""
        if not self.isOpen():
            self.logger.error('Attempting to receive on %s' % str(self) )
            raise IOError
        saved_timeout=self.connection.timeout
        self.connection.timeout=timeout
        try:
            if type(delim)==str:
                response=self.connection.readline(eol=delim)
            else:
                response=self.connection.read(nBytes)
            response=trimNewlineFromString(response)
        except serial.SerialException, e:
            self.handle_error(e)
            raise IOError
        finally:
            if self.connection !=None:
                self.connection.timeout=saved_timeout
        return response
    
    def connect(self):
        if self.connection is None:
            try:
                self.connection=serial.Serial(self.port, baudrate=self.baudrate,
                    timeout=self.timeout)
            except Exception, e:
                raise ConnectError(e)
            finally:
                self.connection=None
    
    def implementationSpecificRead(self):
        """ Perform a device specific read, Rais ReadError if no data or any error """
        try:
            data=self.connection.read(self.connection.inWaiting())
            if not data:
                raise ReadError("Unexpectedly empty read")
            return data
        except serial.SerialException, err:
            raise ReadError(err)

    def implementationSpecificWrite(self, data):
        """ Perform a device specific read, Raise WriteError if no data or any error """
        try:
            count = self.connection.write(self.out_buffer)
            return count
        except serial.SerialException,err:
            raise WriteError(err)
    
    def implementationSpecificDisconnect(self):
        """disconnection specific to serial"""
        self.connection.flushOutput()
        self.connection.flushInput()
        self.connection.close()
    
    def isOpen(self):
        return self.connection is not None and self.connection.isOpen()
        
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
            self.connection=Live_Socket_To_Use
        else:
            self.connection=None
            try:
                self.connect()
            except socket.error, err:
                self.connection=None
                self.logger.info('Could not connect to %s. %s' % 
                    (self.addr_str(),str(err)))
    
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
            count = self.connection.send(self.out_buffer)
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
        saved_timeout=self.connection.gettimeout()
        self.connection.settimeout(timeout)
        try:
            response=self.connection.recv(nBytes)
            response=self.trimNewlineFromString(response)
        except socket.timeout:
            return ''
        except socket.error, e:
            self.handle_error(e)
            raise IOError
        finally:
            if self.connection !=None:
                self.connection.settimeout(saved_timeout)
        return response

    def connect(self):
        if self.connection is None:
            thesocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            thesocket.connect((self.host, self.port))
            thesocket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            thesocket.setblocking(0)
            self.connection=thesocket
   
    def implementationSpecificRead(self):
        """ Perform a device specific read, Raise ReadError if no data or any error """
        try:
            data=self.connection.recv(1024)
            if not data:
                raise ReadError("Unexpectedly empty read")
            return data
        except socket.error, err:
            raise ReadError(err)

    def implementationSpecificWrite(self, data):
        """ Perform a device specific read, Raise WriteError if no data or any error """
        try:
            count = self.connection.send(self.out_buffer)
            return count
        except socket.error, err:
            raise WriteError(err)
    
    def implementationSpecificDisconnect(self):
        """disconnection specific to socket"""
        self.connection.close()
    
    def isOpen(self):
        return self.connection is not None

