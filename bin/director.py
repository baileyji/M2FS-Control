#!/usr/bin/env python2.7
import sys, socket, os, time
from threading import Timer
sys.path.append(sys.path[0]+'/../lib/')
from agent import Agent
import SelectedConnection
from m2fsConfig import m2fsConfig
import PyNUT

DIRECTOR_VERSION_STRING='Director v0.7'
LINUX_SHUTDOWN_COMMAND='shutdown now'
POLL_NUT_INTERVAL=15
MIN_UPS_RUNTIME=360
NUT_LOGIN="monitor"
NUT_PASSWORD="1"

# TODOsave resources by making sure systemd selectively starts based on UDEV creation or some such

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
        GENERAL_COMMANDS = {
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
            #Report the state of the cradles
            'CRADLESTATE': self.cradlestate_command_handler,
            #Command switch between M2FS and IFUM
            'MODE': self.instrumentmode_command_handler,
            #Galil Agent (R & B) Commands
            #
            #The director determines if the command is for the R or B galilAgent
            #and then passes it along to the agent.
            #
            #Authoritative command descriptions are in galilAgent.py
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
            'FILTER_MOVE':self.galil_command_handler,
            'FLSIM':self.galil_command_handler,
            'FLSIM_INSERT':self.galil_command_handler,
            'FLSIM_REMOVE':self.galil_command_handler,
            'FLSIM_MOVE':self.galil_command_handler,
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
            # MCAL Agent Commands
            #
            # The director passes the command along to the agent.
            #
            # Authoritative command descriptions are in mcalAgent.py
            'MCLED': self.mcal_command_handler,
            # Datalogger Agent Commands
            #
            # The director passes the command along to the agent.
            #
            # Authoritative command descriptions are in dataloggerAgent.py
            'TEMPS': self.datalogger_command_handler}
        self.M2FS_COMMANDS = {
            # Enable/Disable plugging mode.
            # Involves GalilAgents, PlugController, & SlitController.
            'PLUGMODE': self.plugmode_command_handler,
            #Shack-Hartman Agent Commands
            #
            #The director passes the command along to the agent.
            #
            #Authoritative command descriptions are in shackhartmanAgent.py
            'SHLED':self.shackhartman_command_handler,
            'SHLENS':self.shackhartman_command_handler,
            #Guider Agent Commands
            #
            #The director passes the command along to the agent.
            #
            #Authoritative command descriptions are in guiderAgent.py
            'GFOCUS':self.guider_command_handler,
            'GFILTER':self.guider_command_handler,
            #Slit Commands
            #
            #The director passes the command along to the agent.
            #
            #Command descriptions are in slitController.py
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
            #Command descriptions are in plugController.py
            'PLATELIST':self.PLUGGING_command_handler,
            'PLATE':self.PLUGGING_command_handler,
            'PLATESETUP':self.PLUGGING_command_handler,
            'PLUGPOS':self.PLUGGING_command_handler}
        self.IFUM_COMMANDS = {
            'IFU':self.IFU_command_handler,
            'IFU_MOVE':self.IFU_command_handler,

            'OCC':self.OCCULTER_command_handler,
            'OCC_STEP':self.OCCULTER_command_handler,
            'OCC_CALIBRATE':self.OCCULTER_command_handler,
            'OCCRAW':self.OCCULTER_command_handler,

            'SLITRAW': self.SLITS_comand_handler,
            'SLIT': self.SLITS_comand_handler,

            'BeNeAr':self.IFUSHIELD_command_handler,
            'LiHe':self.IFUSHIELD_command_handler,
            'ThXe':self.IFUSHIELD_command_handler}
        self.command_handlers.update(GENERAL_COMMANDS)
        self.command_handlers.update(self.M2FS_COMMANDS)
        self.command_handlers.update(self.IFUM_COMMANDS)

        #Fetch the agent ports
        agent_ports=m2fsConfig.getAgentPorts()
        #Galil Agents
        self.connections['GalilAgentR']=SelectedConnection.SelectedSocket('localhost', agent_ports['GalilAgentR'])
        self.connections['GalilAgentB']=SelectedConnection.SelectedSocket('localhost', agent_ports['GalilAgentB'])
        #Datalogger Agent
        self.connections['DataloggerAgent']=SelectedConnection.SelectedSocket('localhost',
                                                                              agent_ports['DataloggerAgent'])
        #MCal Agent
        self.connections['MCalAgent']=SelectedConnection.SelectedSocket('localhost', agent_ports['MCalAgent'])

        #TODO How do we deal with this if nothing is installed? Restart director on insert of device?

        #Agents are started by their devices (but not stopped by removing their devices, TODO perhaps they should be)
        # We default to M2FS mode, If MFib isn't hooked up then won't be able to connect to the MFib agents, but will
        # retry auto-magically as connections exist. If IFU-M is later connected (e.g. IFU-M installed, forgot to
        # connect USB before boot) MFib agents would never get started and IFU-M agents would be running.
        # MODE will trigger _enterIFUMode() or _enterM2FSMode(), failing would fail if the other is connected.
        # If MODE is issued before anything is connected it will switch.
        if m2fsConfig.ifum_devices_present():
            self._enterIFUMode()
        else:
            self._enterM2FSMode()

        #Ensure stowed shutdown is disabled by default
        m2fsConfig.disableStowedShutdown()
        self.batteryState = [('Battery', 'Unknown')]
        updateBatteryStateTimer = Timer(2.5, self.updateBatteryState)
        updateBatteryStateTimer.daemon = True
        updateBatteryStateTimer.start()

    def _enterM2FSMode(self):
        """
        This will leave any IFUM only commands in flight with no way to query them. If they are blocking their
        blocks would remain forever.
        """
        agent_ports = m2fsConfig.getAgentPorts()
        for k in self.IFUM_COMMANDS:
            self.command_handlers[k] = self.NOT_IFUM_command_handler
        self.command_handlers.update(self.M2FS_COMMANDS)
        # Plugging Controller
        self.connections['PlugController'] = SelectedConnection.SelectedSocket('localhost',
                                                                               agent_ports['PlugController'])
        # Guider Agent
        self.connections['GuiderAgent'] = SelectedConnection.SelectedSocket('localhost',
                                                                            agent_ports['GuiderAgent'])
        # Shack-Hartman Agent
        self.connections['ShackHartmanAgent'] = SelectedConnection.SelectedSocket('localhost',
                                                                                  agent_ports['ShackHartmanAgent'])
        # Slit Subsytem Controller
        self.connections['SlitController'] = SelectedConnection.SelectedSocket('localhost',
                                                                               agent_ports['SlitController'])
        for c in ('SelectorAgent','OcculterAgentS','OcculterAgentH','OcculterAgentL','IFUShieldAgent','IFUShoeAgent'):
            try:
                self.connections.pop(c).close()
            except KeyError:
                pass
            except IOError:
                self.logger.info("Failed to close connection to {} when switching to IFU Mode".format(c), exc_info=True)
        self.active_mode = 'm2fs'

    def _enterIFUMode(self):
        """
        This will leave any M2FS only commands in flight with no way to query them. If they are blocking their
        blocks would remain forever.
        """
        agent_ports = m2fsConfig.getAgentPorts()
        for k in self.M2FS_COMMANDS:
            self.command_handlers[k] = self.NOT_M2FS_command_handler
        self.command_handlers.update(self.IFUM_COMMANDS)
        #IFU Selector
        self.connections['SelectorAgent']=SelectedConnection.SelectedSocket('localhost', agent_ports['SelectorAgent'])
        #Occulter Controllers
        self.connections['OcculterAgentH']=SelectedConnection.SelectedSocket('localhost', agent_ports['OcculterAgentH'])
        self.connections['OcculterAgentS']=SelectedConnection.SelectedSocket('localhost', agent_ports['OcculterAgentS'])
        self.connections['OcculterAgentL']=SelectedConnection.SelectedSocket('localhost', agent_ports['OcculterAgentL'])
        #IFU Shield (LEDs, Lamps, & Temps)
        self.connections['IFUShieldAgent']=SelectedConnection.SelectedSocket('localhost', agent_ports['IFUShieldAgent'])
        # Slit Subsystem Controller
        self.connections['IFUShoeAgent']=SelectedConnection.SelectedSocket('localhost', agent_ports['IFUShoeAgent'])
        for c in ('PlugController','GuiderAgent','ShackHartmanAgent','SlitController'):
            try:
                self.connections.pop(c).close()
            except KeyError:
                pass
            except IOError:
                self.logger.info("Failed to close connection to {} when switching to IFU Mode".format(c), exc_info=True)
        self.active_mode = 'ifum'

    def NOT_IFUM_command_handler(self, command):
        command.setReply('ERROR: Command only supported in IFU-M mode.')

    def NOT_M2FS_command_handler(self, command):
        command.setReply('ERROR: Command only supported in M2FS mode.')

    def instrumentmode_command_handler(self, command):
        if '?' in command.string:
            command.setReply('IFU-M' if self.active_mode=='ifum' else 'M2FS')
            return
        cmd=command.string.lower()
        if ('ifum' in cmd and 'm2fs' in cmd) or ('ifum' not in cmd and 'm2fs' not in cmd):
            command.setReply('ERROR: Options are IFUM or M2FS')
            return
        if len(self.commands) != 1:
            command.setReply('ERROR: Mode setting not allowed due to pending commands.')
            return
        if 'ifum' in cmd:
            if m2fsConfig.m2fs_devices_present():
                command.setReply('ERROR: MFib is connected.')
            else:
                self._enterIFUMode()
                command.setReply('OK')
        else:
            if m2fsConfig.ifum_devices_present():
                command.setReply('ERROR: IFU-M is connected.')
            else:
                self._enterM2FSMode()
                command.setReply('OK')

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
        """
        m2fsConfig.enableStowedShutdown()
        command.setReply('OK')
        os.system(LINUX_SHUTDOWN_COMMAND)
    
    def cradlestate_command_handler(self, command):
        """
        Report the state of the cradles
        
        """
        rcolor=m2fsConfig.getShoeColorInCradle('R')
        bcolor=m2fsConfig.getShoeColorInCradle('B')
        rstate='CRADLE_R='
        rstate+='SHOE_'+rcolor if rcolor else 'NONE'
        bstate='CRADLE_B='
        bstate+='SHOE_' + bcolor if bcolor else 'NONE'
        command.setReply('%s %s' % (rstate, bstate))
    
    def shackhartman_command_handler(self, command):
        """
        Handle commands for the Shack-Hartman system
        
        Pass the command string along to the SH agent. The response and error
        callbacks are the command's setReply function.
        """
        self.connections['ShackHartmanAgent'].sendMessage(command.string,
            responseCallback=command.setReply, errorCallback=command.setReply)
    
    def mcal_command_handler(self, command):
        """
        Handle commands for the MCal system
        
        In M2FS mode pass the command string along to the MCal agent. The response and error
        callbacks are the command's setReply function.

        In IFUM mode the command is passed on to the IFUShieldAgent instead.
        """
        if self.active_mode=='ifum':
            self.connections['IFUShieldAgent'].sendMessage(command.string, responseCallback=command.setReply,
                                                           errorCallback=command.setReply)
        else:
            self.connections['MCalAgent'].sendMessage(command.string, responseCallback=command.setReply,
                                                      errorCallback=command.setReply)

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
        if self.active_mode=='ifum':
            self.connections['IFUShoeAgent'].sendMessage(command.string, responseCallback=command.setReply,
                                                         errorCallback=command.setReply)
        else:
            self.connections['SlitController'].sendMessage(command.string, errorCallback=command.setReply,
                                                           responseCallback=command.setReply)

    def IFU_command_handler(self, command):
        """
        Handle commands for the IFU selector system

        Pass the command string along to the selector controller agent. The response and error
        callbacks are the command's setReply function.
        """
        self.connections['SelectorAgent'].sendMessage(command.string,
            responseCallback=command.setReply, errorCallback=command.setReply)

    def OCCULTER_command_handler(self, command):
        """
        Handle commands for the OCCulters selector system

        Pass the command string along to the appropriate occulter agent. The response and error
        callbacks are the command's setReply function.

        Determine the appropriate agent by checking the second word in
        the command string if it is 'H' 'S' or 'L'. The command is considered bad if it is
        not one of those three.
        """
        command_name,_,args=command.string.partition(' ')
        HSL,_,args=args.partition(' ')
        HSL=HSL.upper()
        occulter_command=command_name+' '+args
        if HSL not in ('H', 'S', 'L'):
            self.bad_command_handler(command)
        self.connections['OcculterAgent'+HSL].sendMessage(occulter_command,
            responseCallback=command.setReply, errorCallback=command.setReply)

    def IFUSHIELD_command_handler(self, command):
        """
        Handle commands for the IFUShield (lamp controller)

        Pass the command string along to the IFUShield agent. The response and error
        callbacks are the command's setReply function.
        """
        self.connections['IFUShieldAgent'].sendMessage(command.string,
            responseCallback=command.setReply, errorCallback=command.setReply)

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
            self.connections['DataloggerAgent'].sendMessage(command.string, responseCallback=command.setReply)
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
        
        TODO When this really matters I need to take into account that the
         FLSIM OUT and FLSIM IN commands might result in an ERROR, which I would
         need to trap a and handle. The most likely cause, which is also expected
         behavior would be to have the instrument be entering plugmode right as
         the gratings and disperser are being reconfigured, perhaps causing the
         galils to temporarily not have a free thread to execute FLSIM.
         The graceful way to handle this is to queue the motions and only fail
         to enter PLUGMODE if they don't complete after some timeout.
         Again given the current arch, this isn't straightforward to implement.
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
            batteryState=[('Battery','Failed to query NUT for status')]
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
