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
sys.path.append('./Galil/')
import galil
from HandledSocket import HandledSocket
from agent import Agent
from command import Command

MAX_CLIENTS=2

class GalilAgent(Agent):
    def __init__(self):
        Agent.__init__(self,'Datalogger Agent')
        
        #Initialize the dataloggers
        dataloggerR=datalogger.Datalogger('/dev/dataloggerR', self.logger)
        dataloggerB=datalogger.Datalogger('/dev/dataloggerB', self.logger)
        dataloggerC=datalogger.Datalogger('/dev/dataloggerC', self.logger)
        self.devices.append(dataloggerR)
        self.devices.append(dataloggerB)
        self.devices.append(dataloggerC)
        
        #open the logging database TODO
    
    def listenOn(self):
        return ('localhost', self.PORT)
      
    def get_version_string(self):
        return 'Datalogger Agent Version 0.1'
    
    def socket_message_recieved_callback(self, source, message_str):
        """Create and execute a Command from the message"""
        if False:#message_str is malformed:
            command=Command(source, message_str, state='complete',
                reply='!ERROR: Malformed Command', callback=None)
        else:
            command=Command(source, message_str, callback=None)
            existing_commands_from_source=filter(lambda x: x.source==source, self.commands)
            if not existing_commands_from_source:
                command_handlers={
                    'TEMPS':self.report_current_temps,
                    'STATUS':self.report_status}
                command_class=message_str.partition(' ')[0].partition('_')[0]
                command_handlers.get(command_class.upper(), self.bad_command_handler)(command)
            else:
                #...ignore and log error
                self.logger.warning(
                    'Command %s recieved before command %s finished.' %
                    (message_str, existing_commands_from_source[0].string))
    
    def report_current_temps(self, command):
        """ report the current temperatures """
        command.state='complete'
        command.reply='1 2 3 4 5 6 7 8 9 \n' #TODO
    
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
            
            check 
            
            #log commands
            for command in self.commands:
                self.logger.debug(command)
            
            self.cull_dead_sockets_and_their_commands()
            self.handle_completed_commands()
            


if __name__=='__main__':
    agent=GalilAgent()
    agent.main()

