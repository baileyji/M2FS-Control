#!/usr/bin/env python2.7
import sys, time
sys.path.append(sys.path[0]+'/../lib/')
import argparse
import logging
import logging.handlers
from agent import Agent
from command import Command
from galil import GalilSerial

class GalilAgent(Agent):
    def __init__(self):
        Agent.__init__(self,'GalilAgent')
        #Initialize the Galil
        if not self.args.DEVICE:
            self.args.DEVICE='/dev/galil'+self.args.SIDE
        self.command_handlers.update({
            'GALILRAW':self.galil_command_handler,
            'FILTER':self.galil_command_handler,
            'LREL':self.galil_command_handler,
            'HREL':self.galil_command_handler,
            'HRAZ':self.galil_command_handler,
            'FOCUS':self.galil_command_handler,
            'GES':self.galil_command_handler,
            'FILTER_INSERT':self.galil_command_handler,
            'FILTER_REMOVE':self.galil_command_handler,
            'FLSIM':self.galil_command_handler,
            'LREL_CALIBRATE':self.galil_command_handler,
            'HREL_CALIBRATE':self.galil_command_handler,
            'HRAZ_CALIBRATE':self.galil_command_handler,
            'GES_CALIBRATE':self.galil_command_handler,
            'GES_DEFHRP':self.defaults_command_handler,
            'GES_DEFLRP':self.defaults_command_handler,
            'FILTER_DEFSTEP':self.defaults_command_handler,
            'FILTER_DEFENC':self.defaults_command_handler,
            'FILTER_DEFINS':self.defaults_command_handler,
            'FILTER_DEFREM':self.defaults_command_handler,
            'FILTER_DEFTOL':self.defaults_command_handler,
            'GES_DEFHRSTEP':self.defaults_command_handler,
            'GES_DEFLRSTEP':self.defaults_command_handler,
            'GES_DEFHRENC':self.defaults_command_handler,
            'GES_DEFLRENC':self.defaults_command_handler,
            'GES_DEFTOL':self.defaults_command_handler,
            'FLSIM_DEFINS':self.defaults_command_handler,
            'FLSIM_DEFREM':self.defaults_command_handler,
            'GES_DEFSWPSTEP':self.defaults_command_handler,
            'GES_DEFSWPENC':self.defaults_command_handler,
            'RESET':self.reset_command_handler,
            'SHUTDOWN':self.shutdown_command_handler})
        self.query_commands={
            'FILTER':self.galil.get_filter,
            'LREL':self.galil.get_loel,
            'HREL':self.galil.get_hrel,
            'HRAZ':self.galil.get_hraz,
            'FOCUS':self.galil.get_foc,
            'GES':self.galil.get_ges,
            'FLSIM':self.galil.get_flsim}
        self.action_commands={
            'GALILRAW':self.galil.raw,
            'FILTER':self.galil.set_filter,
            'LREL':self.galil.set_loel,
            'HREL':self.galil.set_hrel,
            'HRAZ':self.galil.set_hraz,
            'FOCUS':self.galil.set_foc,
            'GES':self.galil.set_ges,
            'FILTER_INSERT':self.galil.insert_filter,
            'FILTER_REMOVE':self.galil.remove_filter,
            'FLSIM_INSERT':self.galil.insert_flsim,
            'FLSIM_REMOVE':self.galil.remove_flsim,
            'LREL_CALIBRATE':self.galil.calibrate_lrel,
            'HREL_CALIBRATE':self.galil.calibrate_hrel,
            'HRAZ_CALIBRATE':self.galil.calibrate_hraz,
            'GES_CALIBRATE':self.galil.calibrate_ges}
        self.command_settingName_map={
            'FILTER_DEFENC 1':'filter1encoder','FILTER_DEFENC 2':'filter2encoder',
            'FILTER_DEFENC 3':'filter3encoder','FILTER_DEFENC 4':'filter4encoder',
            'FILTER_DEFENC 5':'filter5encoder','FILTER_DEFENC 6':'filter6encoder',
            'FILTER_DEFENC 7':'filter7encoder','FILTER_DEFENC 8':'filter8encoder',
            'FILTER_DEFENC 9':'filter9encoder', #NB LOAD position
            'FILTER_DEFINS':'filterInserted','FILTER_DEFREM':'filterRemoved',
            'FILTER_DEFTOL':'filterTolerance',
            'GES_DEFHRSTEP':'hiresStep','GES_DEFLRSTEP':'loresStep',
            'GES_DEFHRENC':'hiresEncoder','GES_DEFLRENC':'loresEncoder',
            'GES_DEFTOL':'gesTolerance',
            'FLSIM_DEFINS':'flsimInserted','FLSIM_DEFREM':'flsimRemoved',
            'GES_DEFSWPSTEP':'loresSwapStep','GES_DEFSWPENC':'loresSwapEncoder'}
        self.galil=GalilSerial(self.args.DEVICE, 115200,
            timeout=0.5, SIDE=self.args.SIDE)
        self.devices.append(self.galil)
    
    def listenOn(self):
        return ('localhost', self.PORT)
    
    def initialize_cli_parser(self):
        """Configure the command line interface"""
        #Create a command parser with the default agent commands
        helpdesc="This is the galil agent"
        cli_parser = argparse.ArgumentParser(
                    description=helpdesc,
                    add_help=True)
        cli_parser.add_argument('--version',
                                action='version',
                                version=self.get_version_string())
        cli_parser.add_argument('--device', dest='DEVICE',
                                action='store', required=False, type=str,
                                help='the device to control')
        cli_parser.add_argument('--side', dest='SIDE',
                                action='store', required=False, type=str,
                                help='R or B',
                                default='R')
        cli_parser.add_argument('-p','--port', dest='PORT',
                                action='store', required=False, type=int,
                                help='the port on which to listen')
        cli_parser.add_argument('command',nargs='*',
                                help='Agent command to execute')
        self.cli_parser=cli_parser
    
    def get_version_string(self):
        return 'Galil Agent Version 0.2'
        
    def STATUS_command_handler(self, command):
        if self.galil.isOpen():
            command.setReply("Connected")
        else:
            command.setReply("Disconnected")
    
    def defaults_command_handler(self, command):
        command_name,junk,args=command.string.partition(' ')
        if command_name in ['FILTER_DEFSTEP','FILTER_DEFENC']:
            command_name=command_name+' '+args.split(' ')[0]
        #double check this is a real config parameter
        if command_name not in self.command_settingName_map:
            command.setReply('!ERROR: Bad Command. %s' % command)
            return
        #Grab the setting name
        settingName=self.command_settingName_map[command_name]
        #Getting or Setting?
        if '?' in command.string:
            command.setReply(self.galil.getDefault(settingName))
        else:
            command.setReply(self.galil.setDefault(settingName, args))
    
    def reset_command_handler(self, command):
        command.setReply(self.galil.reset())
    
    def shutdown_command_handler(self, command):
        command.setReply(self.galil.shutdown())
    
    def galil_command_handler(self, command):
        """Execute the command on the galil and setReply"""
        command_name,junk,args=command.string.partition(' ')
        query='?' in command.string
        
        if command_name=='FLSIM':
            if args=='IN':
                command_name='FLSIM_INSERT'
            elif args=='OUT':
                command_name='FLSIM_REMOVE'
        elif command_name=='FILTER':
            if args=='IN':
                command_name='FLSIM_INSERT'
            elif args=='OUT':
                command_name='FLSIM_REMOVE'
        
        if query:
            command.setReply(self.query_commands[command_name]())
        else:
            command.setReply(self.action_commands[command_name](args))
    

if __name__=='__main__':
    agent=GalilAgent()
    agent.main()

