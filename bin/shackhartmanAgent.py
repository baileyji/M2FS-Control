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
        self.shled=SelectedConnection.SelectedSerial('/dev/shLED', 115200)
        self.shlenslet=SelectedConnection.SelectedSerial('/dev/shLenslet', 115200)
        self.devices.append(self.shlenslet)
        self.devices.append(self.shled)
        self.shledValue=0
        self.command_handlers.update({
            'SHLED':self.SHLED_command_handler,
            'SHLENS':self.SHLENS_command_handler,
            'TEMP':self.TEMP_command_handler})
    
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
                self.bad_command_handler(command)
            except IOError, e:
                command.setReply('ERROR: %s' % str(e))
    
    def SHLENS_command_handler(self, command):
        """ Handle geting/setting the position of the lenslet inserter """
        if '?' in command.string:
            position=self.determineLensletPosition()
            command.setReply(position)
        else:
            err=self.getErrorStatus()
            if err !='0x0':
                command.setReply('ERROR: %s' % err)
            else:
                try:
                    if 'IN' in command.string and 'OUT' not in command.string:
                        self.shlenslet.sendMessage('\x89\x7F')
                    elif 'OUT' in command.string and 'IN' not in command.string:
                        self.shlenslet.sendMessage('\x8A\x7F')
                    else:
                        self.bad_command_handler(command)
                except IOError, e:
                    command.setReply('ERROR: %s' % e)
    
    def TEMP_command_handler(self, command):
        """report temperature in deg C, temps below 0 = 0"""
        command.setReply(self.getTemp())
    
    def status_command_handler(self, command):
        """report status"""
        lensStatus=self.determineLensletPosition()
        temp=self.getTemp()
        err=self.getErrorStatus()
        try:
            self.shled.sendMessage(chr(self.shledValue))
            ledStatus='%i' % self.shledValue
        except IOError:
            ledStatus='ERROR'
        command.setReply('Lenslet:%s Led:%s Temp:%s Err:%s' %
                         (lensStatus, ledStatus, temp, err))
    
    def getErrorStatus(self):
        """
        Poll the controller for the error status byte
        
        Returns the error value as a hex string or ERROR if IOERROR
        """
        try:
            self.shlenslet.sendMessageBlocking('\xA1\x00')
            response=self.shlenslet.receiveMessageBlocking(nBytes=2)
            #for bit meanings se simple_motor_controllers.pdf
            err=hex(256*ord(response[1])+ord(response[0]))
            return err
        except Exception, e:
            return str(e)
    
    def getTemp(self):
        """
        Poll the controller for the temp
        
        Returns the temp value as a string or ERROR if IOERROR
        """
        try:
            self.shlenslet.sendMessageBlocking('\xA1\x18')
            response=self.shlenslet.receiveMessageBlocking(nBytes=2)
            temp=str(0.1*(ord(response[0])+256*ord(response[1])))
        except IOError:
            temp='ERROR'
        return temp
    
    def determineLensletPosition(self):
        try:
            self.shlenslet.sendMessageBlocking('\xA1\x21')
            response=self.shlenslet.receiveMessageBlocking()
            err=self.getErrorStatus()
            if response != 0 and err =='0x0':
                return 'MOVING'
            else:
                self.shlenslet.sendMessageBlocking('\xA1\x12')
                response=self.shlenslet.receiveMessageBlocking()
                if ord(response[0]) > 64: #limit is NC with pullup on 12bit ADC
                    return 'IN'
                else:
                    self.shlenslet.sendMessageBlocking('\xA1\x16')
                    response=self.shlenslet.receiveMessageBlocking()
                    if ord(response[0]) > 64:
                        return 'OUT'
                    else:
                        return 'INTERMEDIATE'
        except IOError:
            return 'ERROR'
    

if __name__=='__main__':
    agent=ShackHartmanAgent()
    agent.main()
