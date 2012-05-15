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
            'SLITS_NOMINALPOS':
            'SLITS_ILLUMPROF':not_implemented_command_handler,
            'SLITS_ILLUMMEAS':not_implemented_command_handler,
            'SLITS_ACTIVEHOLD':
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
            command.state='complete'
            command.reply='TODO: Fetching of slit positions not yet implemented.\n'
        else:
            """Command should be in form SLITS [R|B] #,#,#,#,#,#,#,# """
            if self.operating_mode='OPEN_LOOP':
                def onAcceptaceOfCommand(source, reply):
                    command.state='complete'
                    command.reply=response_string+'\n'
                if 'R' in command.string:
                    self.shoeR_connection.sendMessage( command_string w/o R/B, responseCallback=onAcceptaceOfCommand)
                elif 'B' in command.string:
                    self.shoeB_connection.sendMessage( command_string w/o R/B, responseCallback=onAcceptaceOfCommand)
            else:
                """ We are operating closed loop, way more work to do folks"""
                command.state='complete'
                command.reply='Closed Loop slit control not yet implemented. Switch to open loop mode.\n'
    
    def SLITS_CLOSEDLOOP_command_handler(self, command):
        """ handle switching between open and closed loop control"""
        if '?' in command.string:
            command.state='complete'
            command.reply='TODO: Fetching of slit positions not yet implemented.\n'
        elif any slits are currently moving:
            command.state='complete'
            command.reply='!ERROR: Slits currently in motion try switching control mode later.\n'
        elif 'ON' in command.string:
            command.state='complete'
            command.reply='OK\n'
            self.operating_mode='CLOSED_LOOP'
        else:
            command.state='complete'
            command.reply='OK\n'
            self.operating_mode='OPEN_LOOP'
    
    
    def main(self):
        """
        Loop forever, acting on commands as received if on a port.
        
        Run once from command line if no port.
        
        """
        if self.PORT is None:
            self.logger.info('Command line commands not yet implemented.')
            sys.exit(0)
        while True:
            self.do_select()

            #log commands
            for command in self.commands:
                self.logger.debug(command)
            
            self.cull_dead_sockets_and_their_commands()
            self.handle_completed_commands()
            


if __name__=='__main__':
    agent=ShoeAgent()
    agent.main()
