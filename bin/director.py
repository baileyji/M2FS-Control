#!/opt/local/bin/python2.7
from agent import Agent
import socket
import time
import select
from SelectedSocket import SelectedSocket
from command import Command
from m2fsConfig import m2fsConfig

class Director(Agent):
    def __init__(self):
        Agent.__init__(self,'M2FS Interface')
        self.max_clients=1
        self.agent_ports=m2fsConfig.getAgentPorts()
        #Galil Agents
        self.galilAgentR_Connection=SelectedSocket('localhost',
            agent_ports['galilR'], self.logger)
        self.devices.append(self.galilAgentR_Connection)
        self.galilAgentB_Connection=SelectedSocket('localhost',
            agent_ports['galilB'], self.logger)
        self.devices.append(self.galilAgentB_Connection)
        #Datalogger Agent
        self.dataloggerAgent_Connection=SelectedSocket('localhost',
            agent_ports['datalogger'], self.logger)
        self.devices.append(self.dataloggerAgent_Connection)
        #Shack-Hartman Agent
        self.shackhatmanAgent_Connection=SelectedSocket('localhost',
            agent_ports['shackhatman'], self.logger)
        self.devices.append(self.shackhatmanAgent_Connection)
        
    
    def listenOn(self):
        if self.PORT:
            return (socket.gethostname(), self.PORT)
        else:
            return (socket.gethostname(), m2fsConfig.getDirectorPort())
            
    def get_version_string(self):
        return 'Director Version 0.1'    
    
    def socket_message_recieved_callback(self, source, message_str):
        """Dispatch message to from the appropriate handler"""
        command_handlers={
            'RAWGALIL':self.galil_command_handler,
            'LREL':self.galil_command_handler,
            'HREL':self.galil_command_handler,
            'HRAZ':self.galil_command_handler,
            'FOCUS':self.galil_command_handler,
            'GES':self.galil_command_handler,
            'FILTER':self.galil_command_handler,
            'SHLED':self.shackhartman_command_handler,
            'SHLENS':self.shackhartman_command_handler,
            'SLITS':self.not_implemented_command_handler,
            'PLUGMODE':self.not_implemented_command_handler,
            'PLUGPOS':self.not_implemented_command_handler,
            'PLATELIST':self.plateConfig_command_handler,
            'PLATE':self.plateConfig_command_handler,
            'PLATESETUP':self.plateConfig_command_handler,
            'TEMPS':self.datalogger_command_handler,
            'STATUS':self.status_command_handler,
            'VERSION':self.version_request_command_handler}
        command_class=message_str.partition(' ')[0].partition('_')[0]
        command=Command(source,message_str)
        if not filter(lambda x: x.source==source, self.commands):
            self.commands.append(command)
            command_handlers.get(command_class.upper(), self.bad_command_handler)(command)
    
    def shackhartman_command_handler(self, command):
        def onReply(source, reply):
            command.state='complete'
            command.reply=reply+'\n'
        if not self.shackhatmanAgent_Connection.isOpen():
            try:
                self.shackhatmanAgent_Connection.connect()
                self.shackhatmanAgent_Connection.sendMessage(command.string, responseCallback=onReply)
            except socket.error, err:
                command.state='complete'
                command.reply='!ERROR: Could not establish a connection with the shackhartman agent.\n'

    def datalogger_command_handler(self, command):
        def onReply(source, reply):
            command.state='complete'
            command.reply=reply+'\n'
        if not self.dataloggerAgent_Connection.isOpen():
            try:
                self.dataloggerAgent_Connection.connect()
                self.dataloggerAgent_Connection.sendMessage(command.string, responseCallback=onReply)
            except socket.error, err:
                command.state='complete'
                command.reply='!ERROR: Could not establish a connection with the datalogger agent.\n'
        
    def status_command_handler(self, command):
        #TODO Query each subsystem for status
        command.state='complete'
        command.reply='Doing just fine\n'

    def galil_command_handler(self, command):
        """ Galil command handler """
        command_name,junk,args=command.string.partition(' ')
        RorB,junk,args=args.partition(' ')
        if command_name[0:3]=='RAW':
            galil_command='RAW'+args
        else:
            galil_command=command_name+' '+args
        if RorB =='R':
            def onReply(source, reply):
                command.state='complete'
                command.reply=reply+'\n'
            if not self.galilAgentR_Connection.isOpen():
                try:
                    self.galilAgentR_Connection.connect()
                except socket.error, err:
                    command.state='complete'
                    command.reply='!ERROR: Could not establish a connection with the galil agent.\n'
            if self.galilAgentR_Connection.isOpen():
                self.galilAgentR_Connection.sendMessage(galil_command, responseCallback=onReply)
        elif RorB =='B':
            def onReply(source, reply):
                command.state='complete'
                command.reply=reply+'\n'
            self.galilAgentB_Connection.sendMessage(galil_command, responseCallback=onReply)
        else:
            self.bad_command_handler(command)


if __name__=='__main__':
    director=Director()
    director.main()
