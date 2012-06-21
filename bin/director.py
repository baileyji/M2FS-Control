#!/opt/local/bin/python2.7
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
        self.command_handlers={
            'RAWGALIL':self.galil_command_handler,
            'LREL':self.galil_command_handler,
            'HREL':self.galil_command_handler,
            'HRAZ':self.galil_command_handler,
            'FOCUS':self.galil_command_handler,
            'GES':self.galil_command_handler,
            'FILTER':self.galil_command_handler,
            'SHLED':self.shackhartman_command_handler,
            'SHLENS':self.shackhartman_command_handler,
            'SLITS':self.SLITS_comand_handler,
            'SLITS_CLOSEDLOOP':self.SLITS_comand_handler,
            'SLITS_SLITPOS':self.SLITS_comand_handler,
            'SLITS_CURRENTPOS':self.SLITS_comand_handler,
            'SLITS_ILLUMPROF':self.SLITS_comand_handler,
            'SLITS_ILLUMMEAS':self.SLITS_comand_handler,
            'SLITS_ACTIVEHOLD':self.SLITS_comand_handler,
            'SLITS_MOVSTEPS':self.SLITS_comand_handler,
            'SLITS_HARDSTOP':self.SLITS_comand_handler,
            'SLITS_IMAGSET':self.SLITS_comand_handler,
            'SLITS_PROJSET':self.SLITS_comand_handler,
            'SLITS_STATUS':self.SLITS_comand_handler,
            'SLITS_VERSION':self.SLITS_comand_handler,
            'PLUGMODE':self.not_implemented_command_handler,
            'PLUGPOS':self.not_implemented_command_handler,
            'PLATELIST':self.plateConfig_command_handler,
            'PLATE':self.plateConfig_command_handler,
            'PLATESETUP':self.plateConfig_command_handler,
            'TEMPS':self.datalogger_command_handler,
            'STATUS':self.status_command_handler,
            'VERSION':self.version_request_command_handler}
    
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
        
    def status_command_handler(self, command):
        #TODO Query each subsystem for status
        command.setReply('Doing just fine')
    
    def plateConfig_command_handler(self, command):
        self.not_implemented_command_handler(command)

    def galil_command_handler(self, command):
        """ Galil command handler """
        command_name,junk,args=command.string.partition(' ')
        RorB,junk,args=args.partition(' ')
        if command_name[0:3]=='RAW':
            galil_command='RAW'+args
        else:
            galil_command=command_name+' '+args
        if RorB =='R':
            if not self.galilAgentR_Connection.isOpen():
                try:
                    self.galilAgentR_Connection.connect()
                except socket.error, err:
                    command.setReply('!ERROR: Could not establish a connection with the galil agent.')
            if self.galilAgentR_Connection.isOpen():
                self.galilAgentR_Connection.sendMessage(galil_command, responseCallback=command.setReply)
        elif RorB =='B':
            self.galilAgentB_Connection.sendMessage(galil_command, responseCallback=command.setReply)
        else:
            self.bad_command_handler(command)


if __name__=='__main__':
    director=Director()
    director.main()
