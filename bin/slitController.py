#!/opt/local/bin/python2.7
#!/opt/local/bin/python2.7
import time
import argparse
import socket
import logging
import logging.handlers
import atexit
import sys
import select
sys.path.append('./lib/')
import shoe
from agent import Agent
from command import Command


class ShoeAgent(Agent):
    def __init__(self):
        Agent.__init__(self,'Slit Controller')
        #Connect to the shoes
        self.agent_ports=m2fsConfig.getAgentPorts()
        TODO GET OWN listening port from config settings 
        self.shoeAgentR_Connection=SelectedSocket('localhost',
            agent_ports['shoeR'], self.logger)
        self.devices.append(self.shoeAgentR_Connection)
        self.shoeAgentB_Connection=SelectedSocket('localhost',
            agent_ports['shoeB'], self.logger)
        self.devices.append(self.shoeAgentB_Connection)
    
    def listenOn(self):
        return ('localhost', self.PORT)
    
    def get_version_string(self):
        return 'Slit Controller Version 0.1'
    
    def socket_message_recieved_callback(self, source, message_str):
        """Create and execute a Command from the message"""
        """Dispatch message to from the appropriate handler"""
        command_handlers={
            'SLITS':SLITS_comand_handler,
            'SLITS_CLOSEDLOOP':SLITS_CLOSEDLOOP_command_handler,
            'SLITS_SLITPOS':
            'SLITS_CURRENTPOS':
            'SLITS_ILLUMPROF':not_implemented_command_handler,
            'SLITS_ILLUMMEAS':not_implemented_command_handler,
            'SLITS_ACTIVEHOLD':SLITS_ACTIVEHOLD_command_handler,
            'SLITS_MOVSTEPS':
            'SLITS_HARDSTOP':
            'SLITS_IMAGSET':
            'SLITS_PROJSET':
            'SLITS_STATUS':self.status_command_handler,
            'SLITS_VERSION':self.version_request_command_handler}
        command_name=message_str.partition(' ')[0]
        command=Command(source, message_str)
        if filter(lambda x: x.source==source, self.commands):
            self.logger.warning('Command %s recieved before command %s finished.' %
                (message_str, existing_commands_from_source[0].string))
        else:
            self.commands.append(command)
            command_handlers.get(command_name.upper(), self.bad_command_handler)(command)
    
    def SLITS_comand_handler(self, command):
        """ Handle a SLITS command """
        if '?' in command.string:
            """ Retrieve the slit positions """
            if 'R' in command.string:
                def onReply(source, reply):
                    command.state='complete'
                    command.reply=reply+'\n'
                self.shoeR_connection.sendMessage('SLITS ?', 
                    responseCallback=onReply, errorCallback=onReply)
            elif 'B' in command.string:
                def onReply(source, reply):
                    command.state='complete'
                    command.reply=reply+'\n'
                self.shoeB_connection.sendMessage('SLITS ?', 
                    responseCallback=onReply, errorCallback=onReply)
        else:
            """Command should be in form SLITS [R|B] #,#,#,#,#,#,#,# """
            if not self.closed_loop:
                def onReply(source, reply):
                    command.state='complete'
                    command.reply=reply+'\n'
                if 'R' in command.string:
                    shoe_command='SLITS'+command.string.partition('R')[2]
                    self.shoeR_connection.sendMessage(shoe_command, 
                        responseCallback=onReply, errorCallback=onReply)
                elif 'B' in command.string:
                    shoe_command='SLITS'+command.string.partition('B')[2]
                    self.shoeB_connection.sendMessage(shoe_command,
                        responseCallback=onReply, errorCallback=onReply)
            else:
                """ We are operating closed loop, way more work to do folks"""
                command.state='complete'
                command.reply='!ERROR: Closed loop control not yet implemented. Switch to open loop mode.\n'
    
    def SLITS_CLOSEDLOOP_command_handler(self, command):
        """ handle switching between open and closed loop control"""
        if '?' in command.string:
            command.state='complete'
            command.reply='On\n' if self.closed_loop else 'Off\n'
        elif:
            def onReply(source, string):
                if string means a motor is moving:
                    command.state='complete'
                    command.reply='!ERROR: Slits currently in motion. Try switching control mode later.\n'
                else:
                    def onReply2(source, string):
                        if string means a motor is moving:
                            command.state='complete'
                            command.reply='!ERROR: Slits currently in motion. Try switching control mode later.\n'
                        else:
                            command.state='complete'
                            command.reply='OK\n'
                            self.closed_loop= 'ON' in command.string
                    self.shoeB_connection.sendMessage('STATUS', responseCallback=onReply2)
            self.shoeR_connection.sendMessage('STATUS', responseCallback=onReply)
            
    def SLITS_CLOSEDLOOP_command_handler_blocking(self, command):
        """ handle switching between open and closed loop control"""
        if '?' in command.string:
            command.state='complete'
            command.reply='On\n' if self.closed_loop else 'Off\n'
        elif:
            #First check Red shoe for motion
            try:
                self.shoeR_connection.sendMessageBlocking('STATUS')
                status_msg=self.shoeR_connection.recieveBlocking()
                if string means a motor is moving:
                    command.state='complete'
                    command.reply='!ERROR: Slits currently in motion. Try switching control mode later.\n'
                    return
            except SelectedSocketError, e:
                command.state='complete'
                command.reply='!ERROR: Coult not get slit motion status.\n'
                return
            #Then check Blue show for motion
            try:
                self.shoeB_connection.sendMessageBlocking('STATUS')
                status_msg=self.shoeB_connection.recieveBlocking()
                if string means a motor is moving:
                    command.state='complete'
                    command.reply='!ERROR: Slits currently in motion. Try switching control mode later.\n'
                    return
            except SelectedSocketError, e:
                command.state='complete'
                command.reply='!ERROR: Coult not get slit motion status.\n'
                return
            #Made it this far, nothing is moving
            command.state='complete'
            command.reply='OK\n'
            self.closed_loop='ON' in command.string
    
    def SLITS_ACTIVEHOLD_command_handler(self, command):
        """ handle switching between motors on while idle and motors off"""
        if '?' in command.string:
            command.state='complete'
            command.reply='On\n' if self.active_hold else 'Off\n'
        elif 'ON' in command.string:
            command.state='complete'
            command.reply='OK\n'
            self.active_hold=True
            self.shoeR_connection.sendMessage('ACTIVEHOLDON', responseCallback=onAcceptaceOfCommand)
            self.shoeB_connection.sendMessage('ACTIVEHOLDON', responseCallback=onAcceptaceOfCommand)
        else:
            command.state='complete'
            command.reply='OK\n'
            self.active_hold=False
            self.shoeR_connection.sendMessage('ACTIVEHOLDOFF', responseCallback=onAcceptaceOfCommand)
            self.shoeB_connection.sendMessage('ACTIVEHOLDOFF', responseCallback=onAcceptaceOfCommand)
            
            
    def SLITS_ACTIVEHOLD_command_handler(self, command):
        """ handle switching between motors on while idle and motors off"""
        if '?' in command.string:
            command.state='complete'
            command.reply='On\n' if self.active_hold else 'Off\n'
        elif 'ON' in command.string:
            command.state='complete'
            command.reply='OK\n'
            self.active_hold=True
            self.shoeR_connection.sendMessage('ACTIVEHOLDON', responseCallback=onAcceptaceOfCommand)
            self.shoeB_connection.sendMessage('ACTIVEHOLDON', responseCallback=onAcceptaceOfCommand)
        else:
            command.state='complete'
            command.reply='OK\n'
            self.active_hold=False
            self.shoeR_connection.sendMessage('ACTIVEHOLDOFF', responseCallback=onAcceptaceOfCommand)
            self.shoeB_connection.sendMessage('ACTIVEHOLDOFF', responseCallback=onAcceptaceOfCommand)
    

if __name__=='__main__':
    agent=ShoeAgent()
    agent.main()
