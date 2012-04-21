import serial, thread, threading, time, sys, socket

class ThreadedSocket(threading.Thread):
    def __init__(self, host, port, logger):
        threading.Thread.__init__(self)
        self.host=host
        self.port=port
        self.socket=None
        self.connect_socket()
        self.logger=logger
        self.out_buffer=''
        self.in_buffer=''
        self.responseCallback=None
        self.sentCallback=None
        self.writeLock = thread.allocate_lock()
        self.start()
            
    def run(self):
        while True:
            self.handle_write()
            self.handle_read()
            self.handle_message(message)
            
    def connect_socket(self):
        if self.socket is None:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            self.socket.setblocking(0)
            
    def sendMessage(self, message, sentCallback=None, responseCallback=None):
        if message=='':
            return
        # lock to ensure that only one message is written to a given socket at a time
        self.writeLock.acquire()
        if self.out_buffer!='':
            self.writeLock.release()
            return
        self.out_buffer=message
        if message[-1] !='\n':
            self.out_buffer=message+'\n'
        else:
            self.out_buffer=message
        if responseCallback is not None:
            self.responseCallback=responseCallback
        if sentCallback is not None:
            self.sentCallback=sentCallback
        self.writeLock.release()
		
    def handle_write(self):
        """Write to socket"""
        try:
            self.writeLock.acquire()
            # write a chunk
            count = self.socket.send(self.out_buffer)
            self.logger.debug('Attempted write: "%s" , Wrote: "%s"' %
                              (self.out_buffer,self.out_buffer[count:]))
            # and remove the sent data from the buffer
            self.out_buffer = self.out_buffer[count:]
            if self.sentCallback:
                callback=self.sentCallback
                self.sentCallback=None
                callback(self)
        except socket.error,err:
            self.logger.error("Socket error %s, disconnecting." % err)
            self.out_buffer=''
            self.socket.close()
            self.socket = None
        finally:
            self.writeLock.release()
    
    def handle_read(self):
        """Read from socket. Call callback"""
        try:
            self.writeLock.acquire()
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
                        self.responseCallback=None
                        callback(self, message_str[:-1])
            else:
                # empty read indicates disconnection
                self.logger.error("Empty read, socket dead.")
                self.out_buffer=''
                self.socket.close()
                self.socket = None
        except socket.error:
            self.handle_error()
        finally:
            self.writeLock.release()
