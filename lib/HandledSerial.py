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


class HandledSerial():
    """class that add select handlers to serial.Serial
    
    messageComplete shall be a function which accepts a string
    and returns the length of the complete message, <1 indicate message 
    is incomplete
    """
    def __init__(self, baudrate=115200, timeout=0, logger=None,
                 sendTerminator='\r', messageComplete=None):
        self.serial=serial.Serial(baudrate=baudrate,timeout=timeout)
        self.logger=logger
        self.in_buffer=''
        self.out_buffer=''
        self.message_sent_callback=None
        self.message_recieved_callback=None
        self.sendTerminator=sendTerminator
        if messageComplete is None:
            self.messageComplete=lambda msg: msg.find('\n')+1
        else:
            self.messageComplete=messageComplete

    def __getattr__(self, attr):
        return getattr(self.serial, attr)

    def handle_read(self):
        bytes_in=self.read(self.inWaiting())
        self.in_buffer+=bytes_in
        #see if message is complete
        msg_len=self.messageComplete(self.in_buffer)
        if msg_len > 0:
            #Complete mesage just recieved
            message_str=self.in_buffer[0:msg_len]
            self.in_buffer=self.in_buffer[msg_len:]
            #message is a response
            self.logger.info("Recieved serial data %s on %s" % 
                (message_str, self))
            if self.message_recieved_callback:
                self.message_recieved_callback(self, message_str)

    def handle_write(self):
        if self.out_buffer:
            try:
                count=self.write(self.out_buffer)
                self.out_buffer=self.out_buffer[count:]
                if (not self.out_buffer and 
                    self.message_sent_callback is not None):
                    self.message_sent_callback(self)
            except serial.SerialException,err:
                self.handle_error(error=err)

    def handle_error(self,error=None):
        self.close()
        if error is not None:
            self.logger.error('%s error %s' % (self.port,error))
        else:
            self.logger.error('Serial port %s error.' % self.port)

    def send_message(self, msg, sentCallback=None, recievedCallback=None):
        """Add message to output buffer and register callbacks
        
        Message may have at most one terminator and it must be at the end of
        the message. If message does not have a terminator one will be added.
        """
        if self.out_buffer:
            raise Exception("Message pending")
        msg_str=str(msg)
        terminator_count=msg_str.count(self.sendTerminator)
        if terminator_count == 0:
            msg_str=msg_str+self.sendTerminator
        elif terminator_count == 1:
            if msg_str[-1] != self.sendTerminator:
                raise Exception("Message terminator not and end of message")
        else:
            raise Exception("Message malformed: has multiple terminators.")
        self.flushInput()
        self.out_buffer=msg_str
        if sentCallback is not None:
            self.message_sent_callback=sentCallback
        if recievedCallback is not None:
            self.message_recieved_callback=recievedCallback
