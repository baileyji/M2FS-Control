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
sys.path.append('../lib/')
import SelectedConnection
from agent import Agent
from command import Command

MAX_CLIENTS=1

class ShoeFirmwareError(SelectedConnection.ConnectError):
    pass

import termios
class PluggingDisplaySerial(SelectedConnection.SelectedSerial):
    def connect(self):
        if self.connection is None:
            expected_version_string='Sharck-Hartman v0.1'
            try:
                self.connection=serial.Serial(self.port, self.baudrate, 
                    timeout=self.timeout)
                time.sleep(1)
                self.sendMessageBlocking('PV\n')
                response=self.receiveMessageBlocking().replace(':','')
                #response=expected_version_string #DEBUGGING LINE OF CODE
                if response != expected_version_string:
                    error_message=("Incompatible Firmware. Shoe reported '%s' , expected '%s'." %
                        (response,expected_version_string))
                    self.connection.close()
                    self.connection=None
                    raise ShoeFirmwareError(error_message)
            except serial.SerialException,e:
                error_message="Failed initialize serial link. Exception: %s"% e 
                self.logger.error(error_message)
                #self.connection.close()
                self.connection=None
                raise SelectedConnection.ConnectError(error_message)
            except IOError,e :
                if type(e)==type(ShoeFirmwareError):
                  raise e
                error_message="Shoe failed to handshake. %s"%e
                self.logger.error(error_message)
                #self.connection.close()
                self.connection=None
                raise SelectedConnection.ConnectError(error_message)

class FeedbackAgent(Agent):
    def __init__(self):
        Agent.__init__(self,'PluggingAgent')
        #Initialize the shoe
        self.misplugAudioFile=m2fsConfig.getMisplugAudioFilename()
        self.display=serial.Serial('/dev/pluggingDisplay', 19200)
        self.max_clients=1
        self.misplug_messages={}
        self.command_handlers.update({
            'MISPLUG':self.MISPLUG_command_handler})
    
    def listenOn(self):
        return ('localhost', self.PORT)
    
    def get_version_string(self):
        return 'Feedback Agent Version 0.1'

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
        self.display.write('\x??') #cursor home
        self.display.write('\n'.join(self.misplug_messages.values())
    
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
