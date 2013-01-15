#!/usr/bin/env python2.7
import sys
sys.path.append(sys.path[0]+'/../lib/')
import SelectedConnection
from agent import Agent

GUIDER_AGENT_VERSION_STRING='Guider Agent v0.1'

class GuiderAgent(Agent):
    def __init__(self):
        Agent.__init__(self,'GuiderAgent')
        self.guider=SelectedConnection.SelectedSerial('/dev/guider', 115200)
        self.devices.append(self.guider)
        self.command_handlers.update({
            #Get/Set the guider filter (1, 2, 3, or 4)
            'GFILTER':self.GFILTER_command_handler,
            #Get/Set the guider focus value
            'GFOCUS':self.GFILTER_command_handler})

    def get_version_string(self):
        """ Return a string with the version."""
        return GUIDER_AGENT_VERSION_STRING
    
    def get_cli_help_string(self):
        """
        Return a brief help string describing the agent.
        
        Subclasses shuould override this to provide a description for the cli
        parser
        """
        return ("This is the guider agent. It controls the guider filter "+
            "wheel & guider focus.")
    
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
        state='Filter:%s Focus:%s Err:%s' % (filterStatus, focusStatus, err)
        reply='%s: %s %s' % (self.get_version_string(), self.cookie, state)
        command.setReply(reply)

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
