import logging, sys

class ReadError(IOError):
    pass

class WriteError(IOError):
    pass

class ConnectError(IOError):
    pass


class SelectedConnection(object):
    def __init__(self,
                default_message_received_callback=None,
                default_message_sent_callback=None,
                default_message_error_callabck=None):
        """ The sent and response callbacks are called iff a message is sent or recieved. If there is an error they will not be called."""
        self.logger=logging.getLogger('SelectedCon')
        self.defaultResponseCallback=default_message_received_callback
        self.defaultSentCallback=default_message_sent_callback
        self.defaultErrorCallback=default_message_error_callabck
        self.responseCallback=self.defaultResponseCallback
        self.sentCallback=self.defaultSentCallback
        self.errorCallback=self.defaultErrorCallback
        self.out_buffer=''
        self.in_buffer=''
    
    def __str__(self):
        """ String form of connection to make easy status reporting """
        if self.isOpen():
            return 'Open SelectedConnection '+self.addr_str()
        else:
            return 'Closed SelectedConnection '+self.addr_str()
    
    def addr_str(self):
        """ Report connection address. Implemented by subclass """
        pass
        
    def __getattr__(self, attr):
        """ This is used to provide functionality with select """
        return getattr(self.connection, attr)
    
    
    def connect(self):
        """
        Establish the connection.
        
        If a connection is open no action is taken, otherwise the
        implementation specific connect is called, followed by the _postConnect
        function.
        All exceptions are trapped and raised as a ConnectError.
        If an error is raised, the connection is not open.
        """
        if self.isOpen():
            return
        try:
            self.implementationSpecificConnect()
            self._postConnect()
        except Exception, e:
            self.logger.info('Connect failed: %s' % str(e))
            self.connection=None
            raise ConnectError(str(e))

    def isOpen(self):
        """ Returns true if the connection is established. Override in subclass"""
        return false

    def _postConnect(self):
        """
        Called after establishing a connection.
        
        Subclass may implement and throw and exception if the connection
        is in any way unsuitable. Any return values are ignored. Exception text
        will be raised as a connect error.
        """
        pass
    
    def sendMessage(self, message,
                    sentCallback=None,
                    responseCallback=None,
                    errorCallback=None):
        """
        Place the string <message> in the output buffer to be sent next time
        connection is selected.

        It is an error to send a message while there remains data in the output
        buffer. If done a WriteError is raised and the error logged. No other 
        action is taken.

        If the connection is not open, an attempt will be made to establish a 
        connection by the standard procedure. If the connection can not be
        established the errorCallback is called with a failure message else a
        connect error is raised.
        
        If defined, errorCallback will update the curent error callback handler.
        If defined and the message is placed into the output buffer, sentCallback and
        responseCallback will update their respective callback handlers.
        
        If message is not \n terminated a \n will be appended.
        
        """
        if self.out_buffer!='':
            err="Attempting to send %s on non-empty buffer" % message
            err=err.replace('\n','\\n').replace('\r','\\r')
            self.logger.error(err)
            raise WriteError(err)
        if errorCallback is not None:
            self.errorCallback=errorCallback
        try:
            self.connect()
        except ConnectError, err:
            self.connection=None
            err="Unable to send '%s' on %s" % (message, str(self))
            self.handle_error(error=err)
            raise WriteError(err)
        if message=='':
            return
        if message[-1] !='\n':
            message=message+'\n'
        self.out_buffer=message
        if responseCallback is not None:
            self.responseCallback=responseCallback
        if sentCallback is not None:
            self.sentCallback=sentCallback
    
    def sendMessageBlocking(self, message):
        """
        Send the string message immediately.
        
        If the connection is not open, an attempt will be made to establish a
        connection by the standard procedure.
        
        Raises WriteError if message cannot be sent, or is only sent in part.
        
        If message is not \n terminated a \n will be appended.
        """
        try:
            self.connect()
        except ConnectError, err:
            self.connection=None
            err=("Attempted to send '%s' to '%s' but coudn't connect." %
                (message, self.addr_str())).replace('\n','\\n').replace('\r','\\r')
            self.logger.error(err)
            raise WriteError(err)
        if not message:
            return
        if message[-1]!='\n':
            message+='\n'
        try:
            count=self.implementationSpecificBlockingSend(message)
            msg=("Attempted write '%s', wrote '%s' to %s" %
                 (message, message[:count], self.addr_str())
                 ).replace('\n','\\n').replace('\r','\\r')
            self.logger.debug(msg)
            if count !=len(message):
                raise WriteError('Could not send complete message.')
        except WriteError,err:
            self.handle_error(err)
            raise WriteError(str(err))
    
    def receiveMessageBlocking(self, nBytes=0, timeout=None):
        """Wait for a response, chops \r & \n off response if present"""
        try:
            self.connect()
        except ConnectError, err:
            self.connection=None
            err="Attempting to receive on %s" % str(self)
            self.logger.error(err)
            raise ReadError(err)
        try:
            response=self.implementationSpecificBlockingReceive(nBytes, timeout)
            self.logger.debug("BlockingReceive got: '%s'" % 
                response.replace('\n','\\n').replace('\r','\\r'))
            return response.rstrip(' \t\n\r')
        except ReadError, e:
            self.handle_error(e)
            raise e
    
    def handle_error(self, error=''):
        """ Connection fails"""
        err=('ERROR: "%s" on %s.' %
            (str(error).replace('\n','\\n').replace('\r','\\r'), self.addr_str()))
        self.logger.error(err)
        if self.errorCallback !=None:
            callback=self.errorCallback
            self.errorCallback=self.defaultErrorCallback
            callback(self,err)
        self._disconnect()
    
    def _disconnect(self):
        """
        Disconnect, clearing output buffer
        
        Calls _implementationSpecificDisconnect to perform the disconnect.
        Trap and log any exceptions that occur.
        Reset set, received, & error callbacks to their defaults.
        """
        if self.connection is None:
            return
        self.logger.info("%s disconnecting." % self)
        self.out_buffer=''
        try:
            self._implementationSpecificDisconnect()
        except Exception, e:
            self.logger.debug('_implementationSpecificDisconnect caused exception: %s'%str(e))
        self.connection = None
        self.sentCallback=self.defaultSentCallback
        self.responseCallback=self.defaultResponseCallback
        self.errorCallback=self.defaultErrorCallback
    
    def close(self):
        """ Terminate the connection"""
        if self.isOpen():
            self._disconnect()
            
    def do_select_read(self):
        """ Do select for read whenever the connection is open """
        return self.isOpen()
    
    def handle_read(self):
        """Read callback for select"""
        try:
            data = self.implementationSpecificRead()
            self.logger.debug("Handle_Read got: %s" %
                              data.replace('\n','\\n').replace('\r','\\r'))
            self.in_buffer += data
            count=self.in_buffer.find('\n')
            if count is not -1:
                message_str=self.in_buffer[0:count+1]
                self.in_buffer=self.in_buffer[count+1:]
                self.logger.debug("Received message '%s' on %s" % 
                    (message_str.replace('\n','\\n').replace('\r','\\r'), self))
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
                msg=('Attempted write "%s", wrote "%s" on %s' %
                     (self.out_buffer, self.out_buffer[:count],self.addr_str())
                ).replace('\n','\\n').replace('\r','\\r')
                self.logger.debug(msg)
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
    def __init__(self, port, baudrate,
                default_message_received_callback=None,
                default_message_sent_callback=None,
                default_message_error_callabck=None,timeout=None):
                
        SelectedConnection.__init__(self,
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
    
    def implementationSpecificConnect(self):
        self.connection=serial.Serial(self.port, baudrate=self.baudrate,
                timeout=self.timeout)
    
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
            if count!=None:
                return count
            else:
                #assume full message sent
                return len(self.out_buffer)
        except serial.SerialException,err:
            raise WriteError(err)
    
    def _implementationSpecificDisconnect(self):
        """disconnection specific to serial"""
        try:
            self.connection.flushOutput()
            self.connection.flushInput()
            self.connection.close()
        except Exception:
          pass
    
    def isOpen(self):
        return self.connection is not None and self.connection.isOpen()
        
import socket
class SelectedSocket(SelectedConnection):
    def __init__(self, host, port, Live_Socket_To_Use=None,
                default_message_received_callback=None,
                default_message_sent_callback=None,
                default_message_error_callabck=None):
        SelectedConnection.__init__(self,
                default_message_received_callback=default_message_received_callback,
                default_message_sent_callback=default_message_sent_callback,
                default_message_error_callabck=default_message_error_callabck)
        self.host=host
        self.port=port
        creation_message='Creating SelectedSocket: '+self.addr_str()
        if isinstance(Live_Socket_To_Use, socket.socket):
            creation_message+=' with live socket.'
        elif Live_Socket_To_Use:
            raise TypeError("Live_socket_to_use must be a socket")
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
    
    def implementationSpecificConnect(self):
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
    
    def _implementationSpecificDisconnect(self):
        """disconnection specific to socket"""
        try:
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()
        except Exception:
            pass
    
    def isOpen(self):
        return self.connection is not None

