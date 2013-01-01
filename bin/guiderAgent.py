#!/usr/bin/env python2.7
import sys, time
sys.path.append(sys.path[0]+'/../lib/')
import argparse
import logging
import logging.handlers
from agent import Agent
sys.path.append('../lib/')
import SelectedConnection
from command import Command


class GuiderAgent(Agent):
    def __init__(self):
        Agent.__init__(self,'GuiderAgent')
        self.guider=SelectedConnection.SelectedSerial('/dev/guider', 115200)
        self.devices.append(self.guider)
        self.command_handlers.update({
            """ Get/Set the guider filter (1, 2, 3, or 4) """
            'GFILTER':self.GFILTER_command_handler,
            """ Get/Set the guider focus value """
            'GFOCUS':self.GFILTER_command_handler})
    
    def listenOn(self):
        return ('localhost', self.PORT)

    def get_version_string(self):
        return 'Guider Agent Version 0.1'
    
    def GFILTER_command_handler(self, command):
        """ Handle geting/setting the LED illumination value """
        if '?' in command.string:
            position=self.determineFilter()
            command.setReply(position)
        else:
            command.setReply('OK')
    
    def GFOCUS_command_handler(self, command):
        """ Handle geting/setting the position of the lenslet inserter """
        if '?' in command.string:
            position=self.determineFocusPosition()
            command.setReply(position)
        else:
            command.setReply('OK')
    
    def status_command_handler(self, command):
        """report status"""
        filterStatus=self.determineFilter()
        focusStatus=self.determineFocusPosition()
        err=self.getErrorStatus()
        command.setReply('%s Filter:%s Focus:%s Err:%s' %
                         (self.cookie, filterStatus, focusStatus, err))

    def determineFilter(self):
        return '1'
    
    def determineFocusPosition(self):
        return '1337.0'
    
    def getErrorStatus(self):
        """
        Poll the controller for the error status byte
        
        Returns the error value as a hex string or ERROR if IOERROR
        """
        try:
            return '0x00'
        except Exception, e:
            return str(e)
    

if __name__=='__main__':
    agent=GuiderAgent()
    agent.main()
