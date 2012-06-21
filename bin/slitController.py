#!/opt/local/bin/python2.7
import time
import argparse
import socket
import logging
import logging.handlers
import atexit
import sys
import select
sys.path.append('../lib/')
from agent import Agent
from command import Command
from m2fsConfig import m2fsConfig
from SelectedConnection import SelectedSocket

class SlitController(Agent):
    def __init__(self):
        Agent.__init__(self,'SlitController')
        #Connect to the shoes
        agent_ports=m2fsConfig.getAgentPorts()
        self.shoeAgentR_Connection=SelectedSocket('localhost',
            agent_ports['ShoeAgentR'], self.logger)
        self.devices.append(self.shoeAgentR_Connection)
        self.shoeAgentB_Connection=SelectedSocket('localhost',
            agent_ports['ShoeAgentB'], self.logger)
        self.devices.append(self.shoeAgentB_Connection)
        #No closed oop 
        self.closed_loop=0
        self.command_handlers={
            'SLITS':self.SLITS_comand_handler,
            'SLITS_CLOSEDLOOP':self.SLITS_CLOSEDLOOP_command_handler_blocking,
            'SLITS_SLITPOS':self.not_implemented_command_handler,
            'SLITS_CURRENTPOS':self.not_implemented_command_handler,
            'SLITS_ILLUMPROF':self.not_implemented_command_handler,
            'SLITS_ILLUMMEAS':self.not_implemented_command_handler,
            'SLITS_ACTIVEHOLD':self.SLITS_ACTIVEHOLD_command_handler,
            'SLITS_MOVSTEPS':self.not_implemented_command_handler,
            'SLITS_HARDSTOP':self.not_implemented_command_handler,
            'SLITS_IMAGSET':self.not_implemented_command_handler,
            'SLITS_PROJSET':self.not_implemented_command_handler,
            'SLITS_STATUS':self.status_command_handler,
            'SLITS_VERSION':self.version_request_command_handler}
    
    def listenOn(self):
        return ('localhost', self.PORT)
    
    def get_version_string(self):
        return 'Slit Controller Version 0.1'
    
    def status_command_handler(self, command):
        #First check Red shoe for motion
        try:
            self.shoeAgentR_Connection.sendMessageBlocking('SLITS_STATUS')
            statusR=self.shoeAgentR_Connection.receiveMessageBlocking()
        except IOError:
            statusR='Disconnected'
        #Then check Blue show for motion
        try:
            self.shoeAgentB_Connection.sendMessageBlocking('SLITS_STATUS')
            statusB=self.shoeAgentB_Connection.receiveMessageBlocking()
        except IOError:
            statusB='Disconnected'
        status=("Closed-loop:%s\rShoeA:%s\rShoeB:%s" %
            ('On' if self.closed_loop else 'Off', statusR, statusB))
        command.setReply(status+'\n')
    
    def SLITS_comand_handler(self, command):
        """ Handle a SLITS command """
        if '?' in command.string:
            """ Retrieve the slit positions """
            if 'R' in command.string:
                self.shoeAgentR_Connection.sendMessage('SLITS ?', 
                    responseCallback=command.setReply, errorCallback=command.setReply)
            elif 'B' in command.string:
                self.shoeAgentB_Connection.sendMessage('SLITS ?', 
                    responseCallback=command.setReply, errorCallback=command.setReply)
            else:
                self.bad_command_handler(command)
        else:
            """Command should be in form SLITS [R|B] #,#,#,#,#,#,#,# """
            if not self.closed_loop:
                if 'R' in command.string:
                    shoe_command='SLITS'+command.string.partition('R')[2]
                    self.shoeAgentR_Connection.sendMessage(shoe_command, 
                        responseCallback=command.setReply, errorCallback=command.setReply)
                elif 'B' in command.string:
                    shoe_command='SLITS'+command.string.partition('B')[2]
                    self.shoeAgentB_Connection.sendMessage(shoe_command,
                        responseCallback=command.setReply, errorCallback=command.setReply)
                else:
                    self.bad_command_handler(command)
            else:
                """ We are operating closed loop, way more work to do folks"""
                command.setReply('ERROR: Closed loop control not yet implemented.')
    
    def SLITS_CLOSEDLOOP_command_handler(self, command):
        """ handle switching between open and closed loop control"""
        if '?' in command.string:
            command.setReply('On' if self.closed_loop else 'Off')
            return
        if 'ON' in command.string and 'OFF' in command.string:
            self.bad_command_handler(command)
            return
        modeSame=((self.closed_loop and 'ON' in command.string) or
                  (not self.closed_loop and 'OFF' in command.string))
        if modeSame:
            command.setReply('OK')
            return
        def onReply(source, string):
            if string.split(' ')[-1] !=0:
                command.setReply('!ERROR: Slits currently in motion. Try switching control mode later.')
            else:
                def onReply2(source, string):
                    if string.split(' ')[-1] !=0:
                        command.setReply('!ERROR: Slits currently in motion. Try switching control mode later.')
                    else:
                        command.setReply('OK')
                        self.closed_loop= 'ON' in command.string
                self.shoeAgentB_Connection.sendMessage('STATUS', responseCallback=onReply2)
        self.shoeAgentR_Connection.sendMessage('STATUS', responseCallback=onReply)
            
    def SLITS_CLOSEDLOOP_command_handler_blocking(self, command):
        """ handle switching between open and closed loop control"""
        if '?' in command.string:
            command.setReply('On' if self.closed_loop else 'Off')
            return
        if 'ON' in command.string and 'OFF' in command.string:
            self.bad_command_handler(command)
            return
        modeSame=((self.closed_loop and 'ON' in command.string) or
                  (not self.closed_loop and 'OFF' in command.string))
        if modeSame:
            command.setReply('OK')
            return
        #First check Red shoe for motion
        try:
            self.shoeAgentR_Connection.sendMessageBlocking('STATUS')
            status_msg=self.shoeAgentR_Connection.receiveMessageBlocking()
            if status_msg.split(' ')[-1] !=0:
                command.setReply('!ERROR: Slits currently in motion. Try switching control mode later.')
                return
        except IOError:
            pass
        #Then check Blue shoe for motion
        try:
            self.shoeAgentB_Connection.sendMessageBlocking('STATUS')
            status_msg=self.shoeAgentB_Connection.receiveMessageBlocking()
            if status_msg.split(' ')[-1] !=0:
                command.setReply('!ERROR: Slits currently in motion. Try switching control mode later.')
                return
        except IOError:
            pass
        #Made it this far, nothing is moving (or they are disconnected)
        command.setReply('OK')
        self.closed_loop='ON' in command.string
                
    def SLITS_ACTIVEHOLD_command_handler(self, command):
        """ handle switching between motors on while idle and motors off"""
        if '?' in command.string:
            #First check Red shoe for motion
            try:
                self.shoeAgentR_Connection.sendMessageBlocking(command.string)
                activeHoldA=self.shoeAgentR_Connection.receiveMessageBlocking()
            except IOError:
                activeHoldR=''
            #Then check Blue shoe for motion
            try:
                self.shoeAgentB_Connection.sendMessageBlocking(command.string)
                activeHoldB=self.shoeAgentB_Connection.receiveMessageBlocking()
            except IOError:
                activeHoldB=''
            if activeHoldR!=activeHoldB and activeHoldR and activeHoldB:
                commandToB=('SLITS_ACTIVEHOLD '+
                            ( 'ON' if 'ON' in activeHoldR.upper() else 'OFF'))
                try:
                    self.shoeAgentB_Connection.sendMessageBlocking(commandToB)
                except IOError:
                    pass
            if activeHoldR:
                command.setReply(activeHoldR)
            elif activeHoldB:
                command.setReply(activeHoldB)
            else:
                command.setReply('ERROR: Unable to poll either shoe for status.')
        else:
            command.setReply('OK')
            self.shoeAgentR_Connection.sendMessage(command.string)
            self.shoeAgentB_Connection.sendMessage(command.string)
    

if __name__=='__main__':
    agent=SlitController()
    agent.main()
