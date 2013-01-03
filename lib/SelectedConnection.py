import logging, sys

class ReadError(IOError):
    pass

class WriteError(IOError):
    pass

class ConnectError(IOError):
    pass


class SelectedConnection(object):
    """
    The SelectedConnection class
    
    This class is intended to create a common interface for all selectable
    connections used in the M2FS control software. At present that includes 
    only sockets and serial connections.
    
    The abstraction is incomplete as the SelectedConnection can not be 
    instantiated directly, rather an instance on SelectedSocket or 
    SelectedSerial must be created. I'd like to finish this abstraction.
    """
    def __init__(self,
                default_message_received_callback=None,
                default_message_sent_callback=None,
                default_message_error_callabck=None):
        """ 
        Instantiate a SelectedConnection.
        
        Optionally register default callbacks for message sends, receives, and 
        errors.
        
        The received callback is called when a complete message is recieved with
        the connection (that is, self) and the message received as arguments.
        See handle_read for further details.
        
        The sent callback is called when all of the requested message has been 
        sent. It is called with the connection (that is, self) as argument.
        the connection (that is, self) and the message received as arguments.
        See handle_write for further details.
        
        The error callback is called when handle_error is called which will
        occur if handle_read or receiveMessageBlocking has a read error,
        handle_write or sendMessageBlocking has a write error, or handle_error 
        is called directly (e.g. by a driver routine after select indicates an
        error).
        
        The sent and received callbacks are called iff a message is sent or 
        recieved. If there is an error they will not be called. """
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
        """
        If class does not have attribute fetch is from the connection
        
        This provides compatibility with select
        """
        return getattr(self.connection, attr)
    
    def connect(self):
        """
        Establish the connection.
        
        If a connection is open no action is taken, otherwise the
        implementation specific connect is called, followed by the _postConnect
        function.
        All exceptions are trapped and raised as a ConnectError.
        If an error is raised, the connection shall not be considered open and
        implementations isOpen should return False.
        
        """
        if self.isOpen():
            return
        try:
            self._implementationSpecificConnect()
            self._postConnect()
        except Exception, e:
            self.logger.info('Connect failed: %s' % str(e))
            self.connection=None
            raise ConnectError(str(e))
    
    def isOpen(self):
        """ 
        Return true iff the connection is established. 
        
        Override in subclass
        """
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
        Place <message> in the output buffer. Null strings are quietly ignored.
        
        Message will be be sent next time connection is selected.
        
        The responseCallback will be called upon receipt of the first
        subsequent message with self and the messaage as arguments.
        
        The sentCallback will be called when the message is transmitted in full
        with self as the only argument.
        
        The errorCallback will only be called if an error occurs. It is called
        with self, and an error message starting with 'ERROR:' as arguments.

        It is an error to send a message while there remains data in the output
        buffer. If done and an errorCallback is passed that callback is called.
        If no error callback is passed a WriteError is raised regardless of the 
        presence of a defaultErrorHandler, which is not called. The thinking 
        here is that code may be anticipating calls to the defaulterrorhandler 
        comming from the previous send attempt.
        
        If the connection is not open, an attempt will be made to establish a 
        connection by the standard procedure. If the connection can not be
        established the errorCallback is called with a failure message. A write
        WriteError is raised if there is no defaultErrorCallback and
        errorCallback.
        
        If defined, errorCallback will be used for the next error or until
        disconnect at which time the defaultErrorCallback will be restored. If
        out_buffer was not empty self.errorCallback is not updated.
        Perhaps the error callback should be replaced with the default if the
        message is sucessfully sent as well. TODO: Consider revising 
        
        If message is not \n terminated a \n will be appended.
        
        Finally, the message is placed in the output buffer and the response 
        and message sent callbacks are updated if defined. They revert to their
        defaults at disconnect. The sent callback will also revert to default
        after the message is sucessfully sent, similarly the recieved after
        the message is received.
        """
        if self.out_buffer!='':
            err="Attempting to send %s on non-empty buffer" % message
            err=err.replace('\n','\\n').replace('\r','\\r')
            self.logger.error(err)
            if errorCallback is not None:
                errorCallback(self, 'ERROR: '+err)
            else
                raise WriteError(err)
        if errorCallback is not None:
            self.errorCallback=errorCallback
        try:
            self.connect()
        except ConnectError, err:
            err="Unable to send '%s'" % message
            #Query state because calling resets to defaul, which may be none
            doRaise=self.errorCallback is None
            self.handle_error(error=err)
            if doRaise:
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
        
        In the message is empty noting is trasmitted. If message is not \n
        terminated a \n will be appended.
        
        
        If connected, but message cannot be sent or is only sent in part 
        handle_error is called (which implies self.errorCallback if set) and
        WriteError is raised. This is probably NOT is ideal behavior, probably
        should just raise the WriteError. TODO: think/test 
        """
        try:
            self.connect()
        except ConnectError, err:
            err=("Attempted to send '%s' to '%s' but coudn't connect." %
                (message, self.addr_str())).replace('\n','\\n').replace('\r','\\r')
            self.logger.error(err)
            raise WriteError(err)
        if not message:
            return
        if message[-1]!='\n':
            message+='\n'
        try:
            count=self._implementationSpecificBlockingSend(message)
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
        """
        Wait for a response, chops whitespace and \r & \n off end of response.
        
        Timeout sets a custom timeout to wait in seconds. Float ok.
        npytes sets the number of bytes for which to wait. See 
        _implementationSpecificBlockingReceive for details.
        
        If the connection is not open, an attempt will be made to establish a
        connection by the standard procedure. If it fails a ReadError is raised.
        
        If _implementationSpecificBlockingReceive raises a ReadError handle_error
        is called (which implies self.errorCallback if set) and ReadeError is
        raised. This is probably NOT is ideal behavior, probably
        should just raise the ReadRrror. TODO: think/test
        """
        try:
            self.connect()
        except ConnectError, err:
            err="Attempting to receive on %s" % str(self)
            self.logger.error(err)
            raise ReadError(err)
        try:
            response=self._implementationSpecificBlockingReceive(nBytes, timeout)
            self.logger.debug("BlockingReceive got: '%s'" % 
                response.replace('\n','\\n').replace('\r','\\r'))
            return response.rstrip(' \t\n\r')
        except ReadError, e:
            self.handle_error(e)
            raise e
    
    def handle_error(self, error=''):
        """
        Handler for select on errors. Also used internally.
        
        error is a string describing the error.
        
        Log Error.
        If an errorCallback is defined, call it with a string describing what
        happened and set errorCallback to defaultErrorCallback
        Close the connection via _disconnect.
        """
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
        """ Terminate the connection """
        if self.isOpen():
            self._disconnect()
    
    def do_select_read(self):
        """ 
        Return true if select should check if conncection is ready be read.
        
        Do select for read whenever the connection is open.
        """
        return self.isOpen()
    
    def handle_read(self):
        """
        Read callback for select
        
        Read with _implementationSpecificRead, appending data to in_buffer
        If '\n' is in the in_buffer leftstrip the in_buffer through the first
        '/n'
        Then call the responseCallback (if defined) with the stripped data, 
        excluding the '\n'.
        Reset responseCallback to the default
        
        If a ReadError is encountered, call error_handler
        """
        try:
            data = self._implementationSpecificRead()
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
        """
        Return true if select should check if conncection is ready for writing.
        
        Do select for write whenever the connection is open & out_buffer is not
        empty.
        """
        return self.isOpen() and self.out_buffer !=''
    
    def handle_write(self):
        """
        Write callback for select
        
        Do nothing if no data to send
        
        Attempt to write all of out_buffer with _implementationSpecificWrite
        If only part of buffer is sent, remove it from the buffer and move on.
        If all of the buffer is sent and sentCallback is defined, call it with
        self as the argument.
        
        If a WriteError is encountered, call error_handler
        """
        try:
            if self.out_buffer:
                # write a chunk
                count = self._implementationSpecificWrite(self.out_buffer)
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
        """ 
        Return true if select should check for errors on the connection.
        
        Do select for errors when the connection is open
        """
        return self.isOpen()


