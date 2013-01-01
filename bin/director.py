#!/usr/bin/env python2.7
import sys, time, socket, os
sys.path.append(sys.path[0]+'/../lib/')
from agent import Agent
import SelectedConnection
from command import Command
from m2fsConfig import m2fsConfig

class Director(Agent):
    def __init__(self):
        Agent.__init__(self,'Director')
        self.max_clients=1
        agent_ports=m2fsConfig.getAgentPorts()
        #Galil Agents
        self.galilAgentR_Connection=SelectedConnection.SelectedSocket('localhost',
            agent_ports['GalilAgentR'])
        self.devices.append(self.galilAgentR_Connection)
        self.galilAgentB_Connection=SelectedConnection.SelectedSocket('localhost',
            agent_ports['GalilAgentB'])
        self.devices.append(self.galilAgentB_Connection)
        #Slit Subsytem Controller
        self.slitController_Connection=SelectedConnection.SelectedSocket('localhost',
            agent_ports['SlitController'])
        self.devices.append(self.slitController_Connection)
        #Datalogger Agent
        self.dataloggerAgent_Connection=SelectedConnection.SelectedSocket('localhost',
            agent_ports['DataloggerAgent'])
        self.devices.append(self.dataloggerAgent_Connection)
        #Shack-Hartman Agent
        self.shackhatmanAgent_Connection=SelectedConnection.SelectedSocket('localhost',
            agent_ports['ShackHartmanAgent'])
        self.devices.append(self.shackhatmanAgent_Connection)
        #Plugging Controller
        self.plugController_Connection=SelectedConnection.SelectedSocket('localhost',
            agent_ports['PlugController'])
        self.devices.append(self.plugController_Connection)
        self.command_handlers.update({
            #Director Commands
            """ Notify the instrument the GUI is about to close """
            'GUICLOSING':self.guiclose_command_handler,
            """ Move all systems to stowage positions and power off """
            'SHUTDOWN':self.shutdown_command_handler,
            """
            Galil Agent (R & B) Commands
            
            The director determines if the command is for the R or B galilAgent
            and then passes it along to the agent.
            
            Authoritative command discriptions are in galilAgent.py
            """
            'GALILRAW':self.galil_command_handler,
            'GES':self.galil_command_handler,
            'GES_MOVE':self.galil_command_handler
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
            'FLSIM_INSERT':self.galil_command_handler,
            'FLSIM_REMOVE':self.galil_command_handler,
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
            """
            Shack-Hartman Agent Commands

            The director passes the command along to the agent.

            Authoritative command discriptions are in shackhartmanAgent.py
            """
            'SHLED':self.shackhartman_command_handler,
            'SHLENS':self.shackhartman_command_handler,
            """
            Guider Agent Commands

            The director passes the command along to the agent.

            Authoritative command discriptions are in guiderAgent.py
            """
            'GFOCUS':self.not_implemented_command_handler,
            'GFILTER':self.not_implemented_command_handler,
            """
            Slit Commands

            The director passes the command along to the agent.

            Command discriptions are in slitController.py
            """
            'SLITS':self.SLITS_comand_handler,
            'SLITS_CLOSEDLOOP':self.SLITS_comand_handler,
            'SLITS_SLITPOS':self.SLITS_comand_handler,
            'SLITS_CURRENTPOS':self.SLITS_comand_handler,
            'SLITS_ACTIVEHOLD':self.SLITS_comand_handler,
            'SLITS_MOVSTEPS':self.SLITS_comand_handler,
            'SLITS_HARDSTOP':self.SLITS_comand_handler,
            """
            Plugging Commands

            The director passes the command along to the agent.

            Command discriptions are in plugController.py
            """
            'PLATELIST': self.PLUGGING_command_handler,
            'PLATE': self.PLUGGING_command_handler,
            'PLATESETUP': self.PLUGGING_command_handler,
            'PLUGPOS': self.PLUGGING_command_handler,
            'PLUGMODE': self.PLUGGING_command_handler,
            """
            Datalogger Agent Commands

            The director passes the command along to the agent.

            Authoritative command discriptions are in dataloggerAgent.py
            """
            'TEMPS':self.datalogger_command_handler})
    
    def listenOn(self):
        return (socket.gethostname(), self.PORT)
    
    def get_version_string(self):
        return 'Director Version 0.1'
    
    def guiclose_command_handler(self, command):#TODO
        command.setReply('OK')
    
    def shutdown_command_handler(self, command):#TODO
        """
        Start instrument power down
        
        init computer shutdown procedure and then systemd notify individual
        agents. I prefer this path, but it would be prefered that 
        agents distinguish between a manual systemctl stop/kill/restart and a
        shutdown now
        
        """
        command.setReply('OK')
        os.system('upsmon -c fsd')
    
    def shackhartman_command_handler(self, command):
        try:
            self.shackhatmanAgent_Connection.connect()
            self.shackhatmanAgent_Connection.sendMessage(command.string,
            responseCallback=command.setReply)
        except SelectedConnection.ConnectError, err:
            command.setReply('ERROR: Could not establish a connection with the shackhartman agent.')
        except SelectedConnection.WriteError, err:
            command.setReply('ERROR: Could not send to ShackHartman agent.')
    
    def SLITS_comand_handler(self, command):
        try:
            self.slitController_Connection.connect()
            self.slitController_Connection.sendMessage(command.string, 
                responseCallback=command.setReply)
        except SelectedConnection.ConnectError, err:
            command.setReply('ERROR: Could not establish a connection with the slit controller.')
        except SelectedConnection.WriteError, err:
            command.setReply('ERROR: Could not send to slit controller.')
    
    def datalogger_command_handler(self, command):
        try:
            self.dataloggerAgent_Connection.connect()
            self.dataloggerAgent_Connection.sendMessage(command.string, 
                responseCallback=command.setReply)
        except SelectedConnection.ConnectError, err:
            command.setReply('ERROR: Could not establish a connection with the datalogger agent.')
        except SelectedConnection.WriteError, err:
            command.setReply('ERROR: Could not send to datalogger agent.')
    
    def PLUGGING_command_handler(self, command):
        """ Pass Plugging related commands along and coordinate multi-system
           actions """
        command_name,_,args=command.string.partition(' ')
        if command_name in ['PLATELIST', 'PLATE','PLATESETUP','PLUGPOS']:
            def callback(junk,reply):
                command.setReply(reply+'\n')
            try:
                self.plugController_Connection.connect()
                self.plugController_Connection.sendMessage(command.string, 
                    responseCallback=callback)
            except SelectedConnection.ConnectError, err:
                command.setReply('ERROR: Could not establish a connection with the plug controller.')
            except SelectedConnection.WriteError, err:
                command.setReply('ERROR: Could not send to plug controller.')
        elif command_name =='PLUGMODE':
            self.not_implemented_command_handler(command)
        else:
            command.setReply(
                "ERROR: PLUGGING_command_handler should not have been called for '%s'" % command.string)
    
    def status_command_handler(self, command):
        #TODO Query each subsystem for status
        reply=self.cookie+'\r'
        for d in self.devices:
            try:
                d.sendMessageBlocking('STATUS')
                statusmsg=d.receiveMessageBlocking()+'\r'
                reply=reply+statusmsg
            except IOError:
                reply=reply+('\r%s:UNKNOWN' % d.addr_str())+'\r'
        command.setReply(reply)
    
    def galil_command_handler(self, command):
        """ Galil command handler """
        command_name,junk,args=command.string.partition(' ')
        RorB,junk,args=args.partition(' ')
        if command_name[0:3]=='RAW':
            galil_command='RAW'+args
        else:
            galil_command=command_name+' '+args
        if RorB =='R':
            self.galilAgentR_Connection.sendMessage(galil_command, responseCallback=command.setReply,
                errorCallback=command.setReply)
        elif RorB =='B':
            self.galilAgentB_Connection.sendMessage(galil_command, responseCallback=command.setReply,
                errorCallback=command.setReply)
        else:
            self.bad_command_handler(command)


if __name__=='__main__':
    director=Director()
    director.main()
