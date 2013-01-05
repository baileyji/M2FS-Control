#!/usr/bin/env python2.7
import sys, time, socket, os
sys.path.append(sys.path[0]+'/../lib/')
from agent import Agent
import SelectedConnection
from command import Command
from m2fsConfig import m2fsConfig

DIRECTOR_VERSION_STRING='Director v0.5'

class Director(Agent):
    """
    This is the primary control program for the M2FS instrument. It does
    relatively little for the majority of commands, merely passing them along to
    the appropriate other Agent program responsible for that particular 
    subsystem. For additional details please refrence the M2FS Control Systems
    document.
    """
    def __init__(self):
        """
        Initialize the M2FS Director
        
        The Director starts by creating connections to all of the other agents.
        It then updates command_handlers withall of the instrument commands
        
        At this point the Director is ready to start listening for commands and
        processing them when self.main() is called
        """
        Agent.__init__(self,'Director')
        #Enable stowed shutdown by default
        m2fsConfig.enableStowedShutdown()
        #Fetch the agent ports
        agent_ports=m2fsConfig.getAgentPorts()
        #Galil Agents
        self.galilAgentR_Connection=SelectedConnection.SelectedSocket('localhost',
            agent_ports['GalilAgentR'])
        self.galilAgentB_Connection=SelectedConnection.SelectedSocket('localhost',
            agent_ports['GalilAgentB'])
        #Slit Subsytem Controller
        self.slitController_Connection=SelectedConnection.SelectedSocket('localhost',
            agent_ports['SlitController'])
        #Datalogger Agent
        self.dataloggerAgent_Connection=SelectedConnection.SelectedSocket('localhost',
            agent_ports['DataloggerAgent'])
        #Shack-Hartman Agent
        self.shackhatmanAgent_Connection=SelectedConnection.SelectedSocket('localhost',
            agent_ports['ShackHartmanAgent'])
        #Plugging Controller
        self.plugController_Connection=SelectedConnection.SelectedSocket('localhost',
            agent_ports['PlugController'])
        #Guider Agent
        self.guiderAgent_Connection=SelectedConnection.SelectedSocket('localhost',
            agent_ports['GuiderAgent'])
        #add them all to devices
        self.devices.append(self.galilAgentR_Connection)
        self.devices.append(self.galilAgentB_Connection)
        self.devices.append(self.slitController_Connection)
        self.devices.append(self.dataloggerAgent_Connection)
        self.devices.append(self.shackhatmanAgent_Connection)
        self.devices.append(self.plugController_Connection)
        self.devices.append(self.guiderAgent_Connection)
        self.command_handlers.update({
            #Director Commands
            #
            #These commands operate on the entire instrument or require
            #coordinating a multiple systems.
            #
            #Notify the instrument the GUI is about to close """
            'GUICLOSING':self.guiclose_command_handler,
            #Shut the instrument down, all axes move to stowed positions
            'SHUTDOWN':self.shutdown_command_handler,
            #Enable/Disable plugging mode.
            #Involves GalilAgents, PlugController, & SlitController.
            'PLUGMODE': self.plugmode_command_handler,
            #Enable/Disable Stowed shutdown
            'STOWEDSHUTDOWN': self.stowedshutdown_command_handler,
            #Galil Agent (R & B) Commands
            #
            #The director determines if the command is for the R or B galilAgent
            #and then passes it along to the agent.
            #
            #Authoritative command discriptions are in galilAgent.py
            'GALILRESET':self.galil_command_handler,
            'GALILRAW':self.galil_command_handler,
            'GES':self.galil_command_handler,
            'GES_MOVE':self.galil_command_handler,
            'GES_CALIBRATE':self.galil_command_handler,
            'LREL':self.galil_command_handler,
            'LREL_CALIBRATE':self.galil_command_handler,
            'HREL':self.galil_command_handler,
            'HREL_CALIBRATE':self.galil_command_handler,
            'HRAZ':self.galil_command_handler,
            'HRAZ_CALIBRATE':self.galil_command_handler,
            'FOCUS':self.galil_command_handler,
            'FILTER':self.galil_command_handler,
            'FILTER_INSERT':self.galil_command_handler,
            'FILTER_REMOVE':self.galil_command_handler,
            'FLSIM':self.galil_command_handler,
            'GES_DEFHRSTEP':self.galil_command_handler,
            'GES_DEFLRSTEP':self.galil_command_handler,
            'GES_DEFHRENC':self.galil_command_handler,
            'GES_DEFLRENC':self.galil_command_handler,
            'GES_DEFTOL':self.galil_command_handler,
            'GES_DEFSWPSTEP':self.galil_command_handler,
            'GES_DEFSWPENC':self.galil_command_handler,
            'FILTER_DEFENC':self.galil_command_handler,
            'FILTER_DEFINS':self.galil_command_handler,
            'FILTER_DEFREM':self.galil_command_handler,
            'FILTER_DEFTOL':self.galil_command_handler,
            'FLSIM_DEFINS':self.galil_command_handler,
            'FLSIM_DEFREM':self.galil_command_handler,
            #Shack-Hartman Agent Commands
            #
            #The director passes the command along to the agent.
            #
            #Authoritative command discriptions are in shackhartmanAgent.py
            'SHLED':self.shackhartman_command_handler,
            'SHLENS':self.shackhartman_command_handler,
            #Guider Agent Commands
            #
            #The director passes the command along to the agent.
            #
            #Authoritative command discriptions are in guiderAgent.py
            'GFOCUS':self.guider_command_handler,
            'GFILTER':self.guider_command_handler,
            #Slit Commands
            #
            #The director passes the command along to the agent.
            #
            #Command discriptions are in slitController.py
            'SLITSRAW':self.SLITS_comand_handler,
            'SLITS':self.SLITS_comand_handler,
            'SLITS_CLOSEDLOOP':self.SLITS_comand_handler,
            'SLITS_SLITPOS':self.SLITS_comand_handler,
            'SLITS_CURRENTPOS':self.SLITS_comand_handler,
            'SLITS_ACTIVEHOLD':self.SLITS_comand_handler,
            'SLITS_MOVSTEPS':self.SLITS_comand_handler,
            'SLITS_HARDSTOP':self.SLITS_comand_handler,
            #Plugging Commands
            #
            #The director passes the command along to the agent.
            #
            #Command discriptions are in plugController.py
            'PLATELIST': self.PLUGGING_command_handler,
            'PLATE': self.PLUGGING_command_handler,
            'PLATESETUP': self.PLUGGING_command_handler,
            'PLUGPOS': self.PLUGGING_command_handler,
            #Datalogger Agent Commands
            #
            #The director passes the command along to the agent.
            #
            #Authoritative command discriptions are in dataloggerAgent.py
            'TEMPS':self.datalogger_command_handler})
    
    def listenOn(self):
        """
        Return an address tuple on which the server shall listen.
        
        Overrides the default localhost address as the director listens for 
        commands from the GUI
        """
        return (socket.gethostname(), self.PORT)

    def get_cli_help_string(self):
        """
        Return a brief help string describing the agent.
        
        Subclasses shuould override this to provide a description for the cli
        parser
        """
        return "This is the M2FS Director"

    def get_version_string(self):
        """ Return a string with the version."""
        return DIRECTOR_VERSION_STRING
    
    def guiclose_command_handler(self, command):
        """
        Handle the GUI telling the instrument it is closing
        
        Do nothing, what do we care
        """
        command.setReply('OK')
    
    def shutdown_command_handler(self, command):
        """
        Start instrument power down
        
        Initiate what Network UPS Tools calls a forced shutdown
        upsmon should start the norma systemd shutdown procedure
        and then, after systemd indicates ready to power off (which entails
        waiting for all agents to shutdown,
        instruct the UPS to kill the load, disabling power to the instrument.
        The instrument power button must be pressed to start it back
        TODO: TEST AND VERIFY FUNCTIONALITY
        """
        command.setReply('OK')
        os.system('upsmon -c fsd')
    
    def stowedshutdown_command_handler(self, command):
        """
        Enable/Disable/Query Stowed shutdown
        
        Default is set in __init__. If enabled, when the instrument is powered
        down, whether by the UPS or by user command every agent's
        _stowedShutdown hook will be called. If an individual agent is killed
        (barring SIGKILL) that agent will call its stowed shutdown hook. 
        """
        if '?' in command.string:
            command.setReply('ON' if m2fsConfig.doStowedShutdown() else 'OFF')
        elif 'ON' in command.string and 'OFF' not in command.string:
            m2fsConfig.enableStowedShutdown()
            command.setReply('OK')
        elif 'OFF' in command.string and 'ON' not in command.string:
            m2fsConfig.disableStowedShutdown()
            command.setReply('OK')
        else:
            self.bad_command_handler(command)
    
    def shackhartman_command_handler(self, command):
        """
        Handle commands for the Shack-Hartman system
        
        Pass the command string along to the SH agent. The response and error
        callbacks are the command's setReply function.
        """
        self.shackhatmanAgent_Connection.sendMessage(command.string,
            responseCallback=command.setReply, errorCallback=command.setReply)
    
    def SLITS_comand_handler(self, command):
        """
        Handle commands for the fiber slit system
        
        Pass the command string along to the slit controller agent. 
        The response callback is the command's setReply function.
        
        This routine implements the same functionality as
        shackhartman_command_handler, but in a different manner.
        Using the errorCallback is much cleaner and removes dependence on an
        additional function, but does not provide direct control over the error
        messages.
        """
        try:
            self.slitController_Connection.connect()
            self.slitController_Connection.sendMessage(command.string, 
                responseCallback=command.setReply)
        except SelectedConnection.ConnectError, err:
            command.setReply('ERROR: Could not establish a connection with the slit controller.')
        except SelectedConnection.WriteError, err:
            command.setReply('ERROR: Could not send to slit controller.')
    
    def datalogger_command_handler(self, command):
        """
        Handle commands for the datalogging system
        
        Pass the command string along to the datalogger agent.
        The response callback is the command's setReply function.
        
        This routine implements the same functionality as
        shackhartman_command_handler, but in a different manner.
        Using the errorCallback is much cleaner and removes dependence on an
        additional function, but does not provide direct control over the error
        messages.
        """
        try:
            self.dataloggerAgent_Connection.connect()
            self.dataloggerAgent_Connection.sendMessage(command.string, 
                responseCallback=command.setReply)
        except SelectedConnection.ConnectError, err:
            command.setReply('ERROR: Could not establish a connection with the datalogger agent.')
        except SelectedConnection.WriteError, err:
            command.setReply('ERROR: Could not send to datalogger agent.')
    
    def PLUGGING_command_handler(self, command):
        """
        Handle commands for the plugging system
        
        Pass the command string along to the plug controller agent.
        The response callback is the command's setReply function.
        
        This routine implements the same functionality as
        shackhartman_command_handler, but in a different manner.
        Using the errorCallback is much cleaner and removes dependence on an
        additional function, but does not provide direct control over the error
        messages.
        """
        try:
            self.plugController_Connection.connect()
            self.plugController_Connection.sendMessage(command.string, 
                responseCallback=command.setReply)
        except SelectedConnection.ConnectError, err:
            command.setReply('ERROR: Could not establish a connection with the plug controller.')
        except SelectedConnection.WriteError, err:
            command.setReply('ERROR: Could not send to plug controller.')
    
    def plugmode_command_handler(self, command):
        """
        Handle entering and exiting plug mode
        
        On entering we need to insert the FLS pickoff 'FLSIM IN' to each galil
        This takes 5-30 seconds and if it fails then we can't sucessfully enter
        plugmode. We then need to make sure that all slits are in a position 
        that is suitable for plugging, what constitutes suitable is unknown at
        present. Finally, notify the plugcontroller that it should start 
        checking fiber plug locations.
        
        On leaving plug mode we need to remove the FLS pickoff ('FLISM OUT' to
        both Galil agents). And perhaps reset the slit positions, which if
        closed loop control is enabled would require the pickoff to still be
        inserted.

        Considering the FLS system isn't yet operational, this command is 
        just a dummy to excersise the FLS Pickoffs
        """
        if '?' in command.string:
            #Check to see if we've made it into plug mode sucess
            reply='OFF'
            command.setReply(reply)
        elif 'OFF' in command.string and 'ON' not in command.string:
            #Turn plugmode off
            try:
                self.galilAgentR_Connection.sendMessage('FLSIM OUT')
                self.galilAgentR_Connection.sendMessage('FLSIM OUT')
                command.setReply('OK')
            except WriteError:
                command.setReply('ERROR: Could not set pickoff position')
        elif 'ON' in command.string and 'OFF' not in command.string:
            #Turn plugmode on
            try:
                self.galilAgentR_Connection.sendMessage('FLSIM IN')
                self.galilAgentR_Connection.sendMessage('FLSIM IN')
                command.setReply('OK')
            except WriteError:
                command.setReply('ERROR: Could not set pickoff position')
        else:
            self.bad_command_handler(command)

    def status_command_handler(self, command):
        """ 
        Report the status of all instrument subsystems 
        
        Return a '\r' delimited set of strings containing the results of STATUS 
        requests to each agent. If an agent doesnt respond report it's status as 
        unknown. TODO make the agent name reported meaningful to the end used.
        """
        reply='%s: %s/r' % (self.get_version_string(),self.cookie)
        for d in self.devices:
            try:
                d.sendMessageBlocking('STATUS')
                statusmsg=d.receiveMessageBlocking()+'\r'
                reply=reply+statusmsg
            except IOError:
                reply=reply+('%s: UNKNOWN\r' % d.addr_str())
        command.setReply(reply)
    
    def galil_command_handler(self, command):
        """ 
        Handle commands for either of the galils
            
        Pass the command string along to the appropriate galil agent.
        The response and error callbacks are the command's setReply function.
        
        Determine the appropriate galil agent by checking the second word in
        the command string if it is 'R' then GalilAgentR, if it is 'B' then 
        agent B. The command is considered bad if it is neither 'R' nor 'B'.
        """
        command_name,junk,args=command.string.partition(' ')
        RorB,junk,args=args.partition(' ')
        galil_command=command_name+' '+args
        if RorB =='R':
            self.galilAgentR_Connection.sendMessage(galil_command,
                responseCallback=command.setReply,
                errorCallback=command.setReply)
        elif RorB =='B':
            self.galilAgentB_Connection.sendMessage(galil_command,
                responseCallback=command.setReply,
                errorCallback=command.setReply)
        else:
            self.bad_command_handler(command)

    def guider_command_handler(self, command):
        """
        Handle commands for the guider system
        
        Pass the command string along to the guider agent.
        The response callback is the command's setReply function.
        
        This routine implements the same functionality as
        shackhartman_command_handler, but in a different manner.
        Using the errorCallback is much cleaner and removes dependence on an
        additional function, but does not provide direct control over the error
        messages.
        """
        try:
            self.guiderAgent_Connection.connect()
            self.guiderAgent_Connection.sendMessage(command.string,
                responseCallback=command.setReply)
        except SelectedConnection.ConnectError, err:
            command.setReply('ERROR: Could not establish a connection with the guider agent.')
        except SelectedConnection.WriteError, err:
            command.setReply('ERROR: Could not send to guider agent.')
    

if __name__=='__main__':
    director=Director()
    director.main()