import serial, termios
class SelectedSerial(SelectedConnection):
    """ Serial implementation of SelectedConnection """
    def __init__(self, port, baudrate,
                default_message_received_callback=None,
                default_message_sent_callback=None,
                default_message_error_callabck=None,timeout=None):
        """
        Create a new instance
        
        The connection address is defined by port (a serial device path) and
        baudrate.
        
        A default timeout may be set for blocking receives.
        
        An attempt to connect to the device is made, however errors are merely 
        logged as information. The device could be unplugged or otherwise 
        temporarily unavailable.
        """
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
            self.logger.info('Could not connect to %s. %s' %
                (self.addr_str(),str(err)))
    
    def addr_str(self):
        """ Report connection address. """
        return "%s@%s"%(self.port,self.baudrate)
    
    def _implementationSpecificBlockingSend(self, message):
        """
        Send message over serial, returning number of bytes sent.
        
        Assume full message sent, as no way to tell. Raise WriteError if fail.
        """
        try:
            self.connection.write(message)
            self.connection.flush()
            return len(message)
        except serial.SerialException, e:
            raise WriteError(str(e))
    
    def _implementationSpecificBlockingReceive(self, nBytes, timeout=None):
        """
        Receive a message of nbytes length over serial, waiting timemout sec.
        
        If timeout is a number it is used as the timeout for this receive only
        Otherwise the default timeout is used. If no default timeout was defined
        125 ms is used. A timout of 0 will block until (if ever) the data 
        arrives.
        
        If nBytes is 0 then listen until we get a '/n' or the timeout occurs.
        
        If a serial exception occurs raise ReadError.
        """
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
    
    def _implementationSpecificConnect(self):
        """ Open a serial connection to self.port @ self.baudrate """ 
        self.connection=serial.Serial(self.port, baudrate=self.baudrate,
                timeout=self.timeout)
    
    def _implementationSpecificRead(self):
        """
        Perform a device specific read, raise ReadError if any error
        
        Read and return all the data in waiting.
        """
        try:
            data=self.connection.read(self.connection.inWaiting())
            if not data:
                raise ReadError("Unexpectedly empty read")
            return data
        except serial.SerialException, err:
            raise ReadError(err)
        except IOError, err:
            raise ReadError(err)
    
    def _implementationSpecificWrite(self, data):
        """
        Write data to serial connection, returning the number of bytes written.
        
        If the version of pySerial doesn't support returning the number of bytes
        written assume all the data was transmitted.
        
        If any serial errors raise WriteError
        """
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
        """ Disconnect the serial connection """
        try:
            self.connection.flushOutput()
            self.connection.flushInput()
            self.connection.close()
        except Exception:
          pass
    
    def isOpen(self):
        """
        Return true if the connection is considered open.
        
        The connection is considered open if it exists and pySerial
        reports it as open.
        """
        return self.connection is not None and self.connection.isOpen()


