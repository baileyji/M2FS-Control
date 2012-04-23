import socket
class SelectedSocket():
    def __init__(self, host, port, logger, Live_Socket_To_Use=None,
                default_message_recieved_callback=None,
                default_message_sent_callback=None):
        self.host=host
        self.port=port
        self.logger=logger
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
                self.logger.info('Could not connect to %s:%s. %s' % 
                    (self.host,str(self.port),str(err)))
        self.out_buffer=''
        self.in_buffer=''
        self.defaultResponseCallback=default_message_recieved_callback
        self.defaultSentCallback=default_message_sent_callback
        self.responseCallback=self.defaultResponseCallback
        self.sentCallback=self.defaultSentCallback

    def __str__(self):
        if self.isOpen():
            return 'Open SelectedSocket '+addr_str(self)
        else:
            return 'Closed SelectedSocket '+addr_str(self)

    def __getattr__(self, attr):
        return getattr(self.socket, attr)

    def addr_str(self):
        return "%s:%s"%(self.host,self.port)

    def sendMessage(self, message, sentCallback=None, responseCallback=None):
        if self.socket==None:
            self.logger.error('Attempting to send %s on disconnected socket %s:%s.'%
                (message,self.host,self.port))
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
                    self.logger.debug("Recieved message %s on %s" % 
                        (message_str, self))
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
                                  (self.out_buffer,self.out_buffer[count:],
                                   self.host,self.port))
                # and remove the sent data from the buffer
                self.out_buffer = self.out_buffer[count:]
                if self.sentCallback and self.out_buffer=='':
                    callback=self.sentCallback
                    self.sentCallback=self.defaultSentCallback
                    callback(self)
        except socket.error,err:
            self.handle_error(str(err))
            
    def handle_error(self, error=None):
        """Socket connection fails"""
        self.logger.error("Socket error %s on %s:%s." %(error, self.host,self.port))
        self.handle_disconnect()
        
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
        if self.responseCallback != None:
            callback=self.responseCallback
            self.responseCallback=self.defaultResponseCallback
            callback(self,'Lost Socket Connection.')
        self.sentCallback=self.defaultSentCallback
    
    def isOpen(self):
        return self.socket is not None
        
    def close(self):
        if self.socket is not None:
            self.handle_disconnect()
            
    def do_select_read(self):
        """ Do select for read whenever the socket is connected """
        return self.socket is not None
    
    def do_select_write(self):
        """ Do select for write whenever the socket is connected & have data """
        return self.socket != None and self.out_buffer !=''
    
    def do_select_error(self):
        """ Do select for errors always """
        return self.socket is not None