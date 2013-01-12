#!/usr/bin/env python2.7
import sys, time
sys.path.append(sys.path[0]+'/../lib/')
import argparse
import logging
import logging.handlers
from agent import Agent
from command import Command
from galil import GalilSerial

GALIL_AGENT_VERSION_STRING='Galil Agent v0.2'

class GalilAgent(Agent):
    """
    This control program is responsible for all motions, exclusive of the tetri,
    for one side of the spectrograph. Two instances are run, one for the R side
    and one for the B side.
    
    Much of the detailed device functionality is handled by the Galil object,
    which is a subclass of SelectedSerial. See galil.py.
    
    For additional details please refrence the M2FS Control Systems
    document.
    """
    def __init__(self):
        Agent.__init__(self,'GalilAgent')
        #Update the list of command handlers
        self.command_handlers.update({
            #Send the command string directely to the Galil
            'GALILRAW':self.galil_command_handler,
            #Reset the Galil to its power-on state
            'GALILRESET':self.reset_command_handler,
            #Get/Set the filter
            'FILTER':self.galil_command_handler,
            #These next two commands are the same as FILTER <current#> & 
            #FILTER 10, perhapse they should be removed
            #Command the filter inserter to insert
            'FILTER_INSERT':self.galil_command_handler,
            #Command the filter inserter to retract
            'FILTER_REMOVE':self.galil_command_handler,
            #Get/Set the lorres elevation position
            'LREL':self.galil_command_handler,
            #Get/Set the hires elevation position
            'HREL':self.galil_command_handler,
            #Get/Set the hires azimuth position
            'HRAZ':self.galil_command_handler,
            #Get/Set the focus position
            'FOCUS':self.galil_command_handler,
            #Command the GES to the HIRES, LORES, or grating change (LRSWAP)
            #position. LRSWAP also blocks LREL commands as it is a coordinated
            #move
            'GES':self.galil_command_handler,
            #Nudge the GES stage by a little
            'GES_MOVE':self.galil_command_handler,
            #Insert/Remove FLS pickoff
            'FLSIM':self.galil_command_handler,
            #Force Calibration of the named axis
            'LREL_CALIBRATE':self.galil_command_handler,
            'HREL_CALIBRATE':self.galil_command_handler,
            'HRAZ_CALIBRATE':self.galil_command_handler,
            'GES_CALIBRATE':self.galil_command_handler,
            #The _DEF commands get/set defailt values for varios values
            #The Hires step position
            'GES_DEFHRSTEP':self.defaults_command_handler,
            #The Lores step position
            'GES_DEFLRSTEP':self.defaults_command_handler,
            #The Hires encoder position
            'GES_DEFHRENC':self.defaults_command_handler,
            #The Lores encoder position
            'GES_DEFLRENC':self.defaults_command_handler,
            #gesenct
            'GES_DEFTOL':self.defaults_command_handler,
            #gesgsp
            'GES_DEFSWPSTEP':self.defaults_command_handler,
            #gesgsep
            'GES_DEFSWPENC':self.defaults_command_handler,
            #The encoder position of specified filter
            'FILTER_DEFENC':self.defaults_command_handler,
            #fesinsp
            'FILTER_DEFINS':self.defaults_command_handler,
            #fesremp
            'FILTER_DEFREM':self.defaults_command_handler,
            #feselrg
            'FILTER_DEFTOL':self.defaults_command_handler,
            #flsinsp
            'FLSIM_DEFINS':self.defaults_command_handler,
            #flsremp
            'FLSIM_DEFREM':self.defaults_command_handler,
            #Do a soft reset of the galil
            'RESET':self.reset_command_handler})
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
        #Initialize the Galil
        if not self.args.DEVICE:
            self.args.DEVICE='/dev/galil'+self.args.SIDE
        self.galil=GalilSerial(self.args.DEVICE, 115200, timeout=0.5,
                               SIDE=self.args.SIDE)
        self.devices.append(self.galil)
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
    
    def get_cli_help_string(self):
        """
        Return a brief help string describing the agent.
        
        Subclasses shuould override this to provide a description for the cli
        parser
        """
        return "This is the galil agent"
    
    def add_additional_cli_arguments(self):
        """
        Additional CLI arguments may be added by implementing this function.
        
        Arguments should be added as:
        self.cli_parser.add_argument(See ArgumentParser.add_argument for syntax)
        """
        self.cli_parser.add_argument('--side', dest='SIDE',
                                action='store', required=False, type=str,
                                help='R or B',
                                default='R')
        self.cli_parser.add_argument('--device', dest='DEVICE',
                                action='store', required=False, type=str,
                                help='the device to control')

    def get_version_string(self):
        """ Return a string with the version."""
        return GALIL_AGENT_VERSION_STRING
        
    def STATUS_command_handler(self, command):
        """ Report the status of the galil """
        if self.galil.isOpen():
            state="Connected"
        else:
            state="Disconnected"
        reply='%s: %s %s' % (self.get_version_string(), self.cookie, state)
        command.setReply(reply)

    
    def defaults_command_handler(self, command):
        """
        Get/Set default positions values for the galil
        
        This implementationn is a bit clunkuy, using two dicts and some string
        analysis. I've not come up with anything better and it works.
        """
        command_name,junk,args=command.string.partition(' ')
        #check if the command needs preprocessing
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
        """ Reset the galil """
        command.setReply(self.galil.reset())
    
    def _stowShutdown(self):
        """
        Perform a stowed shutdown
        """
        self.galil.shutdown()
    
    def galil_command_handler(self, command):
        """
        Execute the command on the galil and set the reply to result 
        
        First analyze the command string to determine the appropriate galil
        function to call.
        
        This implementationn is a bit clunkuy, using two dicts and some string
        analysis. I've not come up with anything better and it works.
        """
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

