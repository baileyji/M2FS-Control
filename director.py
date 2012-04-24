#!/opt/local/bin/python2.7
from agent import Agent
import socket
import time
import select
from SelectedSocket import SelectedSocket
from command import Command

MAX_CLIENTS=2
VERSION_STRING='0.1'
GALIL_AGENT_R_PORT=40000
GALIL_AGENT_B_PORT=45000
class Director(Agent):
    def __init__(self):
        Agent.__init__(self,'M2FS Interface')
        self.max_clients=2
        self.galilAgentR_Connection=SelectedSocket('localhost',GALIL_AGENT_R_PORT, self.logger)
        self.devices.append(self.galilAgentR_Connection)
        #self.galilAgentB_Connection=ThreadedSocket('localhost',GALIL_AGENT_B_PORT)
    
    def listenOn(self):
        return (socket.gethostname(), self.PORT)
        
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
            'SLITS':self.not_implemented_handler,
            'SHLED':self.not_implemented_handler,
            'SHLENS':self.not_implemented_handler,
            'PLUGMODE':self.not_implemented_handler,
            'PLATELIST':self.not_implemented_handler,
            'PLATE':self.not_implemented_handler,
            'PLATESETUP':self.not_implemented_handler,
            'PLUGPOS':self.not_implemented_handler,
            'TEMPS':self.not_implemented_handler,
            'STATUS':self.not_implemented_handler,
            'VERSION':self.version_request_handler}

        command_class=message_str.partition(' ')[0].partition('_')[0]
        command=Command(source,message_str)
        if not filter(lambda x: x.source==source, self.commands):
            self.commands.append(command)
        command_handlers.get(command_class.upper(), self.bad_command_handler)(command)

    def version_request_handler(self,command):
        command.state='complete'
        command.reply=self.get_version_string()+'\n'

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

    def not_implemented_handler(self, command):
        """ Placeholder command handler """
        command.state='complete'
        command.reply='!ERROR: Command not implemented.\n'
    
    def bad_command_handler(self, command):
        """ Handle an unrecognized command """
        command.state='complete'
        command.reply='!ERROR: Unrecognized command.\n'
    
    def main(self):
        """
        Loop forever, acting on commands as received if on a port.
        """            
        while True:
            select_start = time.time()
            read_map = {}
            write_map = {}
            error_map = {}
            self.update_select_maps(read_map, write_map, error_map)
            try:
                readers, writers, errors = select.select(
                    read_map.keys(),write_map.keys(),error_map.keys(), 5)
            except select.error, err:
                if err[0] != EINTR:
                    raise
            select_end = time.time()
            #self.logger.debug("select used %.3f s" % (select_end-select_start))
            for reader in readers: read_map[reader]()
            for writer in writers: write_map[writer]()
            for error  in errors:  error_map[error]()       
            #self.logger.debug("select operation used %.3f s" % (time.time() - select_end))

            #log commands
            for command in self.commands:
                self.logger.debug(command)
            
            self.cull_dead_sockets_and_their_commands()
            self.handle_completed_commands()
            


if __name__=='__main__':
    director=Director()
    director.main()
