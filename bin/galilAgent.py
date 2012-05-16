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
sys.path.append('./lib/')
import galil
from HandledSocket import HandledSocket
from agent import Agent
from command import Command

MAX_CLIENTS=2

class GalilAgent(Agent):
    def __init__(self):
        Agent.__init__(self,'Galil Agent')
        
        #Initialize the Galil
        try:
            galilR=galil.Galil(self.args.DEVICE, self.logger)
        except galil.GalilStartupException:
            exit(1)
        self.devices.append(galilR)
    
    def listenOn(self):
        return ('localhost', self.PORT)
    
    def initialize_cli_parser(self):
        """Configure the command line interface"""
        #Create a command parser with the default agent commands
        helpdesc="This is the galil agent. It takes commands via \
            a socket connection (if started with a port) or via \
            CLI arguments."
        cli_parser = argparse.ArgumentParser(
                    description=helpdesc,
                    add_help=True)
        cli_parser.add_argument('--version',
                                action='version',
                                version=self.get_version_string())
        cli_parser.add_argument('-d','--daemon',dest='DAEMONIZE',
                                action='store_true', default=False,
                                help='Run agent as a daemon')
        cli_parser.add_argument('--device', dest='DEVICE',
                                action='store', required=False, type=str,
                                help='the device to control',
                                default='/dev/galilR')
        cli_parser.add_argument('-p','--port', dest='PORT',
                                action='store', required=False, type=int,
                                help='the port on which to listen')
        cli_parser.add_argument('command',nargs='*',
                                help='Agent command to execute')
        self.cli_parser=cli_parser
    
    def get_version_string(self):
        return 'Galil Agent Version 0.1'
    
    def socket_message_recieved_callback(self, source, message_str):
        """Create and execute a Command from the message"""
        if False:#message_str is malformed:
            command=Command(source, message_str, state='complete',
                reply='!ERROR: Malformed Command', callback=None)
        else:
            command=Command(source, message_str, callback=None)
            existing_commands_from_source=filter(lambda x: x.source==source, self.commands)
            if not existing_commands_from_source:
                if self.command_is_for_agent(command):# TODO command is command for agent:
                    1
                else:
                    self.commands.append(command)
                    def responseCallback(response_string):
                        command.state='complete'
                        command.reply=response_string+'\n'
                    def errorCallback(response_string):
                        command.state='complete'
                        command.reply='!ERROR:'+response_string+'\n'
                    self.devices[0].executeCommand(
                        command.string,
                        responseCallback,
                        errorCallback
                        )
            else:
                #...ignore and log error
                self.logger.warning(
                    'Command %s recieved before command %s finished.' %
                    (message_str, existing_commands_from_source[0].string))

    def command_is_for_agent(self, command):
        return False


if __name__=='__main__':
    agent=GalilAgent()
    agent.main()
