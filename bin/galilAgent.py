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
            """ Send the command string directely to the Galil """
            'GALILRAW':self.galil_command_handler,
            """ Reset the Galil to its power-on state """
            'GALILRESET':self.not_implemented_command_handler,
            """ Get/Set the filter """
            'FILTER':self.galil_command_handler,
            """ These next two commands are the same as FILTER <current#> & 
            FILTER 10, perhapse they should be removed """
            """ Command the filter inserter to insert """
            'FILTER_INSERT':self.galil_command_handler,
            """ Command the filter inserter to retract """
            'FILTER_REMOVE':self.galil_command_handler,
            """ Get/Set the lorres elevation position """
            'LREL':self.galil_command_handler,
            """ Get/Set the hires elevation position """
            'HREL':self.galil_command_handler,
            """ Get/Set the hires azimuth position """
            'HRAZ':self.galil_command_handler,
            """ Get/Set the focus position """
            'FOCUS':self.galil_command_handler,
            """ 
            Command the GES to the HIRES, LORES, or grating change (LRSWAP)
            position. LRSWAP also blocks LREL commands as it is a coordinated
            move
            """
            'GES':self.galil_command_handler,
            #Nudge the GES stage by a little
            'GES_MOVE':self.galil_command_handler,
            #Insert/Remove FLS pickoff
            'FLSIM':self.galil_command_handler,
            """ Force Calibration of the named axis """
            'LREL_CALIBRATE':self.galil_command_handler,
            'HREL_CALIBRATE':self.galil_command_handler,
            'HRAZ_CALIBRATE':self.galil_command_handler,
            'GES_CALIBRATE':self.galil_command_handler,
            """ The _DEF commands get/set defailt values for varios values """
            """ The Hires step position"""
            'GES_DEFHRSTEP':self.defaults_command_handler,
            """ The Lores step position"""
            'GES_DEFLRSTEP':self.defaults_command_handler,
            """ The Hires encoder position"""
            'GES_DEFHRENC':self.defaults_command_handler,
            """ The Lores encoder position"""
            'GES_DEFLRENC':self.defaults_command_handler,
            """ gesenct """
            'GES_DEFTOL':self.defaults_command_handler,
            """ gesgsp """
            'GES_DEFSWPSTEP':self.defaults_command_handler,
            """ gesgsep """
            'GES_DEFSWPENC':self.defaults_command_handler,
            """ The encoder position of specified filter """
            'FILTER_DEFENC':self.defaults_command_handler,
            """ fesinsp"""
            'FILTER_DEFINS':self.defaults_command_handler,
            """ fesremp"""
            'FILTER_DEFREM':self.defaults_command_handler,
            """ feselrg """
            'FILTER_DEFTOL':self.defaults_command_handler,
            """ flsinsp """
            'FLSIM_DEFINS':self.defaults_command_handler,
            """ flsremp """
            'FLSIM_DEFREM':self.defaults_command_handler,
            #Do a soft reset of the galil
            'RESET':self.reset_command_handler})
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
            'GALILRESET':self.galil.reset,
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
            'GES_CALIBRATE':self.galil.calibrate_ges,
            'GES_MOVE':self.galil.nudge_ges}
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
        if command_name is 'FILTER_DEFENC':
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
    
    def _stowShutdown(self):
        """
        Perform a stowed shutdown
        """
        self.galil.shutdown()
    
    def galil_command_handler(self, command):
        """Execute the command on the galil and setReply"""
        command_name,junk,args=command.string.partition(' ')
        query='?' in command.string
        
        if command_name=='FLSIM':
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

