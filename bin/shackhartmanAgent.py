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


class ShackHartmanAgent(Agent):
    def __init__(self):
        Agent.__init__(self,'ShackHartmanAgent')
        #Initialize the agent
        self.args=self.cli_parser.parse_args()
        self.shled=SelectedConnection.SelectedSerial('/dev/SHled', 115200)
        self.shledValue=0
        self.shlenslet=SelectedConnection.SelectedSerial('/dev/SHlenslet',
            115200)
        self.devices.append(self.shlenslet)
        self.devices.append(self.shled)
        self.max_clients=1
        self.command_handlers.update({
            'SHLED':self.SHLED_command_handler,
            'SHLENS':self.SHLENS_command_handler})
    
    def listenOn(self):
        return ('localhost', self.PORT)

    def get_version_string(self):
        return 'Shack-Hartman Agent Version 0.1'
    
    def SHLED_command_handler(self, command):
        """ Handle geting/setting the LED illumination value """
        if '?' in command.string:
            command.setReply('%i' % self.shledValue)
        else:
            """ Set the LED brightness 0-255 """
            command_parts=command.string.split(' ')
            try:
                self.shled.sendMessage(chr(int(command_parts[1])))
                self.shledValue=int(command_parts[1])
                command.setReply('OK')
            except ValueError:
                self.invalid_command_handler(command)
            except IOError, e:
                command.setReply('ERROR: %s' % str(e))
    
    def SHLENS_command_handler(self, command):
        """ Handle geting/setting the position of the lenslet inserter """
        if '?' in command.string:
            position=self.determineLensletPosition()
            command.setReply(position)
        else:
            #TODO add in command response
            if 'IN' in command.string and 'OUT' not in command.string:
                self.shlenslet.sendMessageBlocking('\x89\x7F')
            elif 'OUT' in command.string and 'IN' not in command.string:
                self.shlenslet.sendMessageBlocking('\x8A\x7F')
            else:
                command.setReply('!ERROR: Improperly formatted command.\n')

    def status_command_handler(self, command):
        """report status"""
        try:
            lensStatus=self.determineLensletPosition()
        except IOError:
            lensStatus='ERROR'
        try:
            self.shled.sendMessage(chr(self.shledValue))
            ledStatus='%i' % self.shledValue
        except IOError:
            ledStatus='ERROR'
        command.setReply('Lenslet: %s Led: %s' % (lensStatus, ledStatus))
    
    def determineLensletPosition(self):
        self.shlenslet.sendMessageBlocking('\xA1\x21')
        response=self.shlenslet.receiveMessageBlocking()
        if response != 0:
            return 'MOVING'
        else:
            self.shlenslet.sendMessageBlocking('\xA1\x12')
            response=self.shlenslet.receiveMessageBlocking()
            if response > 1024: #limit is NC with pullup on 12bit ADC 
                return 'IN'
            else:
                self.shlenslet.sendMessageBlocking('\xA1\x16')
                response=self.shlenslet.receiveMessageBlocking()
                if response > 1024:
                    return 'OUT'
                else:
                    return 'INTERMEDIATE'

if __name__=='__main__':
    agent=ShackHartmanAgent()
    agent.main()
