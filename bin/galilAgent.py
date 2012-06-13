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
from agent import Agent
from command import Command

class GalilAgent(Agent):
    def __init__(self):
        Agent.__init__(self,'GalilAgent')    
        #Initialize the Galil
        self.command_handlers={
            'STATUS':self.STATUS_command_handler,
            'VERSION':self.version_request_command_handler,
            'GALILRAW':self.galil_command_handler,
            'FILTER':self.galil_command_handler,
            'LREL':self.galil_command_handler,
            'HREL':self.galil_command_handler,
            'HRAZ':self.galil_command_handler,
            'FOCUS':self.galil_command_handler,
            'GES':self.galil_command_handler,
            'FILTER_INSERT':self.galil_command_handler,
            'FILTER_REMOVE':self.galil_command_handler,
            'FLSIM_INSERT':self.galil_command_handler,
            'FLSIM_REMOVE':self.galil_command_handler,
            'FOCUS_CALIBRATE':self.galil_command_handler,
            'LREL_CALIBRATE':self.galil_command_handler,
            'HREL_CALIBRATE':self.galil_command_handler,
            'HRAZ_CALIBRATE':self.galil_command_handler,
            'GES_CALIBRATE':self.galil_command_handler,
            'GES_DEFHRP':self.defaults_command_handler,
            'GES_DEFLRP':self.defaults_command_handler,
            'FILTER_DEFSTEP':defaults_command_handler,
            'FILTER_DEFENC'defaults_command_handler
            'FILTER_DEFINS':defaults_command_handler,
            'FILTER_DEFREM':defaults_command_handler,
            'FILTER_DEFTOL':defaults_command_handler,
            'GES_DEFHRSTEP':defaults_command_handler,
            'GES_DEFLRSTEP':defaults_command_handler,
            'GES_DEFHRENC':defaults_command_handler,
            'GES_DEFLRENC':defaults_command_handler,
            'GES_DEFTOL':defaults_command_handler,
            'FLSIM_DEFINS':defaults_command_handler,
            'FLSIM_DEFREM':defaults_command_handler,
            'GES_DEFSWPSTEP':defaults_command_handler,
            'GES_DEFSWPENC':defaults_command_handler} 
        self.galil=GalilSerial(self.args.DEVICE, 115200, self.logger, timeout=0.5)
        self.devices.append(self.galil)
    
    def listenOn(self):
        return ('localhost', self.PORT)
    
    def initialize_cli_parser(self):
        """Configure the command line interface"""
        #Create a command parser with the default agent commands
        helpdesc="This is the shoe agent. It takes shoe commands via \
            a socket connection (if started as a daemon) or via \
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
        
    def defaults_command_handler(self, command):
        command_name,junk,args=command.string.partition(' ')
        if command_name in ['FILTER_DEFSTEP','FILTER_DEFENC']:
            command_name=command_name+' '+args.split(' ')[0]
        #double check this is a real config parameter
        command_settingName_map={
            'FILTER_DEFSTEP 1':'filter1step','FILTER_DEFSTEP 2':'filter2step',
            'FILTER_DEFSTEP 3':'filter3step','FILTER_DEFSTEP 4':'filter4step',
            'FILTER_DEFSTEP 5':'filter5step','FILTER_DEFSTEP 6':'filter6step',
            'FILTER_DEFSTEP 7':'filter7step','FILTER_DEFSTEP 8':'filter8step',
            'FILTER_DEFSTEP 9':'filter9step', #NB LOAD position
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
            'FLSIM_DEFINS':'flsimInserted','FLSIM_DEFREM':'flsimRemoved'
            'GES_DEFSWPSTEP':'loresSwapStep','GES_DEFSWPENC':'loresSwapEncoder'}
        if command_name not in command_settingName_map:
            command.setReply('!ERROR: Bad Command. %s' % command)
            return
        #Grab the setting name
        settingName=command_settingName_map[command_name]
        #Getting or Setting?
        if '?' in command.string:
            command.setReply(self.galil.getDefault(settingName)
        else:
            command.setReply(self.galil.setDefault(settingName, args)
    
    def galil_command_handler(self, command):
        """Execute the command on the galil and setReply"""
        command_name,junk,args=command.string.partition(' ')[0]
        query='?' in command.string
        try:
            self.galil.connect()
            self.galil.initialize()
            if not self.galil.ready():
                command.setReply('ERROR: TODO')
        except IOError,e:
            command.setReply(e)
        
        query_commands={
            'FILTER':self.galil.get_filter,
            'LREL':self.galil.get_loel,
            'HREL':self.galil.get_hrel,
            'HRAZ':self.galil.get_hraz,
            'FOCUS':self.galil.get_foc,
            'GES':self.galil.get_ges
            }
        action_commands={
            'FILTER':self.galil.set_filter,
            'LREL':self.galil.set_loel,
            'HREL':self.galil.set_hrel,
            'HRAZ':self.galil.set_hraz,
            'FOCUS':self.galil.set_foc,
            'GES':self.galil.set_ges
            'FILTER_INSERT':self.galil.insert_filter
            'FILTER_REMOVE':self.galil.remove_filter
            'FLSIM_INSERT':self.galil.insert_flsim
            'FLSIM_REMOVE':self.galil.remove_flsim
            'LREL_CALIBRATE':self.galil.calibrate_lrel
            'HREL_CALIBRATE':self.galil.calibrate_hrel
            'HRAZ_CALIBRATE':self.galil.calibrate_hraz
            'GES_CALIBRATE':self.galil.calibrate_ges
        if query:
            command.setReply(query_commands[command_name]()))
        else:
            action_commands[command_name](args)
            command.setReply(TODO)
    

if __name__=='__main__':
    agent=GalilAgent()
    agent.main()

