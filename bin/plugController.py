#!/usr/bin/python
import sys, time
sys.path.append(sys.path[0]+'/../lib/')
import logging
import logging.handlers
from agent import Agent
from command import Command


class PlugController(Agent):
    def __init__(self):
        Agent.__init__(self,'PlugController')
        self.agent_ports=m2fsConfig.getAgentPorts()
        self.command_handlers={
            'PLATELIST':PLATELIST_command_handler,
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
            'STATUS':self.status_command_handler,
            'VERSION':self.version_request_command_handler}
    
    def listenOn(self):
        return ('localhost', self.PORT)
    
    def get_version_string(self):
        return 'Plugging Controller Version 0.1'
    

                    
                    
    def PLATELIST_command_handler(self, command):
        """ Command is to get the list of available plates and their setups"""
        command.setReply(self.get_string_of_available_plates_and_setups())
        
    def PLATE_command_handler(self, command)
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
    agent=PlugController()
    agent.main()
