#!/usr/bin/env python2.7
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
sys.path.append('../lib/')
import SelectedConnection
from agent import Agent
from command import Command

MAX_CLIENTS=1

import termios


class FeedbackAgent(Agent):
    def __init__(self):
        Agent.__init__(self,'PluggingAgent')
        #Initialize the shoe
        self.misplugAudioFile=m2fsConfig.getMisplugAudioFilename()
        self.status='OK'
        self.max_clients=1
        self.misplug_messages={}
        self.command_handlers.update({'MISPLUG':self.MISPLUG_command_handler}
                    'DISPLAYOFF':self.DISPLAYOFF_command_handler)
        try:
            self.display=serial.Serial('/dev/pluggingDisplay', 115200)
            self.display.write('\x14') #cursor off
            # Set brightness to 200% (25-200% set by changing final byte from 1-8)
            self.display.write('\x1F\x58\x08')
            
    def listenOn(self):
        return ('localhost', self.PORT)
    
    def get_version_string(self):
        return 'Feedback Agent Version 0.1'
    
    def DISPLAYOFF_command_handler(self, command):
        command.setReply('OK')
        try:
            self.display.write('\x1F\x28\x61\x40\x00')
        except Exception, e:
            self.status['Display']='disconnected'

    def status_command_handler(self, command):
        command.setReply('%s %s'%(self.displayStatus, self.speakerStatus))

    def MISPLUG_command_handler(self, command):
        """ Play sound on side and display message

        Syntax: MISPLUG ID # msg  OR MISPLUG ID
        ID is a unique for the misplug, sending just an ID clears the misplug.
        ID must not have spaces.
        # number between -1 & 1. Defines the relative horizontal position of
        the misplug on the plate -1 for left side, 1 for right side
        msg a message to be displayed about the misplug.
        msg may have spaces but should be fewer than 25 characters

        """
        command_parts=command.string.split(' ')

        if len(command_parts) != 2 and len(command_parts) < 4:
            self.bad_command_handler(command)
            return
            
        if len(command_parts) == 2:
            self.misplug_messages.pop(command_parts[1],None)
            self.update_display_text()
            command.setReply('OK')
        else:
            try:
                pan=int(float(command_parts[2]))
            except ValueError:
                command.setReply("!ERROR Second parameter must be a number.")
            else:
                play_misplug(pan)
                self.misplug_messages[command_parts[1]]=''.join(command_parts[3:])
                self.update_display_text()
                command.setReply('OK')
    
    def update_display_text(self):
        """ Show the current misplug info on the display """
        self.display.write('\x1F\x28\x61\x40\x01') #display on
        self.display.sendMessageBlocking('\x0C') #cursor home
        self.display.sendMessageBlocking(''.join(self.misplug_messages.values())
    
    def play_misplug(self, pan):
        """ TODO: Play misplug sound with pan setting """
        from wave import open as waveOpen
        from ossaudiodev import open as ossOpen
        s = waveOpen(self.misplugAudioFile,'rb')
        (nc,sw,fr,nf,comptype, compname) = s.getparams( )
        dsp = ossOpen('/dev/dsp','w')
        try:
          from ossaudiodev import AFMT_S16_NE
        except ImportError:
          if byteorder == "little":
            AFMT_S16_NE = ossaudiodev.AFMT_S16_LE
          else:
            AFMT_S16_NE = ossaudiodev.AFMT_S16_BE
        dsp.setparameters(AFMT_S16_NE, nc, fr)
        data = s.readframes(nf)
        s.close()
        dsp.write(data)
        dsp.close()

if __name__=='__main__':
    agent=FeedbackAgent()
    agent.main()