import socket
class SelectedSocket(SelectedConnection):
    """ Socket implementation of SelectedConnection """
    def __init__(self, host, port, Live_Socket_To_Use=None,
                default_message_received_callback=None,
                default_message_sent_callback=None,
                default_message_error_callabck=None):
        """
        Create a new instance
        
        The connection address is defined by host and port number.
        
        A live socket may be passed if a connection has already been 
        established.
        
        An attempt to connect to the device is made, however errors are merely 
        logged as information. The device could be unplugged or otherwise 
        temporarily unavailable. The attempt is not performed if a live socket
        is given.
        """
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
                self.logger.info('Could not connect to %s. %s' % 
                    (self.addr_str(),str(err)))
    
    def addr_str(self):
        """ Report connection address. """
        return "%s:%s"%(self.host,self.port)
    
    def _implementationSpecificBlockingSend(self, message):
        """
        Send message over socket, returning number of bytes sent.
        
        Raise WriteError if an error occurs.
        """
        try:
            count = self.connection.send(message)
            return count
        except socket.error,err:
            raise WriteError(str(err))
    
    def _implementationSpecificBlockingReceive(self, nBytes, timeout=None):
        """
        Receive a message of nbytes length over a socket, waiting timemout sec.
        
        Returns the bytes received, if any.
        
        If timeout is a number it is used as the timeout for this receive only
        Otherwise the default timeout is used. If no default timeout was defined
        125 ms is used. A timout of 0 will block until (if ever) the data 
        arrives.
        
        If nBytes is 0 then read 1024 bytes (sokects don't support readline)
        or the timeout occurs.
        
        If a socket error occurs raise ReadError.
        """
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
    
    def _implementationSpecificConnect(self):
        """ Open a nonblocking socket connection to self.host on self.port """ 
        thesocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        thesocket.connect((self.host, self.port))
        thesocket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        thesocket.setblocking(0)
        self.connection=thesocket
   
    def _implementationSpecificRead(self):
        """
        Try reading 1024 bytes from the socket.
       
        Since socket is nonblocking it will return with only the bytes available
        Raise ReadError if socket error or no data received (select will only 
        indicate a read if data is available) 
        """
        try:
            data=self.connection.recv(1024)
            if not data:
                raise ReadError("Unexpectedly empty read")
            return data
        except socket.error, err:
            raise ReadError(err)
    
    def _implementationSpecificWrite(self, data):
        """
        Write data out over the socket, returning the number of bytes written.
        
        If any socket errors raise WriteError
        """
        try:
            count = self.connection.send(self.out_buffer)
            return count
        except socket.error, err:
            raise WriteError(err)
    
    def _implementationSpecificDisconnect(self):
        """
        Disconnect the socket
        
        I think I'm doing this right.
        """
        try:
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()
        except Exception:
            pass
    
    def isOpen(self):
        """
        Return true if the connection is considered open.
        
        The connection is considered open if it exists.
        """
        return self.connection is not None

