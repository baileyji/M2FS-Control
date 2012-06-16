class ReadError(IOError):
    pass

class WriteError(IOError):
    pass

class ConnectError(IOError):
    pass

class SelectedConnection(object):
    def __init__(self, logger=None,
                default_message_received_callback=None,
                default_message_sent_callback=None,
                default_message_error_callabck=None):

        self.logger=logger
        self.defaultResponseCallback=default_message_received_callback
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

    def trimReceivedString(self, string):
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
        if not self.isOpen():
            try:
                self.connect()
            except ConnectError, err:
                self.connection=None
                err="Attempting to send '%s' on '%s'" % (message, str(self))
                self.logger.error(err)
                raise IOError(err)
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
    
    def sendMessageBlocking(self, message):
        """ Send a string immediately, appends string terminator if needed"""
        if not self.isOpen():
            try:
                self.connect()
            except ConnectError, err:
                self.connection=None
                err="Attempted to send '%s' to '%s' but coudn't connect." % (message, self.addr_str())
                self.logger.error(err)
                raise IOError(err)
        if not message:
            return
        if message[-1]!='\n':
            message+='\n'
        try:
            count=self.implementationSpecificBlockingSend(message)
            self.logger.debug("Attempted write '%s', wrote '%s' to %s" %
                    (message.replace('\n','\\n').replace('\r','\\r'),
                     message[:count].replace('\n','\\n').replace('\r','\\r'),
                     self.addr_str()))
            if count !=len(message):
                raise WriteError('Could not send complete message.')
        except WriteError,err:
            self.handle_error(err)
            raise WriteError(str(err))
    
    def receiveMessageBlocking(self, nBytes=0, timeout=None):
        """Wait for a response, chops \r & \n off response if present"""
        if not self.isOpen():
            try:
                self.connect()
            except ConnectError, err:
                self.connection=None
                err="Attempting to receive %s" % str(self)
                self.logger.error(err)
                raise IOError(err)
        try:
            response=self.implementationSpecificBlockingReceive(nBytes, timeout)
            self.logger.debug("BlockingReceive got: %s" % 
                response.replace('\n','\\n').replace('\r','\\r'))
            return self.trimReceivedString(response)
        except ReadError, e:
            self.handle_error(e)
            raise e
    
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
        try:
            self.implementationSpecificDisconnect()
        except Exception, e:
            self.logger.debug('implementationSpecificDisconnect caused exception: %s'%str(e))
        self.connection = None
        self.sentCallback=self.defaultSentCallback
        if self.errorCallback !=None:
            callback=self.errorCallback
            self.errorCallback=self.defaultErrorCallback
            callback(self,'Lost Connection %s'%str(self))
        elif self.responseCallback != None:
            callback=self.responseCallback
            self.responseCallback=self.defaultResponseCallback
            callback(self,'Lost Connection %s'%str(self))
    
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
            self.logger.debug("Handle_Read got: %s" % data.replace('\n','\\n'))
            self.in_buffer += data
            count=self.in_buffer.find('\n')
            if count is not -1:
                message_str=self.in_buffer[0:count+1]
                self.in_buffer=self.in_buffer[count+1:]
                self.logger.debug("Received message '%s' on %s" % 
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
                default_message_received_callback=None,
                default_message_sent_callback=None,
                default_message_error_callabck=None,timeout=None):
                
        SelectedConnection.__init__(self, logger=logger,
                default_message_received_callback=default_message_received_callback,
                default_message_sent_callback=default_message_sent_callback,
                default_message_error_callabck=default_message_error_callabck)
        self.port=port
        self.baudrate=baudrate
        self.timeout=timeout
        creation_message='Creating SelectedSerial: '+self.addr_str()
        self.logger.debug(creation_message)
        self.connection=None
        try:
            self.connect()
        except ConnectError, err:
            self.connection=None
            self.logger.info('Could not connect to %s. %s' % 
                (self.addr_str(),str(err)))
    
    def addr_str(self):
        return "%s@%s"%(self.port,self.baudrate)
    
    def implementationSpecificBlockingSend(self, message):
        try:
            self.connection.write(message)
            self.connection.flush()
            return len(message)
        except serial.SerialException, e:
            raise WriteError(str(e))
    
    def implementationSpecificBlockingReceive(self, nBytes, timeout=None):
        saved_timeout=self.connection.timeout
        if type(timeout) in (int,float,long) and timeout>0:
            self.connection.timeout=timeout
        elif saved_timeout==None:
            self.connection.timeout=0.125
        try:
            if nBytes==0:
                response=self.connection.readline()
            else:
                response=self.connection.read(nBytes)
        except serial.SerialException, e:
            raise ReadError(str(e))
        finally:
            if self.connection !=None:
                self.connection.timeout=saved_timeout
        return response
    
    def connect(self):
        if self.connection is not None:
            return
        try:
            self.connection=serial.Serial(self.port, baudrate=self.baudrate,
                timeout=self.timeout)
        except Exception, e:
            self.connection=None
            raise ConnectError(e)
    
    def implementationSpecificRead(self):
        """ Perform a device specific read, Rais ReadError if no data or any error """
        try:
            data=self.connection.read(self.connection.inWaiting())
            if not data:
                raise ReadError("Unexpectedly empty read")
            return data
        except serial.SerialException, err:
            raise ReadError(err)
        except IOError, err:
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
        try:
            self.connection.flushOutput()
            self.connection.flushInput()
            self.connection.close()
        except termios.error:
          pass

    
    def isOpen(self):
        return self.connection is not None and self.connection.isOpen()
        
import socket
class SelectedSocket(SelectedConnection):
    def __init__(self, host, port, logger, Live_Socket_To_Use=None,
                default_message_received_callback=None,
                default_message_sent_callback=None,
                default_message_error_callabck=None):
        SelectedConnection.__init__(self, logger=logger,
                default_message_received_callback=default_message_received_callback,
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
            except ConnectError, err:
                self.connection=None
                self.logger.info('Could not connect to %s. %s' % 
                    (self.addr_str(),str(err)))
    
    def addr_str(self):
        return "%s:%s"%(self.host,self.port)
    
    def implementationSpecificBlockingSend(self, message):
        try:
            count = self.connection.send(message)
            return count
        except socket.error,err:
            raise WriteError(str(err))
    
    def implementationSpecificBlockingReceive(self, nBytes, timeout=None):
        saved_timeout=self.connection.gettimeout()
        if type(timeout) in (int,float,long) and timeout>0:
            self.connection.settimeout(timeout)
        elif saved_timeout==0.0:
            self.connection.settimeout(.125)
        try:
            if nBytes==0:
                #Consider a line to be 1024 bytes
                nBytes=1024
            response=self.connection.recv(nBytes)
        except socket.timeout:
            response=''
        except socket.error, e:
            raise ReadError(str(e))
        finally:
            if self.connection !=None:
                self.connection.settimeout(saved_timeout)
        return response
    
    def connect(self):
        if self.connection is not None:
            return
        try:
            thesocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            thesocket.connect((self.host, self.port))
            thesocket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            thesocket.setblocking(0)
            self.connection=thesocket
        except Exception, e:
            self.connection=None
            raise ConnectError(str(e))
   
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
        self.connection.shutdown(socket.SHUT_RDWR)
        self.connection.close()
    
    def isOpen(self):
        return self.connection is not None

