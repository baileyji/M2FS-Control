#!/usr/bin/python
import sys, time, socket
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
            agent_ports['GalilAgentR'], self.logger)
        self.devices.append(self.galilAgentR_Connection)
        self.galilAgentB_Connection=SelectedConnection.SelectedSocket('localhost',
            agent_ports['GalilAgentB'], self.logger)
        self.devices.append(self.galilAgentB_Connection)
        #Slit Subsytem Controller
        self.slitController_Connection=SelectedConnection.SelectedSocket('localhost',
            agent_ports['SlitController'], self.logger)
        self.devices.append(self.slitController_Connection)
        #Datalogger Agent
        self.dataloggerAgent_Connection=SelectedConnection.SelectedSocket('localhost',
            agent_ports['DataloggerAgent'], self.logger)
        self.devices.append(self.dataloggerAgent_Connection)
        #Shack-Hartman Agent
        self.shackhatmanAgent_Connection=SelectedConnection.SelectedSocket('localhost',
            agent_ports['ShackHartmanAgent'], self.logger)
        self.devices.append(self.shackhatmanAgent_Connection)
        #Plugging Controller
        self.plugController_Connection=SelectedConnection.SelectedSocket('localhost',
            agent_ports['PlugController'], self.logger)
        self.devices.append(self.plugController_Connection)
        self.command_handlers.update({

            #Galil Agent Commands
            'GALILRAW':self.galil_command_handler,
            'GES':self.galil_command_handler,
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
            #Shack Hartman Commands
            'SHLED':self.shackhartman_command_handler,
            'SHLENS':self.shackhartman_command_handler,
            #Slit Commands
            'SLITS':self.SLITS_comand_handler,
            'SLITS_CLOSEDLOOP':self.SLITS_comand_handler,
            'SLITS_SLITPOS':self.SLITS_comand_handler,
            'SLITS_CURRENTPOS':self.SLITS_comand_handler,
            'SLITS_ACTIVEHOLD':self.SLITS_comand_handler,
            'SLITS_MOVSTEPS':self.SLITS_comand_handler,
            'SLITS_HARDSTOP':self.SLITS_comand_handler,
            #Plugging commands
            'PLATELIST': self.PLATELIST_command_handler,
            'PLATE': self.PLATE_command_handler,
            'PLATESETUP': self.PLATESETUP_command_handler,
            'PLUGPOS': self.PLUGPOS_command_handler,
            'PLUGMODE': self.PLUGMODE_command_handler,
            #Datalogger Commands
            'TEMPS':self.datalogger_command_handler})
    
    def listenOn(self):
        return (socket.gethostname(), self.PORT)
    
    def get_version_string(self):
        return 'Director Version 0.1'    
      
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
            try:
                self.plugController_Connection.connect()
                self.plugController_Connection.sendMessage(command.string, 
                    responseCallback=command.setReply)
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
        reply=self.cookie+' '
        for d in self.devices:
            try:
                d.sendMessageBlocking('STATUS')
                statusmsg=d.receiveMessageBlocking()
                reply=reply+statusmsg
            except IOError:
                reply=reply+('%s:UNKNOWN' % d.prettyname)
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
