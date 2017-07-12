#!/usr/bin/env python2.7
import sys, socket, os, time
from threading import Timer
sys.path.append(sys.path[0]+'/../lib/')
from agent import Agent
import SelectedConnection
from m2fsConfig import m2fsConfig
import PyNUT

DIRECTOR_VERSION_STRING='Director v0.6'
LINUX_SHUTDOWN_COMMAND='shutdown now'
POLL_NUT_INTERVAL=15
MIN_UPS_RUNTIME=360
NUT_LOGIN="monitor"
NUT_PASSWORD="1"

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
        #Fetch the agent ports
        agent_ports=m2fsConfig.getAgentPorts()
        #Galil Agents
        self.connections['GalilAgentR']=SelectedConnection.SelectedSocket('localhost',
            agent_ports['GalilAgentR'])
        self.connections['GalilAgentB']=SelectedConnection.SelectedSocket('localhost',
            agent_ports['GalilAgentB'])
        #Slit Subsytem Controller
        self.connections['SlitController']=SelectedConnection.SelectedSocket('localhost',
            agent_ports['SlitController'])
        #Datalogger Agent
        self.connections['DataloggerAgent']=SelectedConnection.SelectedSocket('localhost',
            agent_ports['DataloggerAgent'])
        #Shack-Hartman Agent
        self.connections['ShackHartmanAgent']=SelectedConnection.SelectedSocket('localhost',
            agent_ports['ShackHartmanAgent'])
        #MCal Agent
        self.connections['MCalAgent']=SelectedConnection.SelectedSocket('localhost',
            agent_ports['MCalAgent'])
        #Plugging Controller
        self.connections['PlugController']=SelectedConnection.SelectedSocket('localhost',
            agent_ports['PlugController'])
        #Guider Agent
        self.connections['GuiderAgent']=SelectedConnection.SelectedSocket('localhost',
            agent_ports['GuiderAgent'])
        self.command_handlers.update({
            #Director Commands
            #
            #These commands operate on the entire instrument or require
            #coordinating a multiple systems.
            #
            #Notify the instrument the GUI is about to close """
            'GUICLOSING':self.guiclose_command_handler,
            #Shut the instrument down
            'SHUTDOWN':self.shutdown_command_handler,
            #Shut the instrument down, moving all axes to stowed positions
            'STOWEDSHUTDOWN': self.stowedshutdown_command_handler,
            #Enable/Disable plugging mode.
            #Involves GalilAgents, PlugController, & SlitController.
            'PLUGMODE': self.plugmode_command_handler,
            #Report the state of the cradles
            'CRADLESTATE': self.cradlestate_command_handler,
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
            #MCAL Agent Commands
            #
            #The director passes the command along to the agent.
            #
            #Authoritative command discriptions are in mcalAgent.py
            'MCLED':self.mcal_command_handler,
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
            'SLITS_MOVESTEPS':self.SLITS_comand_handler,
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
        #Ensure stawed shutdown is disabled by default
        m2fsConfig.disableStowedShutdown()
        self.batteryState=[('Battery','Unknown')]
        updateBatteryStateTimer=Timer(.1, self.updateBatteryState)
        updateBatteryStateTimer.daemon=True
        updateBatteryStateTimer.start()
    
    def listenOn(self):
        """
        Return an address tuple on which the server shall listen.
        
        Overrides the default localhost address as the director listens for 
        commands from the GUI
        """
        return ('', self.PORT)

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
    
    def _exitHook(self):
        self.store_system_logs()
    
    def store_system_logs(self):
        """
        Write the system logs to the log directory as a gzipped file
        
        file name is of the form 
        """
        logdir=m2fsConfig.getLogfileDir()
        datestr=time.strftime("%d.%b.%Y.%H.%M.%S", time.localtime(time.time()))
        logfile=logdir+datestr+'.log.gz'
        os.system('journalctl --this-boot | gzip > '+logfile)
    
    def shutdown_command_handler(self, command):
        """
        Start instrument power down
        
        Initiate what Network UPS Tools calls a forced shutdown
        upsmon should start the normal systemd shutdown procedure
        and then, after systemd indicates ready to power off (which entails
        waiting for all agents to shutdown,
        instruct the UPS to kill the load, disabling power to the instrument.
        The instrument power button must be pressed to start it back
        TODO: TEST AND VERIFY FUNCTIONALITY
        """
        m2fsConfig.disableStowedShutdown()
        command.setReply('OK')
        os.system(LINUX_SHUTDOWN_COMMAND)
    
    def stowedshutdown_command_handler(self, command):
        """
        Enable/Disable/Query Stowed shutdown
        
        Initiate what Network UPS Tools calls a forced shutdown
        upsmon should start the normal systemd shutdown procedure
        and then, after systemd indicates ready to power off (which entails
        waiting for all agents to shutdown,
        instruct the UPS to kill the load, disabling power to the instrument.
        The instrument power button must be pressed to start it back
        
        In addition the the stowed shutdown flag is set, which will result in
        every agent calling its _stowedShutdown hook as it shuts down.
        TODO: Test that power stays on for long enough for everything to close 
        out. TODO make sure the systemd timeouts for exiting agents are long 
        enough 
        """
        m2fsConfig.enableStowedShutdown()
        command.setReply('OK')
        os.system(LINUX_SHUTDOWN_COMMAND)
    
    def cradlestate_command_handler(self, command):
        """
        Report the state of the cradles
        
        """
        rstate='CRADLE_R='
        rcolor=m2fsConfig.getShoeColorInCradle('R')
        if rcolor:
            rstate+='SHOE_'+rcolor
        else:
            rstate+='NONE'
        bstate='CRADLE_B='
        bcolor=m2fsConfig.getShoeColorInCradle('B')
        if bcolor:
            bstate+='SHOE_'+bcolor
        else:
            bstate+='NONE'
        command.setReply('%s %s' % (rstate, bstate))
    
    def shackhartman_command_handler(self, command):
        """
        Handle commands for the Shack-Hartman system
        
        Pass the command string along to the SH agent. The response and error
        callbacks are the command's setReply function.
        """
        self.connections['ShackHartmanAgent'].sendMessage(command.string,
            responseCallback=command.setReply, errorCallback=command.setReply)
    
    def shackhartman_command_handler(self, command):
        """
        Handle commands for the MCal system
        
        Pass the command string along to the MCal agent. The response and error
        callbacks are the command's setReply function.
        """
        self.connections['MCalAgent'].sendMessage(command.string,
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
            self.connections['SlitController'].connect()
            self.connections['SlitController'].sendMessage(command.string, 
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
            self.connections['DataloggerAgent'].connect()
            self.connections['DataloggerAgent'].sendMessage(command.string, 
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
            self.connections['PlugController'].connect()
            self.connections['PlugController'].sendMessage(command.string, 
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
        
        TODO When this really matters I need to take into accout that the 
        FLSIM OUT and FLSIM IN commands might result in an ERROR, which I would
        need to trap a and handle. The most likely cause, which is also expected
        behavior would be to have the instrument be entering plugmode right as
        the gratings and disperser are being reconfigured, perhaps causing the
        galils to temporarily not have a free thread to execute FLSIM.
        The gracefull way to handle this is to queue the motions and only fail 
        to enter PLUGMODE if they don't complete after some timeout.
        Again given the current arch, this isn't straightforward to implement, 
        at least to me.
        """
        if '?' in command.string:
            #Check to see if we've made it into plug mode sucess
            reply='OFF'
            command.setReply(reply)
        else:
            command.setReply('ERROR: Not implemented')
#        elif 'OFF' in command.string and 'ON' not in command.string:
#            #Turn plugmode off
#            try:
#                self.connections['GalilAgentR'].sendMessage('FLSIM OUT')
#                self.connections['GalilAgentB'].sendMessage('FLSIM OUT')
#                command.setReply('OK')
#            except WriteError:
#                command.setReply('ERROR: Could not set pickoff position')
#        elif 'ON' in command.string and 'OFF' not in command.string:
#            #Turn plugmode on
#            try:
#                self.connections['GalilAgentR'].sendMessage('FLSIM IN')
#                self.connections['GalilAgentB'].sendMessage('FLSIM IN')
#                command.setReply('OK')
#            except WriteError:
#                command.setReply('ERROR: Could not set pickoff position')
#        else:
#            self.bad_command_handler(command)

    def get_status_list(self):
        """
        Report the status of all instrument subsystems
        
        Return a list of key:value pairs plus the status responses resulting
        from STATUS requests to each agent. If an agent doesnt respond report 
        it's status it is listed as Offline.
        TODO make the agent name reported meaningful to the end used.
        """
        status=[(self.get_version_string(),self.cookie)]
        #Get the battery backup state
        status.extend(self.batteryState)
        #Poll all the agents for their status
        for k, d in self.connections.items():
            if k.startswith('INCOMING'):
                continue
            agentName=m2fsConfig.nameFromAddrStr(d.addr_str())
            agentName=agentName.replace(':','_').replace(' ','_')
            try:
                d.sendMessageBlocking('STATUS')
                response=d.receiveMessageBlocking()
            except IOError:
                response='%s:Offline' % agentName
            if response=='':
                response='%s:Not_Responding' % agentName
            status.append(response)
        return status
    
    
    def updateBatteryState(self):
        #Get the current state of the UPS
        try:
            nut=PyNUT.PyNUTClient(login=NUT_LOGIN, password=NUT_PASSWORD)
            upsstate=nut.GetUPSVars('myups')
            batteryState=[('Battery',upsstate['ups.status']),
                               ('Runtime(s)',upsstate['battery.runtime'])]
        except Exception:
            batteryState=[('Battery','Faild to query NUT for status')]
        #self.logger.info(' '.join(['{}:{}'.format(x,y) for x,y in batteryState]))
        if len(batteryState)==2:
            if int(batteryState[1][1])<MIN_UPS_RUNTIME:
                os.system(LINUX_SHUTDOWN_COMMAND)
                return
        self.batteryState=batteryState
        #Do it again in in a few
        updateBatteryStateTimer=Timer(POLL_NUT_INTERVAL, self.updateBatteryState)
        updateBatteryStateTimer.daemon=True
        updateBatteryStateTimer.start()
    
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
            self.connections['GalilAgentR'].sendMessage(galil_command,
                responseCallback=command.setReply,
                errorCallback=command.setReply)
        elif RorB =='B':
            self.connections['GalilAgentB'].sendMessage(galil_command,
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
            self.connections['GuiderAgent'].connect()
            self.connections['GuiderAgent'].sendMessage(command.string,
                responseCallback=command.setReply)
        except SelectedConnection.ConnectError, err:
            command.setReply('ERROR: Could not establish a connection with the guider agent.')
        except SelectedConnection.WriteError, err:
            command.setReply('ERROR: Could not send to guider agent.')
    

if __name__=='__main__':
    director=Director()
    director.main()
