#!/opt/local/bin/python2.7
import time
import argparse
import socket
import signal
import logging
import logging.handlers
import atexit
import serial
import sys
import select

class HandledSocket():
    def __init__(self, sock, message_callback=None,logger=None):
        if type(sock) is tuple:
            self.socket=socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect(sock)
        else:
            self.socket=sock
        self.logger=logger
        self.in_buffer=''
        self.out_buffer=''
        self.message_recieved_callback=message_callback

    def __getattr__(self, attr):
        return getattr(self.socket, attr)
    #def __setattr__(self, attr, value):
        #return setattr(self.socket, attr, value)   

    def have_data_to_send(self):
        return self.out_buffer != ''
    
    def clear_output_buffer(self):
        self.out_buffer=''

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
                    self.message_recieved_callback(self, message_str[:-1])
            else:
                # empty read indicates disconnection
                self.handle_disconnect()
        except socket.error:
            self.handle_socket_error()
            
    def handle_write(self):
        """Write to socket"""
        try:
            if self.out_buffer and '\n' not in self.out_buffer:
                self.out_buffer+='\n'
            # write a chunk
            count = self.socket.send(self.out_buffer)
            self.logger.debug('Attempted write: "%s" , Wrote: "%s"' %
                              (self.out_buffer,self.out_buffer[count:]))
            # and remove the sent data from the buffer
            self.out_buffer = self.out_buffer[count:]
        except socket.error,err:
            self.handle_socket_error(err)

    def handle_error(self, error=None):
        """Socket connection fails"""
        self.logger.error("Socket error %s, disconnecting." % socket.error)
        self.handle_disconnect()
    
    
    def isOpen(self):
        return self.socket is not None
    
    def handle_disconnect(self):
        """Socket gets disconnected"""
        self.clear_output_buffer()
        if self.socket is not None:
            self.socket.close()
            self.socket = None
            self.logger.info('Client disconnected')
            
    def do_select_read(self):
        """ Do select for read whenever the socket is connected """
        return self.socket is not None
    
    def do_select_write(self):
        """ Do select for write whenever the socket is connected & have data """
        return self.socket is not None and self.have_data_to_send()
    
    def do_select_error(self):
        """ Do select for errors always """
        return True