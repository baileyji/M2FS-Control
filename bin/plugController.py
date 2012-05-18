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
            'SLITS':
            'SLITS_CLOSEDLOOP':
            'SLITS_SLITPOS':
            'SLITS_NOMINALPOS':
            'SLITS_ILLUMPROF':
            'SLITS_ILLUMMEAS':
            'SLITS_ACTIVEHOLD':
            'SLITS_MOVSTEPS':
            'SLITS_HARDSTOP':
            'SLITS_IMAGSET':
            'SLITS_PROJSET':
            'SLITS_STATUS':self.status_command_handler,
            'SLITS_VERSION':self.version_request_command_handler}
        command_name=message_str.partition(' ')[0].partition('_')[0]
        command=Command(source, message_str)
        if filter(lambda x: x.source==source, self.commands):
            self.logger.warning('Command %s recieved before command %s finished.' %
                (message_str, existing_commands_from_source[0].string))
        else:
            self.commands.append(command)
            command_handlers.get(command_class.upper(), self.bad_command_handler)(command)
        
           command_name=message_str.partition(' ')
        if command_name not in commands.keys():
            command=Command(source, message_str, state='complete',
                reply='!ERROR: Malformed Command', callback=None)
        else:
            command=Command(source, message_str, callback=None)
            existing_commands_from_source=filter(lambda x: x.source==source, self.commands)
            if existing_commands_from_source: #...ignore and log error
                self.logger.warning(
                    'Command %s recieved before command %s finished.' %
                    (message_str, existing_commands_from_source[0].string))
            else:
                self.commands.append(command)
                
                def responseCallback(response_string):
                    command.state='complete'
                    command.reply=response_string+'\n'
                def errorCallback(response_string):
                    command.state='complete'
                    command.reply='!ERROR:'+response_string+'\n'
                    
                    
        def plateConfig_command_handler(self, command):
        command_name,junk,args=command.string.partition(' ')
        if command_name=='PLATELIST':
            """ Command is to get the list of available plates and their setups"""
            command.state='complete'
            command.reply=self.get_string_of_available_plates_and_setups()+'\n'
        elif command_name=='PLATE':
            """ Command is to get or set the current plate setup"""
            if '?' in command.string:
                command.state='complete'
                command.reply=self.current_active_plate+'\n'
            elif self.is_a_valid_plate(args):
                self.current_active_plate=args
                command.state='complete'
                command.reply='OK\n'
            else:
                command.state='complete'
                command.reply='!ERROR: Invalid plate specifier.\n'
        elif command_name=='PLATESETUP':
            """ Command is to get or set the current plate setup"""
            if '?' in command.string:
                command.state='complete'
                command.reply=self.current_active_plate_setup+'\n'
            elif self.is_a_valid_plate_setup(args):
                self.current_active_plate_setup=args
                command.state='complete'
                command.reply='OK\n'
            else:
                command.state='complete'
                command.reply='!ERROR: Invalid plate setup specifier.\n'
        else:
            """ This function shouldn't have been called."""
                command.state='complete'
                command.reply='!ERROR: Invalid command.\n'
    
    def is_a_valid_plate_setup(self, setup_string):
        """ Retrun true if setup_string is a setup on the current plate"""
        return Fasle

    def is_a_valid_plate(self, plate_string):
        """ Retrun true if plate_string is an available plate"""
        return False
        
    def get_string_of_available_plates_and_setups(self):
        """ Return a list of all the plates and their setups"""
        import os
        os.listdir(getPlateFileDirectory())
        return ''.join(os.listdir(getPlateFileDirectory()))
            


if __name__=='__main__':
    agent=ShoeAgent()
    agent.main()
