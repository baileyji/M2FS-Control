#!/usr/bin/env python2.7
import sys, time
sys.path.append(sys.path[0]+'/../lib/')
import logging
import logging.handlers
import SelectedConnection
from agent import Agent
from command import Command
from m2fsConfig import m2fsConfig

SLIT_CONTROLLER_VERSION_STRING='Slit Controller v0.1'

class SlitController(Agent):
    def __init__(self):
        Agent.__init__(self,'SlitController')
        #Connect to the shoes
        agent_ports=m2fsConfig.getAgentPorts()
        self.shoeAgentR_Connection=SelectedConnection.SelectedSocket(
            'localhost', agent_ports['ShoeAgentR'])
        self.devices.append(self.shoeAgentR_Connection)
        self.shoeAgentB_Connection=SelectedConnection.SelectedSocket(
            'localhost', agent_ports['ShoeAgentB'])
        self.devices.append(self.shoeAgentB_Connection)
        #No closed loop
        self.closed_loop=False
        self.closedLoopMoveInProgress=False
        self.command_handlers.update({
            """ Note that the R slits are the slits in whichever shoe 
                is in the R cradle 
            """
            """ Get/Set the positions of all 8 of the R or B slits """
            'SLITS':self.SLITS_comand_handler,
            """ Toggle closed loop positioning or get status """
            'SLITS_CLOSEDLOOP':self.SLITS_CLOSEDLOOP_command_handler_blocking,
            """ Get/Set wheather to leave tetris motors on after a move """
            'SLITS_ACTIVEHOLD':self.SLITS_ACTIVEHOLD_command_handler,
            """ Pass command along to appropriate shoe """
            'SLITSRAW':self.pass_along_command_handler,
            'SLITS_MOVSTEPS':self.pass_along_command_handler,
            'SLITS_HARDSTOP':self.pass_along_command_handler,
            'SLITS_SLITPOS':self.pass_along_command_handler,
            'SLITS_CURRENTPOS':self.pass_along_command_handler})
            #'SLITS_ILLUMPROF':self.not_implemented_command_handler,
            #'SLITS_ILLUMMEAS':self.not_implemented_command_handler,
            #'SLITS_IMAGSET':self.not_implemented_command_handler,
            #'SLITS_PROJSET':self.not_implemented_command_handler})
    
    def get_cli_help_string(self):
        """
        Return a brief help string describing the agent.
        
        Subclasses shuould override this to provide a description for the cli
        parser
        """
        return "This is the slit controller agent"
    
    def get_version_string(self):
        """ Return a string with the version."""
        return SLIT_CONTROLLER_VERSION_STRING
    
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
    
    def pass_along_command_handler(self, command):
        """ 
        Command handler for commands that just get passed along
        
        Make sure the current mode is suitable to pass them along
        """
        command_name,junk,args=command.string.partition(' ')
        RorB,junk,args=args.partition(' ')
        #Verify that it is ok to pass the command along
        if (self.closed_loop and self.closedLoopMoveInProgress and
            command_name in ['SLITS_HARDSTOP','SLITS_MOVSTEPS']):
            command.setReply('ERROR: Closed loop move in progress.')
        else:
            if RorB!='R' and RorB !='B':
                self.bad_command_handler(command)
            elif 'R'==RorB:
                shoe_command='%s %s' % (command_name, args)
                try:
                    self.shoeAgentR_Connection.sendMessageBlocking(shoe_command)
                    response=self.shoeAgentR_Connection.receiveMessageBlocking()
                    command.setReply(response)
                except IOError:
                    command.setReply('Shoe R Disconnected')
            elif 'B'==RorB:
                shoe_command='%s %s' % (command_name, args)
                try:
                    self.shoeAgentB_Connection.sendMessageBlocking(shoe_command)
                    response=self.shoeAgentB_Connection.receiveMessageBlocking()
                    command.setReply(response)
                except IOError:
                    command.setReply('Shoe B Disconnected')
    
    def SLITS_comand_handler(self, command):
        """ Handle a SLITS command """
        if '?' in command.string:
            """ Retrieve the slit positions """
            if not self.closed_loop:
                if 'R' in command.string:
                    self.shoeAgentR_Connection.sendMessage('SLITS ?', 
                        responseCallback=command.setReply,
                        errorCallback=command.setReply)
                elif 'B' in command.string:
                    self.shoeAgentB_Connection.sendMessage('SLITS ?', 
                        responseCallback=command.setReply,
                        errorCallback=command.setReply)
                else:
                    self.bad_command_handler(command)
            else:
                """ We are operating closed loop, way more work to do folks"""
                command.setReply('ERROR: Closed loop control not yet implemented.')
        else:
            """
            Command should be in form:
            SLITS [R|B] {1-7} {1-7} {1-7} {1-7} {1-7} {1-7} {1-7} {1-7}
            """
            if not self.closed_loop:
                if 'R' in command.string:
                    shoe_command='SLITS'+command.string.partition('R')[2]
                    self.shoeAgentR_Connection.sendMessage(shoe_command, 
                        responseCallback=command.setReply,
                        errorCallback=command.setReply)
                elif 'B' in command.string:
                    shoe_command='SLITS'+command.string.partition('B')[2]
                    self.shoeAgentB_Connection.sendMessage(shoe_command,
                        responseCallback=command.setReply,
                        errorCallback=command.setReply)
                else:
                    self.bad_command_handler(command)
            else:
                """ We are operating closed loop, way more work to do folks"""
                command.setReply('ERROR: Closed loop control not yet implemented.')
    
    def SLITS_CLOSEDLOOP_command_handler(self, command):
        """ handle switching between open and closed loop control"""
        if '?' in command.string:
            command.setReply('ON' if self.closed_loop else 'OFF')
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
        """
        This is an engineering/testing command. Once a state is decided on it
        will be hardcoded as the default into the shoes' microcontroller.
        
        The function is an example of state synchronization problem with the 
        current control architecture. Say we want to set active holding to the
        non-default state. Now there should never be a situation where the 
        states of the two shoes differ. If the command arrives while one
        shoe is disconnected or one of the shoe agents crashes then the state 
        needs to be sent/resent to the shoe later. How do we resolve this?
        
        This instance of the issue is of minor importance as the default state
        will be preferred however the general problem with state could surface
        in some other area of the system.
        """
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
